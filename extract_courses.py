# Turn transcript PDFs listed in a config file into a course CSV for review before autofill.
# Created: 2026-10-24  Last modified: 2026-10-24
import argparse
import csv
import json
from pathlib import Path

from transcript_formats import DEFAULT_TERM_MONTHS, NO_CREDIT_GRADES, PARSERS, pdf_lines

FIELDS = [
    "row_id", "include", "institution", "term", "course_code", "course_title", "course_name",
    "course_start", "grade", "textbook", "flags", "notes", "source_file", "source_page",
]


def course_rows(transcript):
    layout = transcript["format"]
    term_months = {**DEFAULT_TERM_MONTHS[layout], **transcript.get("term_months", {})}
    rows = []
    for course in PARSERS[layout](pdf_lines(transcript["path"])):
        if course.get("start_month"):
            start_month, flags = course["start_month"], ["start_date_from_transcript"]
        else:
            start_month, flags = term_months[course["season"]], ["start_month_inferred_from_term"]
        if not course["grade"]:
            flags.append("no_grade_in_progress")
        elif course["grade"] in NO_CREDIT_GRADES:
            flags.append(f"grade_{course['grade']}_no_credit")
        rows.append({
            "include": "yes",
            "institution": transcript["institution"],
            "term": course["term"],
            "course_code": course["course_code"],
            "course_title": course["course_title"],
            "course_name": f"{course['course_code']} {course['course_title']}",
            "course_start": f"{start_month:02d}/{course['year']}",
            "grade": course["grade"],
            "textbook": "",
            "flags": ";".join(flags),
            "notes": course["notes"],
            "source_file": Path(transcript["path"]).name,
            "source_page": course["source_page"],
        })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="private/config.json")
    parser.add_argument("--out", default="private/courses.csv")
    args = parser.parse_args()

    out_path = Path(args.out)
    if out_path.exists():
        raise SystemExit(f"{out_path} exists; move it or pass --out so your edits are not overwritten")

    config = json.loads(Path(args.config).read_text())
    rows = []
    for transcript in config["transcripts"]:
        transcript_rows = course_rows(transcript)
        print(f"{transcript['institution']}: {len(transcript_rows)} courses")
        rows.extend(transcript_rows)
    for row_id, row in enumerate(rows, start=1):
        row["row_id"] = row_id

    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
