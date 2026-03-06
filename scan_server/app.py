from __future__ import annotations

import logging
import hashlib
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .config import config
from .database import ScanStore
from .worker import ScanWorker

# Enable imports from WEB-itinvent backend for shared auth/permission logic.
project_root = Path(__file__).resolve().parent.parent
web_root = project_root / "WEB-itinvent"
if web_root.exists() and str(web_root) not in sys.path:
    sys.path.insert(0, str(web_root))

from backend.config import config as web_config
from backend.services import authorization_service, session_service, user_service
from backend.services.authorization_service import (
    PERM_SCAN_ACK,
    PERM_SCAN_READ,
    PERM_SCAN_TASKS,
)
from backend.utils.security import decode_access_token

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scan-server")
security_optional = HTTPBearer(auto_error=False)


def _now_ts() -> int:
    return int(time.time())


class IngestPayload(BaseModel):
    agent_id: str
    hostname: str
    branch: Optional[str] = ""
    user_login: Optional[str] = ""
    user_full_name: Optional[str] = ""
    file_path: str
    file_name: Optional[str] = ""
    file_hash: Optional[str] = ""
    file_size: Optional[int] = 0
    source_kind: Optional[str] = "unknown"
    event_id: Optional[str] = ""
    text_excerpt: Optional[str] = ""
    pdf_slice_b64: Optional[str] = ""
    local_pattern_hits: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


class HeartbeatPayload(BaseModel):
    agent_id: str
    hostname: str
    branch: Optional[str] = ""
    ip_address: Optional[str] = ""
    version: Optional[str] = ""
    status: Optional[str] = "online"
    queue_pending: Optional[int] = 0
    last_seen_at: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskCreatePayload(BaseModel):
    agent_id: str
    command: str
    payload: Optional[Dict[str, Any]] = None
    dedupe_key: Optional[str] = None


class TaskResultPayload(BaseModel):
    agent_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error_text: Optional[str] = ""


class IncidentAckPayload(BaseModel):
    ack_by: Optional[str] = ""


store = ScanStore(
    db_path=config.db_path,
    archive_dir=config.archive_dir,
    task_ack_timeout_sec=config.task_ack_timeout_sec,
)
stop_event = threading.Event()
worker = ScanWorker(store=store, config=config, stop_event=stop_event)


def _key_fingerprint(value: Optional[str]) -> str:
    token = str(value or "").strip()
    if not token:
        return "none"
    return hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _check_agent_key(x_api_key: Optional[str]) -> None:
    token = str(x_api_key or "").strip()
    if not token or token not in set(config.api_keys):
        logger.warning("Scan API rejected unknown key fingerprint=%s", _key_fingerprint(token))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def _resolve_access_token(
    credentials: Optional[HTTPAuthorizationCredentials],
    access_token_cookie: Optional[str],
) -> Optional[str]:
    if credentials and credentials.credentials:
        return credentials.credentials
    if access_token_cookie:
        return str(access_token_cookie).strip() or None
    return None


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden_exception(permission: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Insufficient permissions: {permission}",
    )


