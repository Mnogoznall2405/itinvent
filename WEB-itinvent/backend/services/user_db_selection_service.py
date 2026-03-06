"""
User database assignment service.

Reads Telegram user -> database mapping from shared bot file:
data/user_db_selection.json
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from local_store import get_local_store


class UserDBSelectionService:
    """Service to resolve assigned SQL database by Telegram ID."""

    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            project_root = Path(__file__).resolve().parents[3]
            file_path = project_root / "data" / "user_db_selection.json"
        self.file_path = file_path
        self.store = get_local_store(data_dir=self.file_path.parent)

    def _read_mapping(self) -> dict[str, str]:
        data = self.store.load_json("user_db_selection.json", default_content={})
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v).strip() for k, v in data.items() if str(v).strip()}

    def _write_mapping(self, mapping: dict[str, str]) -> None:
        self.store.save_json("user_db_selection.json", mapping)

    def get_assigned_database(self, telegram_id: Optional[int]) -> Optional[str]:
        """Return assigned DB ID for Telegram user or None."""
        if telegram_id in (None, 0):
            return None
        mapping = self._read_mapping()
        return mapping.get(str(int(telegram_id)))

    def set_assigned_database(self, telegram_id: Optional[int], database_id: Optional[str]) -> None:
        """Upsert or remove assigned DB for Telegram user."""
        if telegram_id in (None, 0):
            return
        key = str(int(telegram_id))
        mapping = self._read_mapping()
        normalized_db = str(database_id or "").strip()
        if normalized_db:
            mapping[key] = normalized_db
        else:
            mapping.pop(key, None)
        self._write_mapping(mapping)


user_db_selection_service = UserDBSelectionService()
