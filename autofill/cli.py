# Command line: autofill discover | extract | map | fill
# Created: 2026-11-26  Last modified: 2026-11-27
import argparse

from autofill import discover, extract
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

    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
