# Open a visible browser, let the user log in and open the add-course popup, then record its structure.
# Read-only: fills nothing, clicks nothing.
# Created: 2026-10-24  Last modified: 2026-10-24
import argparse
import json
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

DESCRIBE_FIELDS_JS = """
(root) => {
  const labelFor = (el) => {
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) return lab.innerText.trim();
    }
    const wrap = el.closest('label');
    if (wrap) return wrap.innerText.trim();
    const row = el.closest('.form_question, .form_q, tr, .row, div');
    const lab = row && row.querySelector('label, .form_label, th');
    return lab ? lab.innerText.trim() : '';
  };
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  return [...root.querySelectorAll('input, select, textarea, button, a[role=button], [contenteditable=true]')]
    .map((el) => ({
      tag: el.tagName.toLowerCase(),
      type: el.type || '',
      id: el.id,
      name: el.getAttribute('name') || '',
      label: labelFor(el),
      aria_label: el.getAttribute('aria-label') || '',
      placeholder: el.getAttribute('placeholder') || '',
      text: el.tagName === 'SELECT' ? '' : (el.innerText || el.value || '').trim().slice(0, 80),
      required: el.required || el.getAttribute('aria-required') === 'true',
      visible: visible(el),
      options: el.tagName === 'SELECT'
        ? [...el.options].map((o) => ({ value: o.value, text: o.text.trim() })).slice(0, 400)
        : undefined,
    }));
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="private/config.json")
    parser.add_argument("--url", help="overrides form_url in the config")
    parser.add_argument("--profile", default="private/browser_profile")
    parser.add_argument("--out-dir", default="private/form_inspection")
    parser.add_argument("--dialog-title", help="only capture a popup whose text contains this title")
    args = parser.parse_args()
    url = args.url or json.loads(Path(args.config).read_text())["form_url"]

    out_dir = Path(args.out_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(args.profile, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url)

        input("\nLog in, go to the page listing your courses, and press Enter here (do not open the add-course popup yet)... ")
        page.screenshot(path=out_dir / "courses_page.png", full_page=True)
        (out_dir / "courses_page.html").write_text(page.content())
        (out_dir / "courses_page_fields.json").write_text(
            json.dumps(page.evaluate(DESCRIBE_FIELDS_JS, page.locator("body").element_handle()), indent=2)
        )

        input("Now open the add-course popup, leave it empty, and press Enter... ")
        dialogs = page.get_by_role("dialog")
        if args.dialog_title:
            dialogs = dialogs.filter(has_text=args.dialog_title)
        visible_dialogs = [dialog for dialog in dialogs.all() if dialog.is_visible()]
        if not visible_dialogs:
            raise SystemExit("no visible popup with role=dialog found; the course form may be inline on the page, "
                             "which courses_page.html already captured")
        dialog = visible_dialogs[-1]
        print(f"captured popup: {dialog.get_attribute('aria-label') or '(no aria-label)'}")
        dialog.screenshot(path=out_dir / "modal.png")
        (out_dir / "modal.html").write_text(dialog.evaluate("el => el.outerHTML"))
        (out_dir / "modal_fields.json").write_text(
            json.dumps(page.evaluate(DESCRIBE_FIELDS_JS, dialog.element_handle()), indent=2)
        )
        # Frames matter: Slate sometimes renders dialogs inside an iframe.
        (out_dir / "frames.json").write_text(json.dumps([frame.url for frame in page.frames], indent=2))

        print(f"saved inspection to {out_dir}")
        input("Close the popup yourself (Cancel), then press Enter to close the browser... ")
        context.close()


if __name__ == "__main__":
    main()
