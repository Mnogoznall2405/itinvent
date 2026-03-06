"""
Per-user UI/database settings storage.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from local_store import get_local_store


class SettingsService:
    """Persist user settings in JSON."""

    FILE_NAME = "web_user_settings.json"
    DEFAULTS = {
        "pinned_database": None,
        "theme_mode": "light",
        "font_family": "Inter",
        "font_scale": 1.0,
    }

    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            project_root = Path(__file__).resolve().parents[3]
            file_path = project_root / "data" / self.FILE_NAME
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = get_local_store(data_dir=self.file_path.parent)
        self._ensure_file()

    def _ensure_file(self) -> None:
        data = self.store.load_json(self.FILE_NAME, default_content={})
        if not isinstance(data, dict):
            self._save_all({})

    def _load_all(self) -> dict[str, dict]:
        data = self.store.load_json(self.FILE_NAME, default_content={})
        return data if isinstance(data, dict) else {}

    def _save_all(self, data: dict[str, dict]) -> None:
        self.store.save_json(self.FILE_NAME, data)

    def get_user_settings(self, user_id: int) -> dict:
        data = self._load_all()
        raw = data.get(str(int(user_id))) or {}
        settings = {**self.DEFAULTS, **raw}
        if settings["theme_mode"] not in {"light", "dark"}:
            settings["theme_mode"] = "light"
        if settings["font_family"] not in {"Inter", "Roboto", "Segoe UI"}:
            settings["font_family"] = "Inter"
        try:
            scale = float(settings.get("font_scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        settings["font_scale"] = max(0.9, min(1.2, scale))
        return settings

    def update_user_settings(self, user_id: int, patch: dict) -> dict:
        data = self._load_all()
        key = str(int(user_id))
        current = self.get_user_settings(user_id)

        if "pinned_database" in patch:
            value = patch.get("pinned_database")
            current["pinned_database"] = str(value).strip() if value not in (None, "") else None
        if "theme_mode" in patch and str(patch.get("theme_mode")) in {"light", "dark"}:
            current["theme_mode"] = str(patch.get("theme_mode"))
        if "font_family" in patch and str(patch.get("font_family")) in {"Inter", "Roboto", "Segoe UI"}:
            current["font_family"] = str(patch.get("font_family"))
        if "font_scale" in patch:
            try:
                scale = float(patch.get("font_scale"))
                current["font_scale"] = max(0.9, min(1.2, scale))
            except (TypeError, ValueError):
                pass

        data[key] = current
        self._save_all(data)
        return current


settings_service = SettingsService()
