"""
Centralized role -> permission mapping.
"""
from __future__ import annotations

from typing import Iterable


PERM_DATABASE_READ = "database.read"
PERM_DATABASE_WRITE = "database.write"
PERM_DASHBOARD_READ = "dashboard.read"
PERM_ANNOUNCEMENTS_WRITE = "announcements.write"
PERM_TASKS_READ = "tasks.read"
PERM_TASKS_WRITE = "tasks.write"
PERM_TASKS_REVIEW = "tasks.review"
PERM_NETWORKS_READ = "networks.read"
PERM_NETWORKS_WRITE = "networks.write"
PERM_COMPUTERS_READ = "computers.read"
PERM_COMPUTERS_READ_ALL = "computers.read_all"
PERM_SCAN_READ = "scan.read"
PERM_SCAN_ACK = "scan.ack"
PERM_SCAN_TASKS = "scan.tasks"
PERM_STATISTICS_READ = "statistics.read"
PERM_KB_READ = "kb.read"
PERM_KB_WRITE = "kb.write"
PERM_KB_PUBLISH = "kb.publish"
PERM_SETTINGS_READ = "settings.read"
PERM_SETTINGS_USERS_MANAGE = "settings.users.manage"
PERM_SETTINGS_SESSIONS_MANAGE = "settings.sessions.manage"
PERM_MAIL_ACCESS = "mail.access"

PERM_AD_USERS_READ = "ad_users.read"
PERM_AD_USERS_MANAGE = "ad_users.manage"

PERM_VCS_READ = "vcs.read"
PERM_VCS_MANAGE = "vcs.manage"

_VIEWER_PERMISSIONS = {
    PERM_DASHBOARD_READ,
    PERM_TASKS_READ,
    PERM_DATABASE_READ,
    PERM_NETWORKS_READ,
    PERM_COMPUTERS_READ,
    PERM_SCAN_READ,
    PERM_STATISTICS_READ,
    PERM_SETTINGS_READ,
    PERM_AD_USERS_READ,
    PERM_VCS_READ,
}

_OPERATOR_EXTRA_PERMISSIONS = {
    PERM_ANNOUNCEMENTS_WRITE,
    PERM_TASKS_WRITE,
    PERM_DATABASE_WRITE,
    PERM_NETWORKS_WRITE,
    PERM_SCAN_ACK,
    PERM_SCAN_TASKS,
    PERM_KB_READ,
    PERM_KB_WRITE,
    PERM_MAIL_ACCESS,
    PERM_AD_USERS_MANAGE,
}

_ADMIN_EXTRA_PERMISSIONS = {
    PERM_TASKS_REVIEW,
    PERM_COMPUTERS_READ_ALL,
    PERM_KB_PUBLISH,
    PERM_SETTINGS_USERS_MANAGE,
    PERM_SETTINGS_SESSIONS_MANAGE,
    PERM_MAIL_ACCESS,
    PERM_VCS_MANAGE,
}


class AuthorizationService:
    """Provides permission checks based on user role."""

    def __init__(self) -> None:
        viewer = set(_VIEWER_PERMISSIONS)
        operator = viewer | set(_OPERATOR_EXTRA_PERMISSIONS)
        admin = operator | set(_ADMIN_EXTRA_PERMISSIONS)
        self._permissions_by_role = {
            "viewer": viewer,
            "operator": operator,
            "admin": admin,
        }
        self._all_permissions = sorted(admin)

    def get_permissions_for_role(self, role: str | None) -> list[str]:
        normalized_role = str(role or "").strip().lower() or "viewer"
        permissions = self._permissions_by_role.get(normalized_role, self._permissions_by_role["viewer"])
        return sorted(permissions)

    def get_all_permissions(self) -> list[str]:
        return list(self._all_permissions)

    def normalize_permissions(self, permissions: Iterable[str] | None) -> list[str]:
        if permissions is None:
            return []
        normalized = {
            str(permission or "").strip()
            for permission in permissions
            if str(permission or "").strip() in self._all_permissions
        }
        return sorted(normalized)

    def get_effective_permissions(
        self,
        role: str | None,
        *,
        use_custom_permissions: bool = False,
        custom_permissions: Iterable[str] | None = None,
    ) -> list[str]:
        if bool(use_custom_permissions):
            return self.normalize_permissions(custom_permissions)
        return self.get_permissions_for_role(role)

    def has_permission(
        self,
        role: str | None,
        permission: str | None,
        *,
        use_custom_permissions: bool = False,
        custom_permissions: Iterable[str] | None = None,
    ) -> bool:
        target = str(permission or "").strip()
        if not target:
            return False
        return target in self.get_effective_permissions(
            role,
            use_custom_permissions=use_custom_permissions,
            custom_permissions=custom_permissions,
        )

    def has_any_permission(
        self,
        role: str | None,
        permissions: Iterable[str],
        *,
        use_custom_permissions: bool = False,
        custom_permissions: Iterable[str] | None = None,
    ) -> bool:
        role_permissions = set(
            self.get_effective_permissions(
                role,
                use_custom_permissions=use_custom_permissions,
                custom_permissions=custom_permissions,
            )
        )
        for permission in permissions:
            target = str(permission or "").strip()
            if target and target in role_permissions:
                return True
        return False


authorization_service = AuthorizationService()
