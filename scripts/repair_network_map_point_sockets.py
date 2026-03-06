from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "WEB-itinvent"
    sys.path.insert(0, str(backend_root))

    from backend.services.network_service import network_service  # noqa: WPS433

    summary = network_service.repair_map_point_socket_conflicts(
        actor_user_id=None,
        actor_role="maintenance_script",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
