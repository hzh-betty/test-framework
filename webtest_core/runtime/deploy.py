"""执行部署命令，超时或中断时回收整棵进程树。"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory


def run_deploy_command(command: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    if os.name != "nt":
        return _capture_process(command, command, timeout)
    with TemporaryDirectory(prefix="webtest-deploy-") as directory:
        error_path = Path(directory) / "startup-error.json"
        # Windows venv python.exe 是转发启动器；必须直接监督真正持有 Job 的解释器。
        executable = getattr(sys, "_base_executable", sys.executable)
        actual_command, launcher = command, ""
        if sys.prefix != sys.base_prefix and os.path.normcase(os.path.abspath(command[0])) == os.path.normcase(sys.executable):
            actual_command = [executable, *command[1:]]
            launcher = sys.executable
        launch = [executable, str(Path(__file__).resolve()), json.dumps(actual_command), str(error_path), launcher]
        completed = _capture_process(launch, command, timeout)
        if error_path.exists():
            failure = json.loads(error_path.read_text(encoding="utf-8"))
            raise OSError(failure["errno"], failure["strerror"], failure["filename"], failure["winerror"])
        return completed


def _capture_process(launch: list[str], command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    with subprocess.Popen(launch, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", **options) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_tree(process)
            stdout, stderr = process.communicate()
            exc.cmd, exc.output, exc.stderr = command, stdout, stderr
            raise
        except KeyboardInterrupt:
            _terminate_process_tree(process)
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        # bootstrap 退出时，其唯一 Job 句柄由内核关闭并终止所有后代。
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _join_windows_job() -> int:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    # NULL security attributes 创建不可继承句柄；后代不能延长 Job 生命周期。
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        kernel32.CloseHandle(job)
        raise
    return job


def _windows_bootstrap(command: list[str], error_path: Path, launcher: str = "") -> int:
    try:
        # 在启动真实命令前入 Job，避免子进程先于 AssignProcessToJobObject 派生后代。
        _join_windows_job()
        # 父命令退出后，后代仍可能持有管道；communicate 等待 EOF 也受外层 timeout 管理。
        # 仅对当前 venv 的已确认启动器绕过转发，同时保留其包环境及 sys.executable。
        environment = dict(os.environ, __PYVENV_LAUNCHER__=launcher) if launcher else None
        completed = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, env=environment)
        sys.stdout.buffer.write(completed.stdout)
        sys.stderr.buffer.write(completed.stderr)
        return completed.returncode
    except OSError as exc:
        error_path.write_text(json.dumps({
            "errno": exc.errno, "winerror": getattr(exc, "winerror", None),
            "strerror": exc.strerror, "filename": exc.filename,
        }), encoding="utf-8")
        return 1
    # Job 不主动关闭：bootstrap 退出时由内核关闭，避免在返回退出码前终止自身。


if __name__ == "__main__":
    sys.exit(_windows_bootstrap(json.loads(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]))
