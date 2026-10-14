"""Command-line interface for flicker."""

import sys


def main(argv=None) -> int:
    """Entry point for flicker CLI."""
    if argv is None:
        argv = sys.argv[1:]

    # For now, just print a placeholder message.
    # In the future, this will be replaced with actual functionality.
    print("Flicker CLI: recording terminal sessions to MP4/WebM")
    print("Use --help for more information.")
    return 0


if __name__ == "__main__":
    sys.exit(main())