# Command line: autofill discover | extract | map | fill
# Created: 2026-11-26  Last modified: 2026-11-27
import argparse

from autofill import discover, extract, fill
from autofill.browser import DEFAULT_CDP_URL


def main(argv=None):
    parser = argparse.ArgumentParser(prog="autofill")
    commands = parser.add_subparsers(dest="command", required=True)

    discover_parser = commands.add_parser("discover", help="list the fields on the open portal page")
    discover_parser.add_argument("--school", required=True)
    discover_parser.add_argument("--page", required=True, help="short name for this page, e.g. experience")
    discover_parser.add_argument("--inventory-dir", default="private/inventory")
    discover_parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    discover_parser.add_argument("--url-contains", help="pick the tab whose URL contains this text")
    discover_parser.add_argument("--no-snapshot", dest="snapshot", action="store_false",
                                 help="skip saving the page HTML and screenshot next to the inventory")
    discover_parser.set_defaults(handler=discover.run)

    extract_parser = commands.add_parser("extract", help="read the values on a finished application page")
    extract_parser.add_argument("--school", required=True)
    extract_parser.add_argument("--page", help="file name for this page; defaults to the page heading")
    extract_parser.add_argument("--url", help="open this URL in the tab first")
    extract_parser.add_argument("--out-dir", default="private/extracted")
    extract_parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    extract_parser.add_argument("--url-contains", help="pick the tab whose URL contains this text")
    extract_parser.set_defaults(handler=extract.run)

    fill_parser = commands.add_parser("fill", help="fill the mapped fields of one page from the profile")
    fill_parser.add_argument("--school", required=True)
    fill_parser.add_argument("--page", required=True)
    fill_parser.add_argument("--profile", default="private/profile.yaml")
    fill_parser.add_argument("--mapping-dir", default="private/mappings")
    fill_parser.add_argument("--report-dir", default="private/fill_reports")
    fill_parser.add_argument("--dry-run", action="store_true", help="print what would be filled; change nothing")
    fill_parser.add_argument("--overwrite", action="store_true", help="replace values already in a field")
    fill_parser.add_argument("--save", action="store_true",
                             help="click Save in each completed popup; without it the first popup stays open for review")
    fill_parser.add_argument("--limit", type=int, help="add at most this many list entries per section")
    fill_parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    fill_parser.add_argument("--url-contains")
    fill_parser.set_defaults(handler=fill.run)

    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