def require_web_permission(permission: str):
    async def _dependency(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
        access_token_cookie: Optional[str] = Cookie(None, alias=web_config.app.auth_cookie_name),
    ) -> Dict[str, Any]:
        token = _resolve_access_token(credentials, access_token_cookie)
        if not token:
            raise _credentials_exception()

        token_data = decode_access_token(token)
        if token_data is None:
            raise _credentials_exception()

        if token_data.session_id and not session_service.is_session_active(token_data.session_id):
            raise _credentials_exception()

        user_raw = None
        if token_data.user_id not in (None, 0):
            user_raw = user_service.get_by_id(token_data.user_id)
        if user_raw is None and token_data.username:
            user_raw = user_service.get_by_username(token_data.username)
        if not user_raw:
            raise _credentials_exception()

        if token_data.session_id:
            session_service.touch_session(token_data.session_id)

        if not bool(user_raw.get("is_active", True)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

        role = str(user_raw.get("role") or token_data.role or "viewer")
        if not authorization_service.has_permission(
            role,
            permission,
            use_custom_permissions=bool(user_raw.get("use_custom_permissions", False)),
            custom_permissions=user_raw.get("custom_permissions"),
        ):
            raise _forbidden_exception(permission)

        return user_raw

    return _dependency


def _model_dump(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop_event.clear()
    if not worker.is_alive():
        worker.start()
    logger.info("Scan server started on %s:%s", config.host, config.port)
    yield
    stop_event.set()
    if worker.is_alive():
        worker.join(timeout=5)
    logger.info("Scan server stopped")


app = FastAPI(
    title="IT-Invent Scan Server",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "time": _now_ts()}


@app.post("/api/v1/scan/heartbeat")
async def heartbeat(payload: HeartbeatPayload, x_api_key: Optional[str] = Header(None)) -> Dict[str, Any]:
    _check_agent_key(x_api_key)
    data = _model_dump(payload)
    data["last_seen_at"] = int(data.get("last_seen_at") or _now_ts())
    row = store.upsert_agent_heartbeat(data)
    return {"success": True, "agent_id": row["agent_id"], "last_seen_at": row["last_seen_at"]}


@app.post("/api/v1/scan/ingest")
async def ingest(payload: IngestPayload, x_api_key: Optional[str] = Header(None)) -> Dict[str, Any]:
    _check_agent_key(x_api_key)
    queued = store.queue_job(_model_dump(payload))
    return {"success": True, **queued}


@app.get("/api/v1/scan/tasks/poll")
async def poll_tasks(
    agent_id: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    x_api_key: Optional[str] = Header(None),
) -> Dict[str, Any]:
    _check_agent_key(x_api_key)
    tasks = store.poll_tasks(agent_id=agent_id, limit=min(limit, config.poll_limit))
    return {"agent_id": agent_id, "tasks": tasks}


@app.post("/api/v1/scan/tasks/{task_id}/result")
async def task_result(task_id: str, payload: TaskResultPayload, x_api_key: Optional[str] = Header(None)) -> Dict[str, Any]:
    _check_agent_key(x_api_key)
    status_value = str(payload.status or "").strip().lower()
    if status_value not in {"acknowledged", "completed", "failed"}:
        raise HTTPException(status_code=400, detail="Unsupported status")
    result = store.report_task_result(
        agent_id=payload.agent_id,
        task_id=task_id,
        status=status_value,
        result=payload.result,
        error_text=payload.error_text,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, **result}


@app.post("/api/v1/scan/tasks")
async def create_task(
    payload: TaskCreatePayload,
    _: Dict[str, Any] = Depends(require_web_permission(PERM_SCAN_TASKS)),
) -> Dict[str, Any]:
    command = str(payload.command or "").strip().lower()
    if command not in {"ping", "scan_now"}:
        raise HTTPException(status_code=400, detail="Unsupported command")
    created = store.create_task(
        agent_id=payload.agent_id,
        command=command,
        payload=payload.payload,
        ttl_days=config.task_ttl_days,
        dedupe_key=payload.dedupe_key,
    )
    return {"success": True, "task": created}


@app.get("/api/v1/scan/incidents")
async def incidents(
    status_value: Optional[str] = Query(None, alias="status"),
    severity: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
    hostname: Optional[str] = Query(None),
    source_kind: Optional[str] = Query(None),
    file_ext: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    has_fragment: Optional[bool] = Query(None),
    ack_by: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    _: Dict[str, Any] = Depends(require_web_permission(PERM_SCAN_READ)),
) -> Dict[str, Any]:
    return store.list_incidents(
        status=status_value,
        severity=severity,
        branch=branch,
        hostname=hostname,
        source_kind=source_kind,
        file_ext=file_ext,
        date_from=date_from,
        date_to=date_to,
        has_fragment=has_fragment,
        ack_by=ack_by,
        q=q,
        limit=limit,
        offset=offset,
    )


@app.post("/api/v1/scan/incidents/{incident_id}/ack")
async def ack_incident(
    incident_id: str,
    payload: IncidentAckPayload,
    _: Dict[str, Any] = Depends(require_web_permission(PERM_SCAN_ACK)),
) -> Dict[str, Any]:
    acked = store.ack_incident(incident_id=incident_id, ack_by=str(payload.ack_by or "").strip())
    if acked is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"success": True, "incident": acked}


@app.get("/api/v1/scan/dashboard")
async def dashboard(
    _: Dict[str, Any] = Depends(require_web_permission(PERM_SCAN_READ)),
) -> Dict[str, Any]:
    return store.dashboard()


@app.get("/api/v1/scan/agents")
async def agents(
    _: Dict[str, Any] = Depends(require_web_permission(PERM_SCAN_READ)),
) -> List[Dict[str, Any]]:
    return store.list_agents()


@app.get("/api/v1/scan/hosts")
async def hosts(
    q: Optional[str] = Query(None),
    branch: Optional[str] = Query(None),
    status_value: Optional[str] = Query(None, alias="status"),
    severity: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    _: Dict[str, Any] = Depends(require_web_permission(PERM_SCAN_READ)),
) -> List[Dict[str, Any]]:
    return store.list_hosts(
        q=q,
        branch=branch,
        status=status_value,
        severity=severity,
        limit=limit,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "scan_server.app:app",
        host=config.host,
        port=config.port,
        reload=False,
    )
