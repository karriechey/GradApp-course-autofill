# autofill discover attached over CDP to a headless Chromium showing the mock Slate page.
# Created: 2026-11-26  Last modified: 2026-11-26
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
MOCK_PAGE = REPO / "tests" / "fixtures" / "mock_slate_application.html"
CDP_PORT = 9333


def run_discover(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=[f"--remote-debugging-port={CDP_PORT}"])
        page = browser.new_page()
        page.goto(MOCK_PAGE.as_uri())
        page.frame(name="recs").wait_for_selector("#rec_email")
        command = [sys.executable, "-m", "autofill", "discover", "--school", "mock", "--page", "experience",
                   "--inventory-dir", str(tmp_path), "--cdp-url", f"http://localhost:{CDP_PORT}",
                   "--url-contains", "mock_slate"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, cwd=REPO)
        assert result.returncode == 0, result.stderr + result.stdout
        browser.close()
    return json.loads((tmp_path / "mock_experience.json").read_text())


def test_discover_lists_fields_groups_popups_and_iframes(tmp_path):
    inventory = run_discover(tmp_path)
    main_frame, recs_frame = inventory["frames"]
    fields = {field["label"]: field for field in main_frame["fields"]}

    phone = fields["Mobile Phone"]
    assert phone["selector"] == "#form_phone" and phone["required"] and phone["maxlength"] == 20
    assert phone["has_value"] and "555" not in json.dumps(inventory)

    citizenship = fields["Citizenship Status"]
    assert citizenship["kind"] == "radio_group"
    assert [option["text"] for option in citizenship["options"]] == ["U.S. Citizen", "Permanent Resident", "International"]

    assert [option["text"] for option in fields["Country"]["options"]] == ["", "United States", "Canada"]
    assert fields["Organization"]["dialog_title"] == "Employment" and not fields["Organization"]["visible"]
    assert fields["Description"]["maxlength"] == 500
    assert fields["Honor Title"]["repeat_hint"] and fields["Honor Title"]["section"] == "Honors"

    adds = {control["text"]: control for control in main_frame["add_controls"]}
    assert adds["Add Employment"]["table_columns"] == ["Organization", "Position", "Dates"]
    assert adds["Add Employment"]["table_rows"] == 1
    assert "Add Another Honor" in adds

    assert recs_frame["name"] == "recs"
    assert recs_frame["fields"][0]["label"] == "Recommender Email" and recs_frame["fields"][0]["required"]
