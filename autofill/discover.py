# List every form field on the current portal page (all frames) and write it to an inventory JSON.
# Read-only: records whether a field has a value, never the value itself.
# Created: 2026-11-26  Last modified: 2026-11-27
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from autofill.browser import attached_page, settle

DESCRIBE_FRAME_JS = r"""
(includeValues) => {
  const clean = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const textOf = (el) => clean(el ? (el.innerText || el.textContent) : '');
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const unique = (sel) => { try { return document.querySelectorAll(sel).length === 1; } catch (e) { return false; } };
  const quoted = (v) => '"' + v.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';

  const selectorOf = (el) => {
    if (el.id && unique('#' + CSS.escape(el.id))) return '#' + CSS.escape(el.id);
    const name = el.getAttribute('name');
    const tag = el.tagName.toLowerCase();
    if (name && unique(`${tag}[name=${quoted(name)}]`)) return `${tag}[name=${quoted(name)}]`;
    const parts = [];
    for (let node = el; node && node.nodeType === 1 && node !== document.body; node = node.parentElement) {
      if (node.id && unique('#' + CSS.escape(node.id))) { parts.unshift('#' + CSS.escape(node.id)); break; }
      const same = [...node.parentElement.children].filter((c) => c.tagName === node.tagName);
      const t = node.tagName.toLowerCase();
      parts.unshift(same.length > 1 ? `${t}:nth-of-type(${same.indexOf(node) + 1})` : t);
    }
    return parts.join(' > ');
  };

  const question = (el) => el.closest('.form_question, fieldset, [role=radiogroup], [role=group], tr');
  const questionLabel = (el) => {
    const q = question(el);
    const lab = q && q.querySelector('.form_label, legend, [role=heading], th, label');
    return lab ? textOf(lab) : '';
  };
  const ownLabel = (el) => {
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const t = clean(by.split(/\s+/).map((id) => textOf(document.getElementById(id))).join(' '));
      if (t) return t;
    }
    if (el.id) {
      const lab = document.querySelector(`label[for=${quoted(el.id)}]`);
      if (lab) return textOf(lab);
    }
    const wrap = el.closest('label');
    if (wrap) return textOf(wrap);
    return clean(el.getAttribute('aria-label'));
  };
  const labelOf = (el) => ownLabel(el) || questionLabel(el)
    || clean(el.getAttribute('placeholder') || el.getAttribute('title'));

  const required = (el) => {
    const q = question(el);
    return !!(el.required || el.getAttribute('aria-required') === 'true'
      || (q && (q.getAttribute('data-required') === '1' || q.classList.contains('required')))
      || /\*\s*$/.test(labelOf(el)));
  };

  const dialogOf = (el) => {
    const d = el.closest('[role=dialog], dialog, .ui-dialog');
    if (!d) return null;
    const by = d.getAttribute('aria-labelledby');
    return clean(d.getAttribute('aria-label'))
      || (by ? textOf(document.getElementById(by)) : '')
      || textOf(d.querySelector('h1, h2, h3, .ui-dialog-title'))
      || '(untitled popup)';
  };

  const headings = [...document.querySelectorAll('h1, h2, h3, h4, legend, .form_section_title, .section-title')]
    .filter((h) => textOf(h));
  const sectionOf = (el) => {
    let last = '';
    for (const h of headings) {
      if (h.contains(el)) continue;
      if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) last = textOf(h);
    }
    return last;
  };

  // Hints that a field belongs to a repeating block: indexed names, or a container whose class says so.
  const repeatHint = (el) => {
    const name = el.getAttribute('name') || el.id || '';
    const indexed = name.match(/\[(\d+)\]|_(\d+)$/);
    if (indexed) return `indexed name (${indexed[0]})`;
    const box = el.closest('[class*=repeat], [class*=multiple], [class*=clone], [data-repeat], [data-index]');
    return box ? `container .${clean(box.className).split(' ')[0] || box.tagName.toLowerCase()}` : '';
  };

  const kindOf = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'select') return el.multiple ? 'multiselect' : 'select';
    if (tag === 'textarea') return 'textarea';
    if (el.isContentEditable) return 'richtext';
    if (el.getAttribute('role') === 'combobox' || el.getAttribute('aria-autocomplete')) return 'combobox';
    return (el.type || 'text').toLowerCase();
  };

  const common = (el) => ({
    section: sectionOf(el),
    in_dialog: !!dialogOf(el),
    dialog_title: dialogOf(el),
    repeat_hint: repeatHint(el),
    visible: visible(el),
    disabled: !!el.disabled,
  });

  const fields = [];
  const groups = new Map();
  const skipTypes = new Set(['hidden', 'submit', 'button', 'image', 'reset']);
  for (const el of document.querySelectorAll('input, select, textarea, [contenteditable=true]')) {
    const kind = kindOf(el);
    if (skipTypes.has(kind)) continue;
    if ((kind === 'radio' || kind === 'checkbox') && el.name) {
      const members = document.querySelectorAll(`input[name=${quoted(el.name)}]`);
      if (kind === 'radio' || members.length > 1) {
        if (!groups.has(el.name)) {
          const entry = {
            kind: kind + '_group', label: questionLabel(el) || labelOf(el), name: el.name, id: '',
            selector: `input[name=${quoted(el.name)}]`, required: required(el), maxlength: null,
            options: [], has_value: false, ...common(el),
          };
          groups.set(el.name, entry);
          fields.push(entry);
        }
        const entry = groups.get(el.name);
        entry.options.push({ value: el.value, text: ownLabel(el) || el.value });
        entry.has_value = entry.has_value || el.checked;
        if (includeValues && el.checked) entry.value = [...(entry.value || []), ownLabel(el) || el.value];
        entry.visible = entry.visible || visible(el);
        continue;
      }
    }
    const maxlength = el.maxLength > 0 ? el.maxLength : (parseInt(el.getAttribute('data-maxlength') || '', 10) || null);
    let options = null;
    let hasValue;
    let value;
    if (kind === 'select' || kind === 'multiselect') {
      options = [...el.options].map((o) => ({ value: o.value, text: clean(o.text) }));
      hasValue = [...el.selectedOptions].some((o) => o.value !== '' && clean(o.text) !== '');
      value = [...el.selectedOptions].map((o) => clean(o.text)).filter(Boolean).join('; ');
    } else if (kind === 'checkbox') {
      hasValue = el.checked;
      value = el.checked;
    } else if (kind === 'richtext') {
      hasValue = textOf(el) !== '';
      value = textOf(el);
    } else {
      hasValue = (el.value || '') !== '';
      value = kind === 'file' || kind === 'password' ? '' : el.value;
    }
    fields.push({
      kind, label: labelOf(el), name: el.getAttribute('name') || '', id: el.id, selector: selectorOf(el),
      required: required(el), maxlength, options, has_value: hasValue, ...common(el),
      ...(includeValues ? { value } : {}),
    });
  }

  // "Add Employment", "Add Another", "+ Add" style links and buttons that open popups or new blocks.
  const addControls = [...document.querySelectorAll('a, button, [role=button], input[type=button]')]
    .map((el) => ({ el, text: textOf(el) || clean(el.value) }))
    .filter(({ text }) => /^(\+\s*)?add\b/i.test(text) && text.length < 60)
    .map(({ el, text }) => {
      const table = el.closest('table');
      return {
        text, selector: selectorOf(el), visible: visible(el), section: sectionOf(el), in_dialog: !!dialogOf(el),
        table_columns: table ? [...table.querySelectorAll('th')].map(textOf).filter(Boolean) : [],
        table_rows: table ? [...table.querySelectorAll('tbody > tr')].filter(visible).length : 0,
      };
    });

  const dialogs = [...document.querySelectorAll('[role=dialog], dialog, .ui-dialog')]
    .filter(visible)
    .map((d) => clean(d.getAttribute('aria-label')) || textOf(d.querySelector('h1, h2, h3, .ui-dialog-title')) || '(untitled)');

  // Lists of saved entries (jobs, awards, ...) are tables; their cells are the only place those values show.
  const tables = includeValues ? [...document.querySelectorAll('table')].filter(visible).map((t) => ({
    section: sectionOf(t),
    columns: [...t.querySelectorAll('th')].map(textOf),
    rows: [...t.querySelectorAll('tbody > tr')].filter(visible).map((r) => [...r.children].map(textOf)),
  })).filter((t) => t.rows.length) : [];
  const text = includeValues ? textOf(document.body) : undefined;

  return { title: document.title, fields, add_controls: addControls, open_dialogs: dialogs, tables, text };
}
"""


