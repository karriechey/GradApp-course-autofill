# Line parsers for three common unofficial-transcript PDF layouts.
# Created: 2026-10-24  Last modified: 2026-10-24
import re

import pdfplumber

# PeopleSoft Campus Solutions layout: "2025-2026 Autumn" headers, rows end in attempted/earned/grade/points.
CAMPUS_SOLUTIONS_TERM = re.compile(r"^(\d{4})-(\d{4}) (Autumn|Fall|Winter|Spring|Summer)$")
CAMPUS_SOLUTIONS_COURSE = re.compile(
    r"^(?P<code>[A-Z]{2,5} \d{2,4}[A-Z]?) (?P<title>.+?) (?P<attempted>\d+\.\d{3}) (?P<earned>\d+\.\d{3})"
    r"(?: (?P<grade>[A-Z][+-]?|[A-Z]{2}))? (?P<points>\d+\.\d{3})$"
)

# Semester table layout: "Fall 2022" headers, rows are code, title, grade, then unit columns.
SEMESTER_TABLE_TERM = re.compile(r"^(Fall|Spring|Summer|Winter) (\d{4})$")
SEMESTER_TABLE_COURSE = re.compile(
    r"^(?P<code>[A-Z]+(?: [A-Z]+)* \d+[A-Z]*) (?P<title>.+?) (?P<grade>[A-F][+-]?|P|NP|W|IP|I)"
    r" (?P<enrolled>\d+\.\d) (?P<attempted>\d+\.\d) (?P<completed>\d+\.\d)\b"
)

# Dated list layout: one row per course with its own start and end date, e.g. continuing-education transcripts.
DATED_LIST_COURSE = re.compile(
    r"^(?P<code>[A-Z]+(?: [A-Z]+)* \d+[A-Z]*) (?P<title>.+?) (?P<start>\d{1,2} [A-Z][a-z]{2} \d{4})"
    r" (?P<end>\d{1,2} [A-Z][a-z]{2} \d{4}) (?P<grade>[A-F][+-]?|P|NP|W|I|IP)(?= )"
)
MONTHS = {name: number for number, name in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

# Transcripts print terms, not dates; these are typical start months and every use is flagged.
DEFAULT_TERM_MONTHS = {
    "campus-solutions": {"Autumn": 9, "Fall": 9, "Winter": 1, "Spring": 3, "Summer": 6},
    "semester-table": {"Fall": 8, "Spring": 2, "Summer": 6, "Winter": 1},
    "dated-list": {},
}

NO_CREDIT_GRADES = {"NP", "W", "IP", "I"}


def pdf_lines(path):
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for line in (page.extract_text() or "").splitlines():
                yield page_number, line.strip()


def parse_campus_solutions(numbered_lines):
    courses, term, in_transfer_section = [], None, False
    for page_number, line in numbered_lines:
        if line == "Transfer Credits":
            in_transfer_section = True
            continue
        term_match = CAMPUS_SOLUTIONS_TERM.match(line)
        if term_match:
            in_transfer_section = False
            first_year, second_year, season = term_match.groups()
            year = int(first_year) if season in {"Autumn", "Fall"} else int(second_year)
            term = (line, season, year)
            continue
        # Transfer credit repeats courses from other schools; enter those from their own transcripts.
        if in_transfer_section or term is None:
            continue
        if line.startswith("Course Topic:") and courses:
            courses[-1]["notes"] = line
            continue
        course_match = CAMPUS_SOLUTIONS_COURSE.match(line)
        if course_match:
            courses.append(_course(term, course_match, course_match["grade"] or "", page_number))
    return courses


def parse_semester_table(numbered_lines):
    courses, term = [], None
    for page_number, line in numbered_lines:
        term_match = SEMESTER_TABLE_TERM.match(line)
        if term_match:
            season, year = term_match.groups()
            term = (line, season, int(year))
            continue
        if term is None:
            continue
        course_match = SEMESTER_TABLE_COURSE.match(line)
        if course_match:
            courses.append(_course(term, course_match, course_match["grade"], page_number))
    return courses


def parse_dated_list(numbered_lines):
    courses = []
    for page_number, line in numbered_lines:
        course_match = DATED_LIST_COURSE.match(line)
        if not course_match:
            continue
        _, month_name, year = course_match["start"].split()
        courses.append({
            "term": f"{course_match['start']} to {course_match['end']}",
            "season": None,
            "year": int(year),
            "start_month": MONTHS[month_name],
            "course_code": course_match["code"],
            "course_title": course_match["title"],
            "grade": course_match["grade"],
            "notes": "",
            "source_page": page_number,
        })
    return courses


def _course(term, course_match, grade, page_number):
    term_label, season, year = term
    return {
        "term": term_label,
        "season": season,
        "year": year,
        "course_code": course_match["code"],
        "course_title": course_match["title"],
        "grade": grade,
        "notes": "",
        "source_page": page_number,
    }


PARSERS = {
    "campus-solutions": parse_campus_solutions,
    "semester-table": parse_semester_table,
    "dated-list": parse_dated_list,
}
