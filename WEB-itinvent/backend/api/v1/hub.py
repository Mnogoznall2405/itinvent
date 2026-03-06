"""
Hub API: dashboard, announcements, tasks, notifications.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from backend.api.deps import ensure_user_permission, get_current_active_user, require_permission
from backend.models.auth import User
from backend.services.authorization_service import (
    PERM_ANNOUNCEMENTS_WRITE,
    PERM_DASHBOARD_READ,
    PERM_TASKS_READ,
    PERM_TASKS_REVIEW,
    PERM_TASKS_WRITE,
)
from backend.services.hub_service import hub_service
from backend.services.markdown_transform_service import (
    MarkdownTransformConfigError,
    MarkdownTransformError,
    markdown_transform_service,
)


router = APIRouter()

MAX_TASK_REPORT_FILE_BYTES = 20 * 1024 * 1024
MAX_ANNOUNCEMENT_FILE_BYTES = 20 * 1024 * 1024
MAX_TASK_ATTACHMENT_FILE_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "jpg",
    "jpeg",
    "png",
    "txt",
    "zip",
}


def _normalize_text(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _has_permission(user: User, permission: str) -> bool:
    current_permissions = set(getattr(user, "permissions", []) or [])
    return permission in current_permissions


def _actor_dict(user: User) -> dict:
    return {
        "id": int(user.id),
        "username": _normalize_text(user.username),
        "full_name": _normalize_text(getattr(user, "full_name", "")),
    }


def _validate_upload(file_name: str, payload_size: int, *, max_bytes: int, context: str) -> None:
    normalized_name = _normalize_text(file_name) or "file.bin"
    ext = Path(normalized_name).suffix.lower().lstrip(".")
    if not ext or ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"{context}: unsupported file type '{ext or '-'}'",
        )
    if int(payload_size) > int(max_bytes):
        raise HTTPException(
            status_code=413,
            detail=f"{context}: file is too large",
        )


@router.get("/dashboard")
async def get_hub_dashboard(
    announcements_limit: int = Query(20, ge=1, le=200),
    tasks_limit: int = Query(10, ge=1, le=200),
    current_user: User = Depends(require_permission(PERM_DASHBOARD_READ)),
):
    return hub_service.get_dashboard(
        user_id=int(current_user.id),
        announcements_limit=int(announcements_limit),
        tasks_limit=int(tasks_limit),
    )


@router.get("/announcements")
async def get_announcements(
    q: str = Query("", min_length=0),
    priority: str = Query("", pattern="^(|low|normal|high)$"),
    unread_only: bool = Query(False),
    has_attachments: bool = Query(False),
    sort_by: str = Query("published_at", pattern="^(published_at|updated_at|priority)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(30, ge=1, le=300),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(PERM_DASHBOARD_READ)),
):
    return hub_service.list_announcements(
        user_id=int(current_user.id),
        q=_normalize_text(q),
        priority=_normalize_text(priority),
        unread_only=bool(unread_only),
        has_attachments=bool(has_attachments),
        sort_by=_normalize_text(sort_by),
        sort_dir=_normalize_text(sort_dir),
        limit=int(limit),
        offset=int(offset),
    )


@router.post("/announcements")
async def create_announcement(
    request: Request,
    current_user: User = Depends(require_permission(PERM_ANNOUNCEMENTS_WRITE)),
):
    try:
        title = ""
        preview = ""
        body = ""
        priority = "normal"
        attachments: list[dict] = []

        content_type = _normalize_text(request.headers.get("content-type")).lower()
        if "multipart/form-data" in content_type:
            form = await request.form()
            title = _normalize_text(form.get("title"))
            preview = _normalize_text(form.get("preview"))
            body = _normalize_text(form.get("body"))
            priority = _normalize_text(form.get("priority"), "normal")
            form_files = form.getlist("files")
            for form_file in form_files:
                if form_file is None or not hasattr(form_file, "read"):
                    continue
                file_name = _normalize_text(getattr(form_file, "filename", "")) or "file.bin"
                file_mime = _normalize_text(getattr(form_file, "content_type", ""))
                payload_bytes = await form_file.read()
                _validate_upload(
                    file_name=file_name,
                    payload_size=len(payload_bytes),
                    max_bytes=MAX_ANNOUNCEMENT_FILE_BYTES,
                    context="Announcement attachment",
                )
                attachments.append(
                    {
                        "file_name": file_name,
                        "file_mime": file_mime,
                        "file_bytes": payload_bytes,
                    }
                )
        else:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="Invalid announcement payload")
            title = _normalize_text(payload.get("title"))
            preview = _normalize_text(payload.get("preview"))
            body = _normalize_text(payload.get("body"))
            priority = _normalize_text(payload.get("priority"), "normal")

        return hub_service.create_announcement(
            title=title,
            preview=preview,
            body=body,
            priority=priority,
            actor=_actor_dict(current_user),
            attachments=attachments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/announcements/{announcement_id}")
async def patch_announcement(
    announcement_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(require_permission(PERM_ANNOUNCEMENTS_WRITE)),
):
    try:
        updated = hub_service.update_announcement(
            announcement_id,
            payload or {},
            actor_user_id=int(current_user.id),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return updated


@router.delete("/announcements/{announcement_id}")
async def delete_announcement(
    announcement_id: str,
    current_user: User = Depends(require_permission(PERM_ANNOUNCEMENTS_WRITE)),
):
    try:
        ok = hub_service.delete_announcement(
            announcement_id=announcement_id,
            actor_user_id=int(current_user.id),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"ok": True, "announcement_id": announcement_id}


@router.post("/announcements/{announcement_id}/mark-as-read")
async def mark_announcement_as_read(
    announcement_id: str,
    current_user: User = Depends(require_permission(PERM_DASHBOARD_READ)),
):
    ok = hub_service.mark_announcement_read(
        announcement_id=announcement_id,
        user=_actor_dict(current_user),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"ok": True, "announcement_id": announcement_id}


@router.get("/announcements/{announcement_id}/reads")
async def get_announcement_reads(
    announcement_id: str,
    _: User = Depends(require_permission(PERM_ANNOUNCEMENTS_WRITE)),
):
    return {"items": hub_service.get_announcement_reads(announcement_id)}


@router.get("/announcements/{announcement_id}/attachments/{attachment_id}/file")
async def download_announcement_attachment(
    announcement_id: str,
    attachment_id: str,
    _: User = Depends(require_permission(PERM_DASHBOARD_READ)),
):
    item = hub_service.get_announcement_attachment(
        announcement_id=announcement_id,
        attachment_id=attachment_id,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Announcement attachment not found")
    file_path = Path(_normalize_text(item.get("file_abs_path")))
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Announcement attachment file is not available")
    return FileResponse(
        path=str(file_path),
        filename=_normalize_text(item.get("file_name"), file_path.name),
        media_type=_normalize_text(item.get("file_mime")) or "application/octet-stream",
    )


@router.get("/users/assignees")
async def get_assignee_users(
    _: User = Depends(require_permission(PERM_TASKS_WRITE)),
):
    return {"items": hub_service.list_assignees()}


@router.get("/users/controllers")
async def get_controller_users(
    _: User = Depends(require_permission(PERM_TASKS_WRITE)),
):
    return {"items": hub_service.list_controllers()}


@router.post("/markdown/transform")
async def transform_markdown(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_active_user),
):
    context = _normalize_text(payload.get("context")).lower()
    text = _normalize_text(payload.get("text"))

    if context not in {"announcement", "task"}:
        raise HTTPException(status_code=400, detail="context must be 'announcement' or 'task'")
    if len(text) < 3:
        raise HTTPException(status_code=400, detail="Text is too short for transformation")
    if len(text) > 20000:
        raise HTTPException(status_code=413, detail="Text is too large (max 20000 symbols)")

    required_permission = PERM_ANNOUNCEMENTS_WRITE if context == "announcement" else PERM_TASKS_WRITE
    ensure_user_permission(current_user, required_permission)

    try:
        return markdown_transform_service.transform_text(text=text, context=context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MarkdownTransformConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MarkdownTransformError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/tasks")
async def get_tasks(
    scope: str = Query("my", pattern="^(my|all)$"),
    role_scope: str = Query("both", pattern="^(assignee|creator|controller|both)$"),
    status_filter: str = Query("", alias="status"),
    q: str = Query("", min_length=0),
    assignee_user_id: Optional[int] = Query(None, ge=1),
    has_attachments: bool = Query(False),
    due_state: str = Query("", pattern="^(|overdue|today|upcoming|none)$"),
    sort_by: str = Query("status", pattern="^(status|updated_at|due_at)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_permission(PERM_TASKS_READ)),
):
    allow_all = str(getattr(current_user, "role", "") or "").lower() == "admin"
    if scope == "all" and not allow_all:
        raise HTTPException(status_code=403, detail="Insufficient permissions: tasks.all")
    return hub_service.list_tasks(
        user_id=int(current_user.id),
        scope=scope,
        role_scope=_normalize_text(role_scope).lower(),
        status_filter=_normalize_text(status_filter).lower(),
        q=_normalize_text(q),
        assignee_user_id=assignee_user_id,
        has_attachments=bool(has_attachments),
        due_state=_normalize_text(due_state).lower(),
        sort_by=_normalize_text(sort_by).lower(),
        sort_dir=_normalize_text(sort_dir).lower(),
        limit=int(limit),
        offset=int(offset),
        allow_all_scope=allow_all,
    )


@router.post("/tasks")
async def create_task(
    payload: dict = Body(...),
    current_user: User = Depends(require_permission(PERM_TASKS_WRITE)),
):
    try:
        controller_raw = payload.get("controller_user_id")
        if controller_raw in (None, "", 0, "0"):
            raise ValueError("controller_user_id is required")
        controller_user_id = int(controller_raw)
        assignee_ids_raw = payload.get("assignee_user_ids")
        assignee_ids: list[int] = []
        if isinstance(assignee_ids_raw, list):
            for item in assignee_ids_raw:
                try:
                    value = int(item)
                except Exception:
                    continue
                if value not in assignee_ids:
                    assignee_ids.append(value)
        if not assignee_ids:
            single_assignee = payload.get("assignee_user_id")
            if single_assignee is not None:
                assignee_ids = [int(single_assignee)]
        if not assignee_ids:
            raise ValueError("At least one assignee is required")

        created_items = []
        for assignee_id in assignee_ids:
            created_items.append(
                hub_service.create_task(
                    title=_normalize_text(payload.get("title")),
                    description=_normalize_text(payload.get("description")),
                    assignee_user_id=int(assignee_id),
                    controller_user_id=controller_user_id,
                    due_at=_normalize_text(payload.get("due_at")) or None,
                    priority=_normalize_text(payload.get("priority"), "normal"),
                    actor=_actor_dict(current_user),
                )
            )
        return {
            "items": created_items,
            "created": len(created_items),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}")
async def patch_task(
    task_id: str,
    payload: dict = Body(...),
    _: User = Depends(require_permission(PERM_TASKS_WRITE)),
):
    try:
        updated = hub_service.update_task(task_id, payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(require_permission(PERM_TASKS_WRITE)),
):
    try:
        is_admin = str(getattr(current_user, "role", "") or "").lower() == "admin"
        ok = hub_service.delete_task(
            task_id=task_id,
            actor_user_id=int(current_user.id),
            is_admin=is_admin,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True, "task_id": task_id}


@router.post("/tasks/{task_id}/start")
async def start_task(
    task_id: str,
    current_user: User = Depends(require_permission(PERM_TASKS_READ)),
):
    try:
        updated = hub_service.start_task(task_id=task_id, user=_actor_dict(current_user))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    hub_service.mark_task_notifications_read(
        task_id=task_id,
        user_id=int(current_user.id),
    )
    return updated


@router.post("/tasks/{task_id}/submit")
async def submit_task(
    task_id: str,
    comment: str = Form(""),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(require_permission(PERM_TASKS_READ)),
):
    file_name = None
    file_bytes = None
    file_mime = None
    if file is not None:
        file_name = _normalize_text(file.filename) or "report.bin"
        file_mime = _normalize_text(file.content_type)
        payload = await file.read()
        _validate_upload(
            file_name=file_name,
            payload_size=len(payload),
            max_bytes=MAX_TASK_REPORT_FILE_BYTES,
            context="Task report",
        )
        file_bytes = payload
    try:
        updated = hub_service.submit_task(
            task_id=task_id,
            user=_actor_dict(current_user),
            comment=_normalize_text(comment),
            file_name=file_name,
            file_bytes=file_bytes,
            file_mime=file_mime,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


@router.post("/tasks/{task_id}/attachments")
async def upload_task_attachment(
    task_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission(PERM_TASKS_READ)),
):
    file_name = _normalize_text(file.filename) or "file.bin"
    file_mime = _normalize_text(file.content_type)
    payload = await file.read()
    _validate_upload(
        file_name=file_name,
        payload_size=len(payload),
        max_bytes=MAX_TASK_ATTACHMENT_FILE_BYTES,
        context="Task attachment",
    )
    try:
        created = hub_service.add_task_attachment(
            task_id=task_id,
            user=_actor_dict(current_user),
            file_name=file_name,
            file_bytes=payload,
            file_mime=file_mime,
            can_review=_has_permission(current_user, PERM_TASKS_REVIEW),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not created:
        raise HTTPException(status_code=404, detail="Task not found")
    return created


@router.post("/tasks/{task_id}/review")
async def review_task(
    task_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(require_permission(PERM_TASKS_REVIEW)),
):
    try:
        updated = hub_service.review_task(
            task_id=task_id,
            reviewer=_actor_dict(current_user),
            decision=_normalize_text(payload.get("decision")),
            comment=_normalize_text(payload.get("comment")),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


@router.get("/tasks/{task_id}/attachments/{attachment_id}/file")
async def download_task_attachment(
    task_id: str,
    attachment_id: str,
    _: User = Depends(require_permission(PERM_TASKS_READ)),
):
    item = hub_service.get_task_attachment(task_id=task_id, attachment_id=attachment_id)
    if not item:
        raise HTTPException(status_code=404, detail="Task attachment not found")
    file_path = Path(_normalize_text(item.get("file_abs_path")))
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Task attachment file is not available")
    return FileResponse(
        path=str(file_path),
        filename=_normalize_text(item.get("file_name"), file_path.name),
        media_type=_normalize_text(item.get("file_mime")) or "application/octet-stream",
    )


@router.get("/tasks/reports/{report_id}/file")
async def download_task_report(
    report_id: str,
    _: User = Depends(require_permission(PERM_TASKS_READ)),
):
    item = hub_service.get_report(report_id)
    if not item:
        raise HTTPException(status_code=404, detail="Task report not found")
    file_path = Path(_normalize_text(item.get("file_abs_path")))
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Task report file is not available")
    return FileResponse(
        path=str(file_path),
        filename=_normalize_text(item.get("file_name"), file_path.name),
        media_type=_normalize_text(item.get("file_mime")) or "application/octet-stream",
    )


@router.get("/tasks/{task_id}/comments")
async def get_task_comments(
    task_id: str,
    _: User = Depends(require_permission(PERM_TASKS_READ)),
):
    return {"items": hub_service.list_task_comments(task_id)}


@router.post("/tasks/{task_id}/comments")
async def create_task_comment(
    task_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(require_permission(PERM_TASKS_READ)),
):
    body = _normalize_text(payload.get("body"))
    if len(body) < 1:
        raise HTTPException(status_code=400, detail="Comment body is required")
    result = hub_service.add_task_comment(
        task_id=task_id,
        user=_actor_dict(current_user),
        body=body,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.get("/tasks/{task_id}/status-log")
async def get_task_status_log(
    task_id: str,
    _: User = Depends(require_permission(PERM_TASKS_READ)),
):
    return {"items": hub_service.list_task_status_log(task_id)}


@router.get("/notifications/poll")
async def poll_notifications(
    since: str = Query("", min_length=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_permission(PERM_DASHBOARD_READ)),
):
    return hub_service.poll_notifications(
        user_id=int(current_user.id),
        since=_normalize_text(since),
        limit=int(limit),
    )


@router.get("/notifications/unread-counts")
async def get_notification_unread_counts(
    current_user: User = Depends(require_permission(PERM_DASHBOARD_READ)),
):
    return hub_service.get_unread_counts(user_id=int(current_user.id))


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(require_permission(PERM_DASHBOARD_READ)),
):
    ok = hub_service.mark_notification_read(notification_id=notification_id, user_id=int(current_user.id))
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True, "notification_id": notification_id}
