"""
Session persistence for web authentication.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from local_store import get_local_store


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionService:
    """Manages auth sessions in JSON file."""

    FILE_NAME = "web_sessions.json"

    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            project_root = Path(__file__).resolve().parents[3]
            file_path = project_root / "data" / self.FILE_NAME
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = get_local_store(data_dir=self.file_path.parent)
        self._ensure_file()

    def _ensure_file(self) -> None:
        data = self.store.load_json(self.FILE_NAME, default_content=[])
        if not isinstance(data, list):
            self._save_sessions([])

    def _load_sessions(self) -> list[dict]:
        data = self.store.load_json(self.FILE_NAME, default_content=[])
        return data if isinstance(data, list) else []

    def _save_sessions(self, sessions: list[dict]) -> None:
        self.store.save_json(self.FILE_NAME, sessions)

    def create_session(
        self,
        *,
        session_id: str,
        user_id: int,
        username: str,
        role: str,
        ip_address: str,
        user_agent: str,
        expires_at: str,
    ) -> dict:
        sessions = self._load_sessions()
        now = _utc_now_iso()
        item = {
            "session_id": session_id,
            "user_id": int(user_id),
            "username": username,
            "role": role,
            "ip_address": ip_address or "",
            "user_agent": user_agent or "",
            "created_at": now,
            "last_seen_at": now,
            "expires_at": expires_at,
            "is_active": True,
        }
        sessions.append(item)
        self._save_sessions(sessions)
        return item

    def touch_session(self, session_id: str) -> None:
        sessions = self._load_sessions()
        changed = False
        for session in sessions:
            if session.get("session_id") == session_id and bool(session.get("is_active", True)):
                session["last_seen_at"] = _utc_now_iso()
                changed = True
                break
        if changed:
            self._save_sessions(sessions)

    def is_session_active(self, session_id: Optional[str]) -> bool:
        if not session_id:
            return True
        for session in self._load_sessions():
            if session.get("session_id") != session_id:
                continue
            return bool(session.get("is_active", True))
        return False

    def close_session(self, session_id: Optional[str]) -> None:
        if not session_id:
            return
        sessions = self._load_sessions()
        changed = False
        for session in sessions:
            if session.get("session_id") == session_id and bool(session.get("is_active", True)):
                session["is_active"] = False
                session["last_seen_at"] = _utc_now_iso()
                changed = True
                break
        if changed:
            self._save_sessions(sessions)

    def close_session_by_id(self, session_id: str) -> bool:
        sessions = self._load_sessions()
        changed = False
        for session in sessions:
            if session.get("session_id") == session_id and bool(session.get("is_active", True)):
                session["is_active"] = False
                session["last_seen_at"] = _utc_now_iso()
                changed = True
                break
        if changed:
            self._save_sessions(sessions)
        return changed

    def list_sessions(self, *, active_only: bool = False) -> list[dict]:
        sessions = self._load_sessions()
        if active_only:
            sessions = [s for s in sessions if bool(s.get("is_active", True))]
        return sorted(sessions, key=lambda x: x.get("last_seen_at", ""), reverse=True)


session_service = SessionService()
