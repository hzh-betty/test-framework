from pathlib import Path


def test_ci_templates_exist_and_reference_required_commands():
    root = Path(__file__).resolve().parents[2]
    github = root / ".github" / "workflows" / "webtest.yml"
    gitlab = root / ".gitlab-ci.yml"
    jenkins = root / "Jenkinsfile"

    for path in (github, gitlab, jenkins):
        assert path.exists(), f"{path} should exist"
        content = path.read_text(encoding="utf-8")
        assert "uv sync --dev" in content
        assert "--dry-run" in content
        assert "--deploy" in content
        assert "--stats-output" in content
        assert "artifacts" in content
