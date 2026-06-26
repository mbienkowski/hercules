import sys

if sys.version_info < (3, 9):
    print(
        f"Hercules requires Python 3.9 or later. "  # pragma: no mutate
        f"You have Python {sys.version_info.major}.{sys.version_info.minor}.\n"  # pragma: no mutate
        "Most systems already ship 3.9+ (incl. macOS 12+); upgrade via your package manager if older.",  # pragma: no mutate
        file=sys.stderr,
    )
    sys.exit(1)

from hercules.cli import main

main()
