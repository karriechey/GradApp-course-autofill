# Read the values already entered on a finished application page (fields, list tables, page text) into JSON,
# the raw material for drafting private/profile.yaml. Read-only: clicks nothing, saves nothing.
# Created: 2026-11-27  Last modified: 2026-11-27
import json
import re
from datetime import datetime
from pathlib import Path

from autofill.browser import attached_page, settle
from autofill.discover import describe_frames


def run(args):
    out_dir = Path(args.out_dir) / args.school
    out_dir.mkdir(parents=True, exist_ok=True)
    with attached_page(args.cdp_url, args.url_contains) as page:
        if args.url:
            page.goto(args.url)
        settle(page)
        heading = page.locator("h1").first.inner_text().strip() if page.locator("h1").count() else page.title()
        stem = args.page or re.sub(r"[^a-z0-9]+", "_", heading.lower()).strip("_")[:40] or "page"
        captured = {
            "school": args.school,
            "url": page.url,
            "heading": heading,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "frames": describe_frames(page, include_values=True),
        }
        (out_dir / f"{stem}.html").write_text(page.content())
    path = out_dir / f"{stem}.json"
    path.write_text(json.dumps(captured, indent=2))
    filled = sum(field["has_value"] for frame in captured["frames"] for field in frame.get("fields", []))
    tables = sum(len(frame.get("tables", [])) for frame in captured["frames"])
    print(f"{heading}: {filled} filled fields, {tables} list tables -> {path}")
