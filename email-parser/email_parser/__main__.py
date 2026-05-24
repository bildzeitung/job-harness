import json
import sys

from .parser import filter_by_seniority, parse


def main() -> None:
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        with open(sys.argv[1]) as f:
            html = f.read()
    else:
        html = sys.stdin.read()

    jobs = parse(html)

    if "--no-filter" not in sys.argv:
        jobs = filter_by_seniority(jobs)

    print(json.dumps(jobs))


if __name__ == "__main__":
    main()
