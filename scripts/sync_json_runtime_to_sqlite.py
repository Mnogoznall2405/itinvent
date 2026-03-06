#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Синхронизация runtime JSON-файлов в SQLite с последующей архивацией JSON.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_store import get_local_store


RUNTIME_JSON_FILES = [
    "unfound_equipment.json",
    "equipment_transfers.json",
    "cartridge_replacements.json",
    "battery_replacements.json",
    "pc_cleanings.json",
    "component_replacements.json",
    "equipment_installations.json",
    "user_db_selection.json",
    "export_state.json",
    "web_users.json",
    "web_sessions.json",
    "web_user_settings.json",
    "cartridge_database.json",
    "printer_component_cache.json",
    "printer_color_cache.json",
]


def _safe_move(src: Path, dest_dir: Path) -> Path:
    dest = dest_dir / src.name
    if dest.exists():
        stamp = datetime.now().strftime("%H%M%S")
        dest = dest_dir / f"{src.stem}_{stamp}{src.suffix}"
    return Path(shutil.move(str(src), str(dest)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync runtime JSON files into SQLite and archive JSON files")
    parser.add_argument(
        "--conflict-policy",
        choices=["keep_sqlite", "update_from_json"],
        default="keep_sqlite",
        help="Conflict policy during merge",
    )
    parser.add_argument(
        "--keep-json",
        action="store_true",
        help="Do not archive/delete JSON files after successful merge",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned actions without changes",
    )
    args = parser.parse_args()

    data_dir = REPO_ROOT / "data"
    store = get_local_store(data_dir=data_dir)

    files_to_sync = [name for name in RUNTIME_JSON_FILES if (data_dir / name).exists()]
    if not files_to_sync:
        print("Нет runtime JSON-файлов для синхронизации.")
        return 0

    print("Файлы для синхронизации:")
    for item in files_to_sync:
        print(f"- {item}")

    if args.dry_run:
        print("DRY-RUN: миграция и архивирование не выполнялись.")
        return 0

    results = store.migrate_json_files(
        merge=True,
        overwrite=False,
        conflict_policy=args.conflict_policy,
        files=files_to_sync,
    )

    errors = [row for row in results if row.status == "error"]
    print("\nРезультат merge:")
    for row in results:
        print(f"{row.file_name:30} {row.status:16} rows={row.rows} note={row.note}")

    if errors:
        print("\nОбнаружены ошибки миграции. Архивирование JSON отменено.")
        return 1

    if args.keep_json:
        print("\nСинхронизация завершена. JSON-файлы оставлены по флагу --keep-json.")
        return 0

    archive_root = REPO_ROOT / "backups" / "json_imported"
    archive_dir = archive_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir.mkdir(parents=True, exist_ok=True)

    moved: list[Path] = []
    for name in files_to_sync:
        src = data_dir / name
        if not src.exists():
            continue
        moved.append(_safe_move(src, archive_dir))

    print(f"\nJSON-файлы архивированы в: {archive_dir}")
    for item in moved:
        print(f"- {item.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
