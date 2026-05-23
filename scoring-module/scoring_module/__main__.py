import sys
from .scorer import score_batch


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scoring_module <batch_file> [batch_file2 ...]", file=sys.stderr)
        sys.exit(1)
    total = 0
    for batch_file in sys.argv[1:]:
        total += score_batch(batch_file)
    sys.exit(0 if total >= 0 else 1)


if __name__ == "__main__":
    main()
