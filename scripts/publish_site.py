import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish rendered report into site pipeline.")
    parser.add_argument("--rendered", required=True, help="Rendered report JSON path")
    args = parser.parse_args()

    rendered = Path(args.rendered)
    if not rendered.exists():
        raise FileNotFoundError(f"Rendered payload not found: {rendered}")

    # Placeholder: connect this script to existing git + web update steps.
    print(f"publish placeholder: {rendered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