def describe_frames(page, include_values=False):
    frames = []
    for index, frame in enumerate(page.frames):
        try:
            described = frame.evaluate(DESCRIBE_FRAME_JS, include_values)
        except Exception as error:
            frames.append({"index": index, "name": frame.name, "url": frame.url, "error": str(error)})
            continue
        if index and not described["fields"] and not described["add_controls"]:
            continue
        frames.append({"index": index, "name": frame.name, "url": frame.url, **described})
    return frames


def summarize(inventory):
    for frame in inventory["frames"]:
        fields = frame.get("fields", [])
        where = "main page" if frame["index"] == 0 else f"iframe {frame['name'] or frame['url'][:60]}"
        if "error" in frame:
            print(f"{where}: could not read ({frame['error'][:80]})")
            continue
        kinds = Counter(field["kind"] for field in fields)
        shown = sum(field["visible"] for field in fields)
        print(f"{where}: {len(fields)} fields ({shown} visible, {sum(f['required'] for f in fields)} required) "
              f"{dict(kinds)}")
        unlabeled = [field["selector"] for field in fields if field["visible"] and not field["label"]]
        if unlabeled:
            print(f"  visible fields with no label: {len(unlabeled)}")
        for control in frame.get("add_controls", []):
            if control["visible"]:
                print(f"  add control: {control['text']!r} (section {control['section']!r}, "
                      f"list columns {control['table_columns']}, {control['table_rows']} rows)")
        for title in frame.get("open_dialogs", []):
            print(f"  open popup: {title!r}")


def run(args):
    out_dir = Path(args.inventory_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.school}_{args.page}"
    with attached_page(args.cdp_url, args.url_contains) as page:
        settle(page)
        inventory = {
            "school": args.school,
            "page": args.page,
            "url": page.url,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "frames": describe_frames(page),
        }
        if args.snapshot:
            (out_dir / f"{stem}.html").write_text(page.content())
            page.screenshot(path=out_dir / f"{stem}.png", full_page=True)
    path = out_dir / f"{stem}.json"
    if path.exists():
        # Keep the earlier capture; portals change their forms mid-cycle.
        previous = out_dir / f"{stem}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.rename(previous)
        print(f"earlier inventory kept as {previous}")
    path.write_text(json.dumps(inventory, indent=2))
    summarize(inventory)
    print(f"wrote {path}")
