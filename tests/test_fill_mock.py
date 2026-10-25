# End-to-end run of fill_courses.py against a local mock of the course page (headless, no network).
# Created: 2026-10-24  Last modified: 2026-10-24
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MOCK_PAGE = REPO / "tests" / "fixtures" / "mock_courses_page.html"
EXAMPLE_CSV = REPO / "examples" / "courses.example.csv"


def run_fill(tmp_path, *extra_args):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"form_url": MOCK_PAGE.as_uri()}))
    command = [sys.executable, str(REPO / "fill_courses.py"), "--csv", str(EXAMPLE_CSV), "--config", str(config),
               "--profile", str(tmp_path / "profile"), "--progress", str(tmp_path / "progress.json"),
               "--headless", *extra_args]
    return subprocess.run(command, input="\n\n\n", capture_output=True, text=True, timeout=120, cwd=REPO)


def test_dry_run_saves_nothing(tmp_path):
    result = run_fill(tmp_path, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "nothing was saved" in result.stdout
    assert not (tmp_path / "progress.json").exists()


def test_saves_verifies_and_resumes(tmp_path):
    result = run_fill(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stdout.count("verified in course list") == 3
    progress = json.loads((tmp_path / "progress.json").read_text())
    assert [entry["status"] for entry in progress.values()] == ["saved"] * 3

    rerun = run_fill(tmp_path)
    assert "0 not yet saved" in rerun.stdout
