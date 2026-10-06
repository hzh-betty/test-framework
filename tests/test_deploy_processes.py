import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

import webtest_core.runtime.deploy as deploy


def _tree_command(ready: Path, marker: Path, *, parent_exits: bool) -> list[str]:
    child = (
        "from pathlib import Path; import sys,time; "
        "Path(sys.argv[1]).write_text('started'); "
        "time.sleep(1.5); Path(sys.argv[2]).write_text('escaped')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([getattr(sys, '_base_executable', sys.executable), '-c', {child!r}, sys.argv[1], sys.argv[2]]); "
        + ("" if parent_exits else "time.sleep(2.5)")
    )
    return [sys.executable, "-c", parent, str(ready), str(marker)]


@pytest.mark.parametrize("parent_exits", [False, True])
def test_timeout_stops_descendants_even_after_parent_exits(tmp_path, parent_exits):
    ready, marker = tmp_path / "ready.txt", tmp_path / "escaped.txt"
    command = _tree_command(ready, marker, parent_exits=parent_exits)
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        deploy.run_deploy_command(command, timeout=0.5)
    assert time.monotonic() - started < 1.25
    assert raised.value.cmd == command
    assert ready.exists(), "probe child must have started before timeout"
    time.sleep(1.6)
    assert not marker.exists()


def test_completed_command_preserves_arguments_output_and_exit_code():
    arguments = ["argument with spaces", 'quote"mark', "中文"]
    script = "import json,sys; print(json.dumps(sys.argv[1:])); print('stderr', file=sys.stderr); sys.exit(7)"
    command = [sys.executable, "-c", script, *arguments]
    completed = deploy.run_deploy_command(command, timeout=5)
    assert completed.args == command
    assert completed.returncode == 7
    assert json.loads(completed.stdout) == arguments
    assert completed.stderr == "stderr\n"


def test_current_python_command_keeps_venv_packages_and_prefix():
    script = (
        "import json,sys,selenium; "
        "print(json.dumps({'prefix':sys.prefix,'executable':sys.executable,'selenium':selenium.__version__}))"
    )
    completed = deploy.run_deploy_command([sys.executable, "-c", script], timeout=5)
    assert completed.returncode == 0
    environment = json.loads(completed.stdout)
    assert environment["prefix"] == sys.prefix
    assert environment["executable"] == sys.executable
    assert environment["selenium"]


def test_large_stdout_and_stderr_are_collected_without_deadlock():
    script = "import os; os.write(1, b'a' * 100000); os.write(2, b'b' * 100000)"
    completed = deploy.run_deploy_command([sys.executable, "-c", script], timeout=5)
    assert completed.returncode == 0
    assert completed.stdout == "a" * 100000
    assert completed.stderr == "b" * 100000


def test_missing_executable_raises_oserror(tmp_path):
    with pytest.raises(FileNotFoundError):
        deploy.run_deploy_command([str(tmp_path / "missing-deployer")], timeout=5)


def test_keyboard_interrupt_stops_the_process_tree(tmp_path, monkeypatch):
    ready, marker = tmp_path / "ready.txt", tmp_path / "escaped.txt"
    original_communicate = subprocess.Popen.communicate
    interrupted = False

    def interrupt_once(process, *args, **kwargs):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            deadline = time.monotonic() + 2
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            raise KeyboardInterrupt
        return original_communicate(process, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "communicate", interrupt_once)
    with pytest.raises(KeyboardInterrupt):
        deploy.run_deploy_command(_tree_command(ready, marker, parent_exits=False), timeout=5)
    assert ready.exists()
    time.sleep(1.6)
    assert not marker.exists()


def test_windows_job_setup_failure_prevents_real_command_start(tmp_path, monkeypatch):
    def reject_job():
        raise OSError(5, "job assignment denied")

    monkeypatch.setattr(deploy, "_join_windows_job", reject_job)
    monkeypatch.setattr(deploy.subprocess, "run", lambda *args, **kwargs: pytest.fail("command started without job"))
    failure_path = tmp_path / "startup-error.json"
    assert deploy._windows_bootstrap(["deployer"], failure_path) == 1
    assert json.loads(failure_path.read_text(encoding="utf-8"))["strerror"] == "job assignment denied"


@pytest.mark.skipif(os.name != "nt", reason="Windows ABI structures")
def test_windows_job_structure_matches_pointer_width():
    is_64bit = ctypes.sizeof(ctypes.c_void_p) == 8
    assert ctypes.sizeof(deploy._BasicLimitInformation) == (64 if is_64bit else 48)
    assert ctypes.sizeof(deploy._ExtendedLimitInformation) == (144 if is_64bit else 112)
    assert deploy._BasicLimitInformation.Affinity.offset == (48 if is_64bit else 32)


def test_output_decoding_replaces_invalid_bytes():
    command = [sys.executable, "-c", "import os; os.write(1, b'\\xffoutput\\n')"]
    completed = deploy.run_deploy_command(command, timeout=5)
    assert completed.returncode == 0
    assert completed.stdout.endswith("output\n")
