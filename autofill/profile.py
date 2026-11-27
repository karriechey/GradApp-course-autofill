# Load private/profile.yaml and turn its values into what a form field needs: length variants, date parts, text.
# Created: 2026-11-27  Last modified: 2026-11-27
import datetime
import re

import yaml

MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]


def load(path):
    with open(path) as handle:
        return yaml.safe_load(handle)


def lookup(container, key):
    value = container
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def text_variants(container, key):
    # "description" resolves to description, description_<n> and description_full, shortest first.
    parent_key, _, leaf = key.rpartition(".")
    parent = lookup(container, parent_key) if parent_key else container
    if not isinstance(parent, dict):
        return []
    pattern = re.compile(rf"^{re.escape(leaf)}(_\d+|_full)?$")
    variants = [str(value).strip() for name, value in parent.items()
                if pattern.match(name) and value not in (None, "") and not isinstance(value, (dict, list))]
    return sorted(set(variants), key=len)


def pick_text(container, key, maxlength):
    variants = text_variants(container, key)
    if not variants:
        return None, "no profile value"
    if not maxlength:
        return variants[-1], ""
    fitting = [text for text in variants if len(text) <= maxlength]
    if not fitting:
        return None, f"too long: shortest variant is {len(variants[0])} chars, limit {maxlength}"
    # Fall back to shorter variants only as far as the limit requires.
    return fitting[-1], ""


def year_month(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.year, value.month
    match = re.fullmatch(r"(\d{4})(?:-(\d{1,2}))?(?:-\d{1,2})?", str(value or "").strip())
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2)) if match.group(2) else None


def date_part(value, part):
    year, month = year_month(value)
    if part == "year":
        return str(year) if year else None
    if part == "month":
        return month
    if part == "day":
        return value.day if isinstance(value, datetime.date) else None
    raise ValueError(f"unknown date part {part!r}")


def format_date(value, fmt):
    if isinstance(value, datetime.date):
        return value.strftime(fmt)
    year, month = year_month(value)
    if not year:
        return None
    return datetime.date(year, month or 1, 1).strftime(fmt)
