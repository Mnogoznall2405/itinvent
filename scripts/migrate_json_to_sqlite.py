#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One-time/recurring migration from data/*.json to data/local_store.db.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_store import get_local_store


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate JSON files in data/ into SQLite local_store.db")
    parser.add_argument(
        "--mode",
        choices=["merge", "overwrite", "skip-existing"],
        default="merge",
        help="Migration mode: merge(new rows only), overwrite(full replace), skip-existing(import only empty targets)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Alias for --mode overwrite",
    )
    parser.add_argument(
        "--conflict-policy",
        choices=["keep_sqlite", "update_from_json"],
        default="keep_sqlite",
        help="Conflict policy for merge mode",
    )
    args = parser.parse_args()

    mode = args.mode
    if args.overwrite:
        mode = "overwrite"

    data_dir = REPO_ROOT / "data"
    store = get_local_store(data_dir=data_dir)
    results = store.migrate_json_files(
        overwrite=(mode == "overwrite"),
        merge=(mode == "merge"),
        conflict_policy=args.conflict_policy,
    )

    imported = 0
    merged = 0
    skipped = 0
    skipped_duplicate = 0
    skipped_conflict = 0
    errors = 0
    print(f"JSON -> SQLite migration report (mode={mode}, conflict_policy={args.conflict_policy})")
    print("=" * 40)
    for row in results:
        print(f"{row.file_name:30} {row.status:16} rows={row.rows} note={row.note}")
        if row.status == "imported":
            imported += 1
        elif row.status == "merged":
            merged += 1
        elif row.status.startswith("skipped"):
            skipped += 1
            note = row.note or ""
            for part in note.split(";"):
                key, _, value = part.partition("=")
                key = key.strip()
                value = value.strip()
                if key == "skipped_duplicate" and value.isdigit():
                    skipped_duplicate += int(value)
                elif key == "skipped_conflict" and value.isdigit():
                    skipped_conflict += int(value)
        else:
            errors += 1
    print("=" * 40)
    print(
        f"imported={imported} merged={merged} skipped={skipped} "
        f"skipped_duplicate={skipped_duplicate} skipped_conflict={skipped_conflict} errors={errors}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
