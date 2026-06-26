import sys

if sys.version_info < (3, 11):
    print(
        f"Hercules requires Python 3.11 or later. "  # pragma: no mutate
        f"You have Python {sys.version_info.major}.{sys.version_info.minor}.\n"  # pragma: no mutate
        "macOS Monterey (12) ships Python 3.9 — upgrade via Homebrew: brew install python@3.11",  # pragma: no mutate
        file=sys.stderr,
    )
    sys.exit(1)

from hercules.cli import main

main()
