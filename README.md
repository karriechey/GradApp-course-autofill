# transcript-course-autofill

Created: 2026-10-24. Last updated: 2026-10-24.

Reads courses from unofficial transcript PDFs into a CSV you review, then helps enter them into the course list of a graduate application (built for the MIT EECS application's "Subjects Taken" form, which runs on Slate). You log in yourself in a visible browser. The tool never solves CAPTCHAs, never works around access controls, and never clicks the final application submit button.

Not affiliated with MIT or any university.

## Status

- `extract_courses.py`: transcript PDFs to CSV. Done.
- `inspect_form.py`: records the structure of the course modal so the autofill uses real labels. Done.
- `fill_courses.py`: autofill with dry run, "Save and Add Another", per-course verification and resume. Done.

## Setup

```
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m playwright install chromium
```

## Your data stays in `private/`

Everything personal lives in `private/`, which is gitignored: transcripts, `config.json`, the course CSV, the browser login profile, form captures and the progress file.

```
mkdir -p private/transcripts
cp examples/config.example.json private/config.json   # then edit it
```

`config.json` holds your application form URL and one entry per transcript:

- `path`: the PDF in `private/transcripts/`
- `format`: `campus-solutions` (PeopleSoft layout, headers like `2025-2026 Autumn`), `semester-table` (headers like `Fall 2022`, rows `CODE TITLE GRADE units...`) or `dated-list` (rows `CODE TITLE 12 Jan 2024 22 Mar 2024 GRADE ...`, start month taken from the printed date)
- `institution`: name as it should appear on the application
- `term_months` (optional): start month per term, overriding the defaults in `transcript_formats.py`

## 1. Extract

```
.venv/bin/python extract_courses.py
```

Writes `private/courses.csv` and refuses to overwrite an existing one. Course names and grades are copied exactly as printed. Transcripts list terms, not dates, so every start month is a guess and is flagged `start_month_inferred_from_term`. Other flags: `no_grade_in_progress`, `grade_NP_no_credit` (and similar for W, I, IP). Transfer-credit sections are skipped; enter those courses from the original school's transcript.

## 2. Review

Open `private/courses.csv` and fix it by hand: correct start months, set `include` to `no` for rows to skip, fill `textbook` only where known. See `examples/courses.example.csv`.

## 3. Inspect the form

```
.venv/bin/python inspect_form.py
```

Opens Chromium on your form URL. Log in, go to the Courses page, press Enter; open an empty course modal, press Enter; cancel it, press Enter. Read-only. Saves screenshots, HTML and a field list to `private/form_inspection/<timestamp>/`.

## 4. Fill

```
.venv/bin/python fill_courses.py --csv private/courses.csv --dry-run
.venv/bin/python fill_courses.py --csv private/courses.csv --limit 1 --confirm-each
.venv/bin/python fill_courses.py --csv private/courses.csv
```

Log in yourself in the window that opens, go to the Courses page, press Enter. Rows with `include=yes` are entered one at a time: Institution, Course Name, Textbook (only if set), Course Start month and year, Grade on Transcript, then "Save and Add Another". After each save the script waits for the course to appear in the course list and records it in `private/progress.json`. A course already in the list is skipped, so rerunning after a crash does not create duplicates. If a course does not appear, it stops and saves a screenshot.

- `--dry-run`: fill the first pending course, wait for you to check it, then Cancel. Nothing is saved.
- `--confirm-each`: ask before every save.
- `--limit N`: stop after N saved courses.
- `--recheck-saved`: also re-enter courses the progress file marks saved but that are missing from the course list (e.g. deleted by accident).

The script only clicks "Add Course", "Save and Add Another" and "Cancel". It never clicks Continue or any submit control. The institution must already exist on the Academic History page.

## Before every commit

`check_private.py` fails if any file git would commit is inside `private/`, is a data file outside `examples/` or `tests/`, or contains a term from `private/private_terms.txt`. Put your name, schools, student IDs, form URL and course names in that file (one per line). Install it as a pre-commit hook:

```
printf '#!/bin/sh\n.venv/bin/python check_private.py\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Tests

```
.venv/bin/python -m pytest -q
```

Tests use invented transcript lines and a local mock of the course page (`tests/fixtures/`), headless, no network.

## License

MIT
