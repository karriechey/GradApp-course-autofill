# Enter reviewed courses into an application's course list popup, one at a time, with verification.
# Only ever clicks "Add Course", "Save and Add Another" and "Cancel"; never touches Continue or any submit control.
# Created: 2026-10-24  Last modified: 2026-10-24
import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

VERIFY_TIMEOUT_MS = 15000
# Overridden by the "form" section of the config; defaults match the MIT EECS "Subjects Taken" popup.
FORM = {"dialog_title": "Subjects Taken", "list_column": "Course Start"}
OPTIONAL_FIELDS = {"Textbook": "textbook", "Grade on Transcript": "grade"}


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def loose(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def course_key(row):
    return f"{row['institution']}|{row['course_name']}|{row['course_start']}"


def load_courses(csv_path):
    with open(csv_path, newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("include", "yes").strip().lower() == "yes"]
    problems = []
    for row in rows:
        label = f"row {row.get('row_id', '?')} ({row.get('course_name', '')})"
        if not row.get("institution", "").strip():
            problems.append(f"{label}: no institution")
        if not row.get("course_name", "").strip():
            problems.append(f"{label}: no course name")
        if not re.fullmatch(r"(0[1-9]|1[0-2])/\d{4}", row.get("course_start", "").strip()):
            problems.append(f"{label}: course_start must be MM/YYYY, got {row.get('course_start')!r}")
    if problems:
        raise SystemExit("fix these rows in the CSV first:\n" + "\n".join(problems))
    return rows


def load_progress(path):
    return json.loads(path.read_text()) if path.exists() else {}


def save_progress(path, progress):
    path.write_text(json.dumps(progress, indent=2))


def course_table(page):
    return page.get_by_role("table").filter(has=page.get_by_role("columnheader", name=FORM["list_column"]))


def listed_courses(page):
    table = course_table(page)
    return [normalize(text) for text in table.locator("tbody tr").all_inner_texts()]


def is_listed(page, row):
    institution, name = loose(row["institution"]), normalize(row["course_name"])
    return any(institution in loose(listed) and name in listed for listed in listed_courses(page))


def open_dialog(page):
    dialog = page.get_by_role("dialog", name=FORM["dialog_title"])
    if not dialog.is_visible():
        course_table(page).get_by_role("link", name="Add Course", exact=True).click()
    dialog.wait_for(state="visible")
    dialog.get_by_label("Course Name").wait_for(state="visible")
    return dialog


def fill_dialog(dialog, row):
    month, year = row["course_start"].strip().split("/")
    institution = dialog.get_by_label("Institution")
    choices = [text.strip() for text in institution.locator("option").all_inner_texts()]
    # Match ignoring case and punctuation, e.g. "University of California, Los Angeles".
    matching = [choice for choice in choices if choice and loose(choice) == loose(row["institution"])]
    if len(matching) != 1:
        raise SystemExit(f"institution {row['institution']!r} not in the form's list {choices}; add it under Academic History")
    institution.select_option(label=matching[0])
    dialog.get_by_label("Course Name").fill(row["course_name"])
    dialog.get_by_role("combobox", name="Month").select_option(value=month)
    year_select = dialog.get_by_role("combobox", name="Year")
    years = [text.strip() for text in year_select.locator("option").all_inner_texts()]
    if year not in years:
        raise SystemExit(f"year {year} is not offered by the form (choices {[y for y in years if y]})")
    year_select.select_option(value=year)
    for label, column in OPTIONAL_FIELDS.items():
        field = dialog.get_by_label(label)
        if field.count():
            field.fill(row.get(column, "").strip())


def cancel_dialog(page):
    dialog = page.get_by_role("dialog", name=FORM["dialog_title"])
    if dialog.is_visible():
        dialog.get_by_role("button", name="Cancel", exact=True).click()
        dialog.wait_for(state="hidden")


def wait_until_listed(page, row):
    deadline = datetime.now().timestamp() + VERIFY_TIMEOUT_MS / 1000
    while datetime.now().timestamp() < deadline:
        if is_listed(page, row):
            return True
        page.wait_for_timeout(500)
    # The list may only refresh once the dialog closes.
    cancel_dialog(page)
    page.reload()
    course_table(page).wait_for(state="visible")
    return is_listed(page, row)


def describe(row):
    return (f"{row['institution']} | {row['course_name']} | start {row['course_start']} | "
            f"grade {row.get('grade') or '(blank)'} | textbook {row.get('textbook') or '(blank)'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="reviewed course CSV")
    parser.add_argument("--config", default="private/config.json")
    parser.add_argument("--profile", default="private/browser_profile")
    parser.add_argument("--progress", default="private/progress.json")
    parser.add_argument("--dry-run", action="store_true", help="fill the first pending course, then cancel without saving")
    parser.add_argument("--limit", type=int, help="stop after saving this many courses")
    parser.add_argument("--confirm-each", action="store_true", help="pause before each save")
    parser.add_argument("--recheck-saved", action="store_true",
                        help="also re-enter courses marked saved in the progress file that are missing from the course list")
    parser.add_argument("--headless", action="store_true", help="for tests against the local mock page")
    args = parser.parse_args()

    courses = load_courses(args.csv)
    progress_path = Path(args.progress)
    progress = load_progress(progress_path)
    pending = [row for row in courses
               if args.recheck_saved or progress.get(course_key(row), {}).get("status") != "saved"]
    print(f"{len(courses)} courses marked include=yes, {len(pending)} not yet saved")
    blank_grades = [row["course_name"] for row in pending if not row.get("grade", "").strip()]
    if blank_grades:
        print(f"blank grade (left empty on the form): {blank_grades}")
    if not pending:
        return

    config = json.loads(Path(args.config).read_text())
    url = config["form_url"]
    FORM.update(config.get("form", {}))
    screenshot_dir = progress_path.parent / "fill_screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(args.profile, headless=args.headless)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url)
        input("\nLog in if needed, open the Courses page, then press Enter here... ")
        course_table(page).wait_for(state="visible")

        if args.dry_run:
            row = pending[0]
            dialog = open_dialog(page)
            fill_dialog(dialog, row)
            print(f"dry run filled: {describe(row)}")
            input("Check the fields in the browser, then press Enter to cancel without saving... ")
            cancel_dialog(page)
            print("cancelled; nothing was saved")
            context.close()
            return

        saved_this_run = 0
        for row in pending:
            key = course_key(row)
            if is_listed(page, row):
                print(f"already listed, skipping: {describe(row)}")
                progress[key] = {"status": "saved", "verified_at": datetime.now().isoformat(timespec="seconds"),
                                 "note": "found in course list before entry"}
                save_progress(progress_path, progress)
                continue

            dialog = open_dialog(page)
            fill_dialog(dialog, row)
            print(f"filled: {describe(row)}")
            if args.confirm_each and input("Save this course? [y/N] ").strip().lower() != "y":
                cancel_dialog(page)
                print("stopped before saving")
                break

            progress[key] = {"status": "submitted", "submitted_at": datetime.now().isoformat(timespec="seconds")}
            save_progress(progress_path, progress)
            dialog.get_by_role("button", name="Save and Add Another", exact=True).click()

            if not wait_until_listed(page, row):
                shot = screenshot_dir / f"not_listed_row{row.get('row_id', '')}.png"
                page.screenshot(path=shot, full_page=True)
                progress[key]["status"] = "unverified"
                save_progress(progress_path, progress)
                print(f"course did not appear in the list; stopping. Screenshot: {shot}")
                print("Check the page by hand. If it was saved, rerunning will detect it and skip it.")
                break

            progress[key] = {"status": "saved", "verified_at": datetime.now().isoformat(timespec="seconds")}
            save_progress(progress_path, progress)
            saved_this_run += 1
            print(f"verified in course list ({saved_this_run} this run)")
            if args.limit and saved_this_run >= args.limit:
                break

        cancel_dialog(page)
        print(f"done: {saved_this_run} saved this run; progress in {progress_path}")
        input("Review the course list in the browser, then press Enter to close it... ")
        context.close()


if __name__ == "__main__":
    try:
        main()
    except PlaywrightTimeout as error:
        raise SystemExit(f"timed out waiting for the page: {error}")
