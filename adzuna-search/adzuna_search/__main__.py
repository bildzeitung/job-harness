import json
import sys

from .search import search


def main() -> None:
    # Optional: pass custom queries as positional args; default queries used if none given
    queries = sys.argv[1:] or None
    results = search(queries=queries)
    print(json.dumps(results))


if __name__ == "__main__":
    main()
