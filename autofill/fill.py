# Fill the mapped fields of one portal page from the profile, including list entries added through popups.
# Never clicks Submit or Continue. A popup's Save is clicked only with --save; without it the first filled popup
# stays open for review. Writes a per-field report to private/fill_reports/.
# Created: 2026-11-27  Last modified: 2026-11-27
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

from autofill import profile as values
from autofill.browser import attached_page, settle
from autofill.discover import describe_frames

FILLED_STYLE = "outline: 3px solid #2e9d5b; outline-offset: 2px;"
TEXT_KINDS = {"text", "textarea", "email", "tel", "url", "number", "search", "richtext", "combobox"}

FIELD_STATE_JS = """
(el) => {
  const kind = el.tagName === 'SELECT' ? 'select' : el.tagName === 'TEXTAREA' ? 'textarea'
    : el.isContentEditable ? 'richtext' : (el.type || 'text').toLowerCase();
  let hasValue;
  if (kind === 'select') hasValue = [...el.selectedOptions].some((o) => o.value !== '' && o.text.trim() !== '');
  else if (kind === 'checkbox' || kind === 'radio') hasValue = el.checked;
  else if (kind === 'richtext') hasValue = el.innerText.trim() !== '';
  else hasValue = (el.value || '') !== '';
  const options = kind === 'select' ? [...el.options].map((o) => ({ value: o.value, text: o.text.trim() })) : null;
  return { kind, hasValue, maxlength: el.maxLength > 0 ? el.maxLength : null, options };
}
"""

RADIO_GROUP_JS = """
(els) => els.map((el) => {
  const lab = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
  return { value: el.value, text: (lab ? lab.innerText : el.value).trim(), checked: el.checked };
})
"""


