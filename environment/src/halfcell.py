"""JSON entry point for the open negative-half-cell response task."""

import json
import sys


def main():
    # The response kernel is intentionally absent from the starter.
    sys.stdin.read()
    json.dump({"error": "not_implemented"}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
