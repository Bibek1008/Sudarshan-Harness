"""Day 4: module entry point that defers command-line behavior to the CLI.

Keeping this bridge minimal lets Day 5 evolve argument handling without adding
another package surface or coupling the harness to a specific invocation mode.
"""

from .cli import main


if __name__ == "__main__":
    main()