def loose(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


class Report:
    def __init__(self):
        self.rows = []

    def add(self, status, where, label, detail=""):
        self.rows.append({"status": status, "where": where, "label": label, "detail": detail})
        print(f"  {status:18} {where[:40]:40} {label[:40]:40} {detail}")

    def summary(self):
        return dict(Counter(row["status"] for row in self.rows))


def choose_option(options, wanted, spec):
    real = [option for option in options if option["value"] != "" or option["text"]]
    if spec.get("part") == "month" and isinstance(wanted, int):
        names = {f"{wanted:02d}", str(wanted), loose(values.MONTH_NAMES[wanted - 1]),
                 loose(values.MONTH_NAMES[wanted - 1][:3])}
        matches = [o for o in real if o["value"] in names or loose(o["text"]) in names]
    else:
        wanted = spec.get("options", {}).get(str(wanted), wanted)
        matches = [o for o in real if loose(o["text"]) == loose(wanted)] or \
                  [o for o in real if o["value"] == str(wanted)]
    return matches[0] if len(matches) == 1 else None


def resolve(spec, data, maxlength, kind):
    if "value" in spec:
        return spec["value"], ""
    raw = values.lookup(data, spec["profile"])
    if spec.get("part"):
        part = values.date_part(raw, spec["part"]) if raw else None
        return (part, "") if part else (None, "no profile value")
    if spec.get("format"):
        formatted = values.format_date(raw, spec["format"]) if raw else None
        return (formatted, "") if formatted else (None, "no profile value")
    if kind in TEXT_KINDS:
        return values.pick_text(data, spec["profile"], maxlength)
    if raw in (None, "", []):
        return None, "no profile value"
    return raw, ""


def locate(scope, spec):
    if spec.get("selector"):
        return scope.locator(spec["selector"])
    return scope.get_by_label(spec["label"], exact=True).nth(spec.get("nth", 0))


def highlight(locator):
    locator.evaluate(f"el => {{ (el.closest('.form_question') || el).style.cssText += '{FILLED_STYLE}'; }}")


def apply_value(locator, spec, data, args, report, where, retried=False):
    label = spec.get("label") or spec.get("selector")
    try:
        if spec.get("kind") == "radio_group":
            return apply_radio(locator, spec, data, args, report, where)
        state = locator.evaluate(FIELD_STATE_JS)
        if state["hasValue"] and not args.overwrite:
            return report.add("skipped_has_value", where, label)
        value, problem = resolve(spec, data, state["maxlength"] or spec.get("maxlength"), state["kind"])
        if value is None:
            status = "too_long" if problem.startswith("too long") else "no_profile_value"
            return report.add(status, where, label, problem)
        if state["kind"] == "select" and state["options"] is None:
            shown = f"{value} (option matched at fill time)"
        elif state["kind"] == "select":
            option = choose_option(state["options"], value, spec)
            if not option:
                return report.add("unresolved", where, label, f"{value!r} matches no single option")
            shown = option["text"]
            if not args.dry_run:
                locator.select_option(value=option["value"])
        elif state["kind"] == "checkbox":
            shown = bool(value) and str(value).lower() not in ("no", "false")
            if not args.dry_run:
                locator.set_checked(shown)
        else:
            shown = value
            if not args.dry_run:
                locator.fill(str(value))
        if args.dry_run:
            return report.add("would_fill", where, label, repr(shown)[:70])
        highlight(locator)
        report.add("filled", where, label, repr(shown)[:70])
    except Exception as error:
        if not retried and not args.dry_run:
            # Slate re-renders fields after a choice elsewhere; one retry covers a stale element.
            locator.page.wait_for_timeout(700)
            return apply_value(locator, spec, data, args, report, where, retried=True)
        report.add("error", where, label, str(error).splitlines()[0][:100])


def apply_radio(locator, spec, data, args, report, where):
    label = spec.get("label")
    choices = locator.evaluate_all(RADIO_GROUP_JS)
    if any(choice["checked"] for choice in choices) and not args.overwrite:
        return report.add("skipped_has_value", where, label)
    value, problem = resolve(spec, data, None, "radio_group")
    if value is None:
        return report.add("no_profile_value", where, label, problem)
    option = choose_option(choices, value, spec)
    if not option:
        return report.add("unresolved", where, label, f"{value!r} matches no single option")
    if args.dry_run:
        return report.add("would_fill", where, label, repr(option["text"]))
    target = locator.and_(locator.page.locator(f"[value=\"{option['value']}\"]"))
    target.check()
    highlight(target)
    report.add("filled", where, label, repr(option["text"]))


def listed_column(page, column):
    return page.evaluate("""(column) => {
      const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      for (const table of document.querySelectorAll('table')) {
        if (!visible(table)) continue;
        const heads = [...table.querySelectorAll('th')].map((th) => th.innerText.trim());
        const index = heads.indexOf(column);
        if (index < 0) continue;
        return [...table.querySelectorAll('tbody > tr')].filter(visible)
          .map((row) => (row.children[index] || {}).innerText || '').map((t) => t.trim()).filter(Boolean);
      }
      return null;
    }""", column)


def is_listed(name, cells):
    wanted = loose(name)
    for cell in cells:
        shown = loose(cell.rstrip(".…"))
        if shown == wanted or (cell.endswith(("...", "…")) and wanted.startswith(shown)):
            return True
    return False


def empty_required(page, dialog_title):
    frames = describe_frames(page)
    return [field["label"] for field in frames[0]["fields"]
            if field["dialog_title"] == dialog_title and field["visible"] and field["required"]
            and not field["has_value"]]


def fill_repeat(page, repeat, profile, args, report):
    title = repeat["dialog_title"]
    entries = values.lookup(profile, repeat["profile"]) or []
    listed = listed_column(page, repeat["list_column"])
    if listed is None:
        return report.add("error", title, repeat["list_column"], "list table not found on this page")
    skip = {loose(name) for name in repeat.get("skip_entries", [])}
    room = repeat.get("max_rows", 99) - len(listed)
    added = 0
    for position, entry in enumerate(entries, 1):
        entry = {**entry, "_position": position}
        name = str(values.lookup(entry, repeat["match_on"]) or "")
        where = f"{title}: {name}"
        if loose(name) in skip:
            report.add("skipped_mapping", where, "", "listed in skip_entries")
            continue
        if is_listed(name, listed):
            report.add("skipped_listed", where, "", "already in the list")
            continue
        if room <= 0:
            report.add("no_room", where, "", f"list allows {repeat.get('max_rows')} rows")
            continue
        if args.limit and added >= args.limit:
            report.add("not_attempted", where, "", f"--limit {args.limit}")
            continue
        if args.dry_run:
            for spec in repeat["fields"]:
                apply_value(_DryLocator(spec), spec, entry, args, report, where)
            room -= 1
            added += 1
            continue

        dialog = page.get_by_role("dialog", name=title)
        add_links = page.get_by_role("link", name=repeat["add_link"], exact=True)
        add_links.first.click()
        dialog.wait_for(state="visible")
        page.wait_for_timeout(800)
        for spec in repeat["fields"]:
            field = locate(dialog, spec)
            if not field.count():
                continue  # fields that depend on an earlier choice, e.g. publication type
            apply_value(field, spec, entry, args, report, where)
            if spec.get("wait_after"):
                page.wait_for_timeout(spec["wait_after"])
        missing = empty_required(page, title)
        if missing:
            report.add("incomplete", where, "", f"required fields left empty: {missing}; popup cancelled")
            dialog.get_by_role("button", name="Cancel", exact=True).click()
            dialog.wait_for(state="hidden")
            continue
        if not args.save:
            report.add("left_open", where, "", "popup filled and left open for review (no --save)")
            return "stop"
        dialog.get_by_role("button", name=repeat.get("save_button", "Save"), exact=True).click()
        dialog.wait_for(state="hidden", timeout=15000)
        page.wait_for_timeout(1500)
        listed = listed_column(page, repeat["list_column"]) or []
        report.add("saved" if is_listed(name, listed) else "saved_unverified", where, "")
        room -= 1
        added += 1


class _DryLocator:
    # Stands in for a popup field that a dry run does not open; kind and maxlength come from the mapping.
    def __init__(self, spec):
        self.spec = spec

    def evaluate(self, script):
        return {"kind": self.spec.get("kind", "text"), "hasValue": False, "maxlength": self.spec.get("maxlength"),
                "options": None}


def run(args):
    profile = values.load(args.profile)
    mapping = yaml.safe_load(Path(args.mapping_dir, f"{args.school}.yaml").read_text())
    page_map = mapping["pages"][args.page]
    report = Report()
    with attached_page(args.cdp_url, args.url_contains or mapping.get("url_contains")) as page:
        if page_map.get("url") and page_map["url"] not in page.url:
            page.goto(page_map["url"])
        settle(page)
        print(f"{'dry run' if args.dry_run else 'filling'}: {args.school} / {args.page} ({page.url})")
        for spec in page_map.get("fields", []):
            label = spec.get("label", spec.get("selector", ""))
            status = spec.get("status", "mapped")
            if status != "mapped":
                report.add(status, "page", label)
                continue
            field = locate(page, spec)
            if not field.count():
                report.add("not_on_page", "page", label, spec.get("selector", ""))
                continue
            apply_value(field.first if spec.get("kind") != "radio_group" else field, spec, profile, args, report, "page")
        for repeat in page_map.get("repeats", []):
            try:
                if fill_repeat(page, repeat, profile, args, report) == "stop":
                    break
            except Exception as error:
                report.add("error", repeat["dialog_title"], "", str(error).splitlines()[0][:120])
                dialog = page.get_by_role("dialog", name=repeat["dialog_title"])
                if dialog.is_visible():
                    dialog.get_by_role("button", name="Cancel", exact=True).click()
    out_dir = Path(args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.school}_{args.page}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps({"dry_run": args.dry_run, "summary": report.summary(), "rows": report.rows}, indent=2))
    print(f"\nsummary: {report.summary()}\nreport: {path}")
