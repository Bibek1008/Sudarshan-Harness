from taskman.cli import CLI
import sys


def main():
    return CLI().run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
