"""
Web users service backed by JSON storage.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import logging

import ldap3

from local_store import get_local_store
from backend.config import config
from backend.services.authorization_service import authorization_service
from backend.services.secret_crypto_service import SecretCryptoError, encrypt_secret

_UNSET = object()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserService:
    """CRUD/authentication operations for web users."""

    FILE_NAME = "web_users.json"
    PBKDF2_ITERATIONS = 120_000

    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            project_root = Path(__file__).resolve().parents[3]
            file_path = project_root / "data" / self.FILE_NAME
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = get_local_store(data_dir=self.file_path.parent)
        self._ensure_defaults()

    @staticmethod
    def _normalize_username(username: str) -> str:
        return str(username or "").strip().lower()

    def _load_users(self) -> list[dict]:
        data = self.store.load_json(self.FILE_NAME, default_content=[])
        return data if isinstance(data, list) else []

    def _save_users(self, users: list[dict]) -> None:
        self.store.save_json(self.FILE_NAME, users)

    @classmethod
    def _hash_password(cls, password: str, salt_b64: Optional[str] = None) -> tuple[str, str]:
        salt = base64.b64decode(salt_b64) if salt_b64 else secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, cls.PBKDF2_ITERATIONS)
        return base64.b64encode(digest).decode("ascii"), base64.b64encode(salt).decode("ascii")

    @classmethod
    def _verify_password(cls, password: str, password_hash_b64: str, salt_b64: str) -> bool:
        digest_b64, _ = cls._hash_password(password, salt_b64=salt_b64)
        return hmac.compare_digest(digest_b64, password_hash_b64)

    @staticmethod
    def _sanitize_user(user: dict) -> dict:
        custom_permissions = authorization_service.normalize_permissions(user.get("custom_permissions"))
        use_custom_permissions = bool(user.get("use_custom_permissions", False))
        mailbox_email = (str(user.get("mailbox_email") or "").strip() or None)
        mailbox_login = (str(user.get("mailbox_login") or "").strip() or None)
        mail_signature_html = (str(user.get("mail_signature_html") or "").strip() or None)
        mailbox_password_enc = str(user.get("mailbox_password_enc") or "").strip()
        return {
            "id": int(user["id"]),
            "username": str(user["username"]),
            "email": user.get("email"),
            "full_name": user.get("full_name"),
            "is_active": bool(user.get("is_active", True)),
            "role": str(user.get("role") or "viewer"),
            "use_custom_permissions": use_custom_permissions,
            "custom_permissions": custom_permissions,
            "auth_source": str(user.get("auth_source") or "local"),
            "telegram_id": user.get("telegram_id"),
            "assigned_database": (str(user.get("assigned_database") or "").strip() or None),
            "mailbox_email": mailbox_email,
            "mailbox_login": mailbox_login,
            "mail_signature_html": mail_signature_html,
            "mail_is_configured": bool(mailbox_email and mailbox_login and mailbox_password_enc),
        }

    def to_public_user(self, user: dict) -> dict:
        """Return safe user representation without password fields."""
        return self._sanitize_user(user)

    def _ensure_defaults(self) -> None:
        users = self._load_users()
        if users:
            return

        now = _utc_now_iso()
        defaults = [
            {
                "id": 1,
                "username": "admin",
                "email": "admin@itinvent.ru",
                "full_name": "Administrator",
                "is_active": True,
                "role": "admin",
                "use_custom_permissions": False,
                "custom_permissions": [],
                "telegram_id": None,
                "assigned_database": None,
                "mailbox_email": None,
                "mailbox_login": None,
                "mailbox_password_enc": "",
                "mail_signature_html": None,
                "mail_updated_at": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": 2,
                "username": "user",
                "email": "user@itinvent.ru",
                "full_name": "Regular User",
                "is_active": True,
                "role": "operator",
                "use_custom_permissions": False,
                "custom_permissions": [],
                "auth_source": "local",
                "telegram_id": None,
                "assigned_database": None,
                "mailbox_email": None,
                "mailbox_login": None,
                "mailbox_password_enc": "",
                "mail_signature_html": None,
                "mail_updated_at": None,
                "created_at": now,
                "updated_at": now,
            },
        ]
        # Для дефолтных админа и юзера прописываем local явно
        defaults[0]["auth_source"] = "local"
        for item, password in ((defaults[0], "admin"), (defaults[1], "user123")):
            password_hash, salt = self._hash_password(password)
            item["password_hash"] = password_hash
            item["password_salt"] = salt
        self._save_users(defaults)

    def get_by_username(self, username: str) -> Optional[dict]:
        normalized = self._normalize_username(username)
        if not normalized:
            return None
        for user in self._load_users():
            if self._normalize_username(user.get("username")) == normalized:
                return user
        return None

    def get_by_id(self, user_id: int) -> Optional[dict]:
        for user in self._load_users():
            if int(user.get("id", 0)) == int(user_id):
                return user
        return None

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        user = self.get_by_username(username)
        if not user:
            return None
        if not bool(user.get("is_active", True)):
            return None
            
        auth_source = user.get("auth_source", "local")
        
        if auth_source == "ldap":
            if not config.app.ldap_server:
                logging.getLogger(__name__).error("LDAP authentication failed: LDAP_SERVER not configured")
                return None
            try:
                domain = config.app.ldap_domain or "zsgp.corp"
                user_principal = f"{username}@{domain}"
                server = ldap3.Server(config.app.ldap_server, get_info=ldap3.ALL)
                # Попытка bind (авторизации) с логином-паролем пользователя
                conn = ldap3.Connection(server, user=user_principal, password=password, auto_bind=True)
                conn.unbind()
                return self._sanitize_user(user)
            except ldap3.core.exceptions.LDAPInvalidCredentialsResult:
                return None
            except Exception as e:
                logging.getLogger(__name__).error(f"LDAP authentication error for {username}: {str(e)}")
                return None
                
        # Если auth_source == local (или отсутствует)
        if not self._verify_password(
            password=password,
            password_hash_b64=str(user.get("password_hash") or ""),
            salt_b64=str(user.get("password_salt") or ""),
        ):
            return None
            
        return self._sanitize_user(user)

    def list_users(self) -> list[dict]:
        users = self._load_users()
        return [self._sanitize_user(user) for user in users]

    def create_user(
        self,
        username: str,
        password: Optional[str] = None,
        role: str = "viewer",
        auth_source: str = "local",
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        telegram_id: Optional[int] = None,
        assigned_database: Optional[str] = None,
        is_active: bool = True,
        use_custom_permissions: bool = False,
        custom_permissions: Optional[list[str]] = None,
        mailbox_email: Optional[str] = None,
        mailbox_login: Optional[str] = None,
        mailbox_password: Optional[str] = None,
        mail_signature_html: Optional[str] = None,
    ) -> dict:
        normalized = self._normalize_username(username)
        if not normalized:
            raise ValueError("Username is required")
        if self.get_by_username(normalized):
            raise ValueError("User already exists")

        users = self._load_users()
        next_id = max([int(u.get("id", 0)) for u in users], default=0) + 1
        if password:
            password_hash, salt = self._hash_password(password)
        else:
            password_hash, salt = "", ""

        mailbox_password_enc = ""
        if str(mailbox_password or "").strip():
            try:
                mailbox_password_enc = encrypt_secret(str(mailbox_password or "").strip())
            except SecretCryptoError as exc:
                raise ValueError(str(exc)) from exc

        now = _utc_now_iso()
        created = {
            "id": next_id,
            "username": normalized,
            "email": email,
            "full_name": full_name,
            "is_active": bool(is_active),
            "role": role if role in {"admin", "operator", "viewer"} else "viewer",
            "use_custom_permissions": bool(use_custom_permissions),
            "custom_permissions": authorization_service.normalize_permissions(custom_permissions),
            "auth_source": auth_source if auth_source in {"local", "ldap"} else "local",
            "telegram_id": int(telegram_id) if telegram_id not in (None, "") else None,
            "assigned_database": (str(assigned_database or "").strip() or None),
            "mailbox_email": (str(mailbox_email or "").strip() or None),
            "mailbox_login": (str(mailbox_login or "").strip() or None),
            "mailbox_password_enc": mailbox_password_enc,
            "mail_signature_html": (str(mail_signature_html or "").strip() or None),
            "mail_updated_at": now if (mailbox_email or mailbox_login or mailbox_password_enc or mail_signature_html) else None,
            "password_hash": password_hash,
            "password_salt": salt,
            "created_at": now,
            "updated_at": now,
        }
        
        users.append(created)
        self._save_users(users)
        if created.get("telegram_id"):
            from .user_db_selection_service import user_db_selection_service
            user_db_selection_service.set_assigned_database(created.get("telegram_id"), created.get("assigned_database"))
        return self._sanitize_user(created)

    def update_user(
        self,
        user_id: int,
        *,
        email: Optional[str] | object = _UNSET,
        full_name: Optional[str] | object = _UNSET,
        role: Optional[str] | object = _UNSET,
        auth_source: Optional[str] | object = _UNSET,
        telegram_id: Optional[int] | object = _UNSET,
        assigned_database: Optional[str] | object = _UNSET,
        is_active: Optional[bool] | object = _UNSET,
        password: Optional[str] | object = _UNSET,
        use_custom_permissions: Optional[bool] | object = _UNSET,
        custom_permissions: Optional[list[str]] | object = _UNSET,
        mailbox_email: Optional[str] | object = _UNSET,
        mailbox_login: Optional[str] | object = _UNSET,
        mailbox_password: Optional[str] | object = _UNSET,
        mail_signature_html: Optional[str] | object = _UNSET,
    ) -> Optional[dict]:
        users = self._load_users()
        updated_user: Optional[dict] = None
        previous_telegram_id: Optional[int] = None
        for user in users:
            if int(user.get("id", 0)) != int(user_id):
                continue
            previous_telegram_id = user.get("telegram_id")
            if email is not _UNSET:
                user["email"] = email
            if full_name is not _UNSET:
                user["full_name"] = full_name
            if role is not _UNSET and role in {"admin", "operator", "viewer"}:
                user["role"] = role
            if auth_source is not _UNSET and auth_source in {"local", "ldap"}:
                user["auth_source"] = auth_source
            if telegram_id is not _UNSET:
                user["telegram_id"] = int(telegram_id) if telegram_id not in (None, "") else None
            if assigned_database is not _UNSET:
                user["assigned_database"] = (str(assigned_database or "").strip() or None)
            if is_active is not _UNSET:
                user["is_active"] = bool(is_active)
            if use_custom_permissions is not _UNSET:
                user["use_custom_permissions"] = bool(use_custom_permissions)
            if custom_permissions is not _UNSET:
                user["custom_permissions"] = authorization_service.normalize_permissions(custom_permissions)
            mail_fields_changed = False
            if mailbox_email is not _UNSET:
                user["mailbox_email"] = (str(mailbox_email or "").strip() or None)
                mail_fields_changed = True
            if mailbox_login is not _UNSET:
                user["mailbox_login"] = (str(mailbox_login or "").strip() or None)
                mail_fields_changed = True
            if mail_signature_html is not _UNSET:
                user["mail_signature_html"] = (str(mail_signature_html or "").strip() or None)
                mail_fields_changed = True
            if mailbox_password is not _UNSET:
                clear_password = not str(mailbox_password or "").strip()
                if clear_password:
                    user["mailbox_password_enc"] = ""
                else:
                    try:
                        user["mailbox_password_enc"] = encrypt_secret(str(mailbox_password or "").strip())
                    except SecretCryptoError as exc:
                        raise ValueError(str(exc)) from exc
                mail_fields_changed = True
            if mail_fields_changed:
                user["mail_updated_at"] = _utc_now_iso()
            if password is not _UNSET and password:
                password_hash, salt = self._hash_password(password)
                user["password_hash"] = password_hash
                user["password_salt"] = salt
            elif auth_source == "ldap":
                user["password_hash"] = ""
                user["password_salt"] = ""
            user["updated_at"] = _utc_now_iso()
            updated_user = user
            break
        if not updated_user:
            return None
        self._save_users(users)
        from .user_db_selection_service import user_db_selection_service
        if previous_telegram_id not in (None, 0):
            if int(previous_telegram_id) != int(updated_user.get("telegram_id") or 0):
                user_db_selection_service.set_assigned_database(previous_telegram_id, None)
        if updated_user.get("telegram_id") is not None:
            user_db_selection_service.set_assigned_database(
                updated_user.get("telegram_id"),
                updated_user.get("assigned_database"),
            )
        return self._sanitize_user(updated_user)

    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        users = self._load_users()
        changed = False
        for user in users:
            if int(user.get("id", 0)) != int(user_id):
                continue
            if not self._verify_password(
                password=old_password,
                password_hash_b64=str(user.get("password_hash") or ""),
                salt_b64=str(user.get("password_salt") or ""),
            ):
                return False
            password_hash, salt = self._hash_password(new_password)
            user["password_hash"] = password_hash
            user["password_salt"] = salt
            user["updated_at"] = _utc_now_iso()
            changed = True
            break
        if changed:
            self._save_users(users)
        return changed

    def delete_user(self, user_id: int) -> bool:
        if user_id == 1:
            return False
            
        users = self._load_users()
        initial_count = len(users)
        users = [u for u in users if int(u.get("id", 0)) != user_id]
        
        if len(users) < initial_count:
            self._save_users(users)
            return True
        return False


user_service = UserService()
