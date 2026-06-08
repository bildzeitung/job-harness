import json
import os
import sys

from api_search.core import append_postings, inspect_batch, run, write_output
from api_search.sources import SOURCES, usage


def _usage() -> str:
    return (
        f"{usage()}\n"
        "  or: python -m api_search append <platform> [--from FILE] [--date YYYY-MM-DD]\n"
        "      merge a JSON batch (array of consolidator-schema postings, or an\n"
        "      object with a 'postings' key) from FILE or stdin into\n"
        "      $JOB_DATA_ROOT/jobs/<platform>-<date>.json, deduped by URL.\n"
        "  or: python -m api_search inspect FILE\n"
        "      print the shape, posting count, and per-field coverage of a\n"
        "      jobs/<platform>-<date>.json file (no hand-rolled json one-liners)."
    )


def _inspect(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_usage(), file=sys.stderr)
        return 2
    path = argv[1]
    try:
        info = inspect_batch(path)
    except OSError as e:
        print(f"[API-SEARCH:INSPECT] cannot read {path}: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"[API-SEARCH:INSPECT] invalid JSON in {path}: {e}", file=sys.stderr)
        return 1

    meta = " ".join(f"{k}={v}" for k, v in info["meta"].items())
    print(f"[API-SEARCH:INSPECT] {path}")
    print(f"  shape: {info['shape']}" + (f"  {meta}" if meta else ""))
    print(f"  postings: {info['count']}")
    if info["fields"]:
        print("  field coverage (non-empty / total):")
        width = max(len(k) for k in info["fields"])
        for key, present in info["fields"].items():
            print(f"    {key.ljust(width)}  {present}/{info['count']}")
    return 0


def _append(argv: list[str]) -> int:
    if len(argv) < 2:
        print(_usage(), file=sys.stderr)
        return 2
    platform = argv[1]
    from_file: str | None = None
    batch_date: str | None = None
    rest = argv[2:]
    i = 0
    while i < len(rest):
        if rest[i] == "--from" and i + 1 < len(rest):
            from_file = rest[i + 1]
            i += 2
        elif rest[i] == "--date" and i + 1 < len(rest):
            batch_date = rest[i + 1]
            i += 2
        else:
            print(_usage(), file=sys.stderr)
            return 2

    if from_file:
        try:
            with open(from_file) as f:
                raw = f.read()
        except OSError as e:
            print(f"[API-SEARCH:APPEND] cannot read batch file {from_file}: {e}", file=sys.stderr)
            return 1
    else:
        raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[API-SEARCH:APPEND] invalid JSON batch: {e}", file=sys.stderr)
        return 1
    postings = data.get("postings", []) if isinstance(data, dict) else data
    if not isinstance(postings, list):
        print("[API-SEARCH:APPEND] batch must be a list or {'postings': [...]}", file=sys.stderr)
        return 1

    result = append_postings(platform, postings, batch_date=batch_date)

    # The batch file is a transient staging artifact — consume it on success so
    # it never lingers in jobs/ alongside the canonical {platform}-{date}.json.
    if from_file and os.path.abspath(from_file) != os.path.abspath(result["path"]):
        try:
            os.remove(from_file)
        except OSError:
            pass

    print(
        f"[API-SEARCH:APPEND:{platform.upper()}] +{result['added']} new "
        f"({result['skipped']} dup/blank) — {result['total']} total in {result['path']}",
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "append":
        return _append(argv)
    if argv and argv[0] == "inspect":
        return _inspect(argv)
    if not argv or argv[0] not in SOURCES:
        print(_usage(), file=sys.stderr)
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
