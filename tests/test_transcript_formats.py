# Parser tests on synthetic transcript lines.
# Created: 2026-10-24  Last modified: 2026-10-24
from transcript_formats import parse_campus_solutions, parse_semester_table


def numbered(text, page=1):
    return [(page, line) for line in text.strip().splitlines()]


def test_campus_solutions_terms_grades_and_transfer_skip():
    lines = numbered("""
Transfer Credits
Incoming Course
MATH 7 Calculus One 4.000 A 2022 FALL SEM
ABC 101 CALCULUS I 6.000 A
2025-2026 Autumn
Course Description Attempted Earned Grade Points
CSC 210 INTRO TO WIDGETS 4.000 4.000 A- 14.800
Course Topic: ROUND WIDGETS
MTH 150 GRAPH THEORY I 4.000 4.000 B+ 13.200
2025-2026 Winter
WRT 310 SCIENCE WRITING 4.000 4.000 A 16.000
2026-2027 Autumn
CSC 410 ADVANCED WIDGETS 4.000 0.000 0.000
""")
    courses = parse_campus_solutions(lines)
    assert [(c["course_code"], c["grade"], c["year"]) for c in courses] == [
        ("CSC 210", "A-", 2025),
        ("MTH 150", "B+", 2025),
        ("WRT 310", "A", 2026),
        ("CSC 410", "", 2026),
    ]
    assert courses[0]["notes"] == "Course Topic: ROUND WIDGETS"
    assert courses[0]["course_title"] == "INTRO TO WIDGETS"


def test_semester_table_keeps_titles_and_multiword_subjects():
    lines = numbered("""
Fall 2022
WRIT 3 CRIT.READ.&ARG A 3.0 3.0 3.0 12.0 1B, 3B A3, C2 AA
ATH PE 12B ELEM ROWING A 1.0 1.0 1.0 4.0 UC E2 AA
Semester Total 4.0 4.0 4.0 16.0 4.000
Spring 2023
MATH 9 PREALGEBRA NP 5.0 0.0 0.0 0.0 2A B4 AA
GEOL 4 ROCKS WITH LAB C 5.0 5.0 5.0 lab 10.0 5A B1 AA
""")
    courses = parse_semester_table(lines)
    assert [(c["course_code"], c["course_title"], c["grade"], c["term"]) for c in courses] == [
        ("WRIT 3", "CRIT.READ.&ARG", "A", "Fall 2022"),
        ("ATH PE 12B", "ELEM ROWING", "A", "Fall 2022"),
        ("MATH 9", "PREALGEBRA", "NP", "Spring 2023"),
        ("GEOL 4", "ROCKS WITH LAB", "C", "Spring 2023"),
    ]


def test_term_header_spanning_pages():
    lines = [(1, "Fall 2024"), (2, "ARTS 5 INTRO SCULPTURE A 3.0 3.0 3.0 12.0 3A C1 AA")]
    courses = parse_semester_table(lines)
    assert courses[0]["term"] == "Fall 2024" and courses[0]["source_page"] == 2


def test_dated_list_uses_printed_start_date():
    from transcript_formats import parse_dated_list
    lines = numbered("""
COURSE TITLE START END GRADE HOURS UNITS CEU
STAT XL 10 INTRODUCTION TO PROBABILITY 8 Jan 2024 15 Mar 2024 A- 40.0 4.00 0.00
ECON XL 1 PRINCIPLES OF ECONOMICS 24 Jun 2024 23 Aug 2024 P 30.0 4.00 0.00
""")
    courses = parse_dated_list(lines)
    assert [(c["course_code"], c["course_title"], c["start_month"], c["year"], c["grade"]) for c in courses] == [
        ("STAT XL 10", "INTRODUCTION TO PROBABILITY", 1, 2024, "A-"),
        ("ECON XL 1", "PRINCIPLES OF ECONOMICS", 6, 2024, "P"),
    ]
