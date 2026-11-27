# Attach to a Chrome the user already started with --remote-debugging-port, and pick the tab to work on.
# Created: 2026-11-26  Last modified: 2026-11-26
import contextlib

from playwright.sync_api import sync_playwright

DEFAULT_CDP_URL = "http://localhost:9222"


def pick_page(browser, url_contains=None):
    pages = [page for context in browser.contexts for page in context.pages
             if page.url.startswith(("http", "file"))]
    if url_contains:
        pages = [page for page in pages if url_contains in page.url]
    if len(pages) > 1:
        # Background tabs report "hidden"; the tab in front of each window reports "visible".
        front = [page for page in pages if page.evaluate("document.visibilityState") == "visible"]
        pages = front or pages
    if not pages:
        raise SystemExit("no matching tab; open the portal page in the debugging Chrome first")
    if len(pages) == 1:
        return pages[0]
    for number, page in enumerate(pages, 1):
        print(f"  {number}. {page.title()[:60]}  {page.url[:80]}")
    choice = input("Which tab? ").strip()
    return pages[int(choice) - 1]


@contextlib.contextmanager
def attached_page(cdp_url=DEFAULT_CDP_URL, url_contains=None):
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.connect_over_cdp(cdp_url)
        except Exception as error:
            raise SystemExit(f"could not reach Chrome at {cdp_url}; start it with --remote-debugging-port ({error})")
        # Leaving the block only disconnects; Chrome and its tabs stay open.
        yield pick_page(browser, url_contains)


def settle(page, timeout_ms=10000):
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
