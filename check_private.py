# Fail if any file git would commit contains a term from private/private_terms.txt or is a transcript-like file.
# Created: 2026-10-24  Last modified: 2026-10-24
import subprocess
import sys
from pathlib import Path

TERMS_FILE = Path("private/private_terms.txt")
ALLOWED_DATA_DIRS = ("examples/", "tests/")
BLOCKED_SUFFIXES = {".pdf", ".csv", ".json", ".png", ".html"}


def commit_candidates():
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=True,
    )
    return [Path(name) for name in listing.stdout.splitlines() if Path(name).is_file()]


def main():
    if not TERMS_FILE.exists():
        sys.exit(f"missing {TERMS_FILE}: list one private term per line (names, schools, IDs, form URL)")
    terms = [line.strip() for line in TERMS_FILE.read_text().splitlines() if line.strip() and not line.startswith("#")]

    problems = []
    for path in commit_candidates():
        if path.parts[0] == "private":
            problems.append(f"{path}: inside private/")
            continue
        if path.suffix.lower() in BLOCKED_SUFFIXES and not str(path).startswith(ALLOWED_DATA_DIRS):
            problems.append(f"{path}: data file outside examples/ or tests/")
        text = path.read_bytes().decode("utf-8", errors="ignore").lower()
        problems += [f"{path}: contains a private term (line {terms.index(term) + 1} of {TERMS_FILE})"
                     for term in terms if term.lower() in text]

    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(f"checked {len(commit_candidates())} files against {len(terms)} private terms: clean")


if __name__ == "__main__":
    main()
