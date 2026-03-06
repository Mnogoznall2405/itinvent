"""
One-time migration helper for IT template fields schema.

Converts legacy required_fields payloads to the new fields schema and disables invalid templates.
"""
from __future__ import annotations

from backend.services.mail_service import mail_service


def main() -> None:
    mail_service._migrate_legacy_template_fields()
    print("Mail template fields migration completed.")


if __name__ == "__main__":
    main()
