#!/usr/bin/env python3
"""
Remove ephemeral files under the skill root after a task run (disk space).
Safe defaults: never deletes scripts/, SKILL.md, seed_urls.json, or whitelist active sources.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def rm_path(p: Path, dry_run: bool) -> None:
    if not p.exists():
        return
    if dry_run:
        print(f"[dry-run] would remove: {p}")
        return
    if p.is_dir():
        shutil.rmtree(p)
        print(f"[ok] removed dir: {p}")
    else:
        p.unlink()
        print(f"[ok] removed file: {p}")


def prune_whitelist_history(whitelist_path: Path, dry_run: bool) -> None:
    if not whitelist_path.exists():
        print(f"[skip] no whitelist at {whitelist_path}")
        return
    text = whitelist_path.read_text(encoding="utf-8")
    data = json.loads(text)
    hist = data.get("history")
    if not isinstance(hist, dict):
        return
    before = len(hist.get("test_log") or []) + len(hist.get("removed") or [])
    if before == 0:
        print("[skip] whitelist history already empty")
        return
    if dry_run:
        print(f"[dry-run] would clear history.test_log and history.removed ({before} entries total)")
        return
    hist["test_log"] = []
    hist["removed"] = []
    data["history"] = hist
    whitelist_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] pruned whitelist history ({before} entries removed from log lists)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean ephemeral skill workspace files.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without deleting.",
    )
    parser.add_argument(
        "--prune-whitelist-history",
        action="store_true",
        help="Clear history.test_log and history.removed in config/whitelist.json (keeps active sources).",
    )
    args = parser.parse_args()
    root = skill_root()
    dry = args.dry_run

    # Default crawler output name
    rm_path(root / "report_payload.json", dry)

    # Optional run directory (recommended in SKILL.md)
    runs = root / "runs"
    if runs.is_dir():
        if dry:
            for child in runs.iterdir():
                print(f"[dry-run] would remove: {child}")
        else:
            for child in list(runs.iterdir()):
                rm_path(child, dry=False)
            try:
                runs.rmdir()
                print(f"[ok] removed empty dir: {runs}")
            except OSError:
                print(f"[info] runs/ not empty or in use, left in place: {runs}")

    # OpenClaw / runtime cache often under skill copy
    rm_path(root / ".openclaw", dry)

    # Python bytecode caches under this package
    for sub in ("tools", "tools/core", "scripts"):
        pyc = root / sub / "__pycache__"
        rm_path(pyc, dry)

    # Loose payload-like JSON in skill root only (not config/)
    for name in ("gold_price_report.json", "badminton_price_report.json"):
        rm_path(root / name, dry)

    if args.prune_whitelist_history:
        prune_whitelist_history(root / "config" / "whitelist.json", dry)

    print("[done] skill_cleanup finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
