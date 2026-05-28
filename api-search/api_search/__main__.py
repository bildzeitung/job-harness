import sys

from api_search.core import run, write_output
from api_search.sources import SOURCES, usage


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in SOURCES:
        print(usage(), file=sys.stderr)
        return 2

    source = argv[0]
    results = run(source)
    path = write_output(source, results)
    print(
        f"[API-SEARCH:{source.upper()}] Found {len(results)} postings — saved to {path}", flush=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
