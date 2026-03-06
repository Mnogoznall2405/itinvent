"""
Mail API for Exchange inbox/sending and IT request templates.
"""
from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import quote
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Form, File, UploadFile, Response, Request
from pydantic import BaseModel, Field

from backend.api.deps import get_current_active_user, get_current_admin_user, require_permission
from backend.models.auth import User
from backend.services.authorization_service import PERM_MAIL_ACCESS
from backend.services.mail_service import MailPayloadTooLargeError, MailServiceError, mail_service


router = APIRouter()
logger = logging.getLogger(__name__)


def _normalize_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _build_content_disposition(filename: str) -> str:
    source = _normalize_text(filename, "attachment.bin").replace("\r", " ").replace("\n", " ")
    source = source.strip() or "attachment.bin"

    ascii_fallback = source.encode("ascii", "ignore").decode("ascii")
    ascii_fallback = re.sub(r'[";\\]+', "_", ascii_fallback).strip(" .")
    if not ascii_fallback:
        ascii_fallback = "attachment.bin"

    encoded = quote(source, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _request_id_from_headers(request: Request) -> str:
    return _normalize_text(request.headers.get("X-Client-Request-ID"), "-")


def _log_request_timing(route_name: str, request_id: str, started_at: float, **context: Any) -> None:
    took_ms = (time.perf_counter() - started_at) * 1000.0
    payload = " ".join([f"{key}={value}" for key, value in context.items() if value is not None])
    logger.info("mail.%s request_id=%s took_ms=%.1f %s", route_name, request_id, took_ms, payload)


class SendMessageRequest(BaseModel):
    to: list[str] = Field(default_factory=list)
    subject: str = Field(default="")
    body: str = Field(default="")
    is_html: bool = True


class SendItRequestPayload(BaseModel):
    template_id: str = Field(..., min_length=1)
    fields: dict[str, Any] = Field(default_factory=dict)


class UpdateMailConfigPayload(BaseModel):
    mailbox_email: Optional[str] = None
    mailbox_login: Optional[str] = None
    mailbox_password: Optional[str] = None
    mail_signature_html: Optional[str] = None


class UpdateMyMailConfigPayload(BaseModel):
    mail_signature_html: Optional[str] = None


class TestConnectionPayload(BaseModel):
    user_id: Optional[int] = None


@router.get("/contacts")
async def get_mail_contacts(
    request: Request,
    q: str = Query("", min_length=0),
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    started_at = time.perf_counter()
    request_id = _request_id_from_headers(request)
    try:
        items = mail_service.search_contacts(user_id=int(current_user.id), q=q)
        return {"items": items}
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        _log_request_timing(
            "contacts",
            request_id,
            started_at,
            user_id=int(current_user.id),
            q_len=len(str(q or "")),
        )


@router.get("/inbox")
async def get_inbox_messages(
    request: Request,
    folder: str = Query("inbox", min_length=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str = Query("", min_length=0),
    unread_only: bool = Query(False),
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    started_at = time.perf_counter()
    request_id = _request_id_from_headers(request)
    try:
        return mail_service.list_messages(
            user_id=int(current_user.id),
            folder=_normalize_text(folder, "inbox"),
            limit=int(limit),
            offset=int(offset),
            q=_normalize_text(q),
            unread_only=bool(unread_only),
        )
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        _log_request_timing(
            "inbox",
            request_id,
            started_at,
            user_id=int(current_user.id),
            folder=_normalize_text(folder, "inbox"),
            q_len=len(str(q or "")),
            unread_only=int(bool(unread_only)),
            limit=int(limit),
            offset=int(offset),
        )


@router.get("/messages/{message_id}")
async def get_mail_message(
    request: Request,
    message_id: str,
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    started_at = time.perf_counter()
    request_id = _request_id_from_headers(request)
    try:
        return mail_service.get_message(user_id=int(current_user.id), message_id=message_id)
    except MailServiceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        _log_request_timing(
            "message",
            request_id,
            started_at,
            user_id=int(current_user.id),
            message_id_len=len(str(message_id or "")),
        )


@router.post("/messages/{message_id}/read")
async def mark_message_read(
    message_id: str,
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    try:
        ok = mail_service.mark_as_read(user_id=int(current_user.id), message_id=message_id)
        return {"ok": ok}
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/unread-count")
async def get_mail_unread_count(
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    count = mail_service.get_unread_count(user_id=int(current_user.id))
    return {"unread_count": count}


@router.post("/messages/send")
async def send_message(
    request: Request,
    payload: SendMessageRequest,
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    started_at = time.perf_counter()
    request_id = _request_id_from_headers(request)
    try:
        return mail_service.send_message(
            user_id=int(current_user.id),
            to=payload.to,
            subject=_normalize_text(payload.subject),
            body=_normalize_text(payload.body),
            is_html=bool(payload.is_html),
        )
    except MailPayloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        _log_request_timing(
            "send",
            request_id,
            started_at,
            user_id=int(current_user.id),
            recipients=len(payload.to or []),
            subject_len=len(str(payload.subject or "")),
        )


@router.get("/messages/{message_id}/attachments/{attachment_ref}")
async def download_message_attachment(
    request: Request,
    message_id: str,
    attachment_ref: str,
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    started_at = time.perf_counter()
    request_id = _request_id_from_headers(request)
    try:
        attachment_id = mail_service.resolve_attachment_id(attachment_ref)
        filename, content_type, content = mail_service.download_attachment(
            user_id=int(current_user.id),
            message_id=message_id,
            attachment_id=attachment_id,
        )
        headers = {"Content-Disposition": _build_content_disposition(filename)}
        return Response(content=content, media_type=content_type, headers=headers)
    except MailServiceError as exc:
        logger.warning(
            "Mail attachment download failed: request_id=%s user_id=%s message_id=%s ref_len=%s error=%s",
            request_id,
            int(current_user.id),
            message_id,
            len(str(attachment_ref or "")),
            str(exc),
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        _log_request_timing(
            "download_attachment",
            request_id,
            started_at,
            user_id=int(current_user.id),
            message_id_len=len(str(message_id or "")),
            ref_len=len(str(attachment_ref or "")),
        )


@router.post("/messages/send-multipart")
async def send_message_multipart(
    request: Request,
    to: str = Form(...),
    subject: str = Form(""),
    body: str = Form(""),
    is_html: bool = Form(True),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    started_at = time.perf_counter()
    request_id = _request_id_from_headers(request)
    try:
        attachments = []
        for file in files:
            content = await file.read()
            if content:
                attachments.append((file.filename or "attachment.bin", content))
        
        to_list = [t.strip() for t in to.split(";") if t.strip()]

        return mail_service.send_message(
            user_id=int(current_user.id),
            to=to_list,
            subject=_normalize_text(subject),
            body=_normalize_text(body),
            is_html=bool(is_html),
            attachments=attachments,
        )
    except MailPayloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        _log_request_timing(
            "send_multipart",
            request_id,
            started_at,
            user_id=int(current_user.id),
            files=len(files or []),
            recipients=len([t for t in str(to or "").split(";") if t.strip()]),
            subject_len=len(str(subject or "")),
        )


@router.post("/messages/send-it-request")
async def send_it_request_message(
    payload: SendItRequestPayload,
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    try:
        return mail_service.send_it_request(
            user_id=int(current_user.id),
            template_id=_normalize_text(payload.template_id),
            fields=payload.fields or {},
        )
    except MailPayloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/messages/send-it-request-multipart")
async def send_it_request_message_multipart(
    request: Request,
    template_id: str = Form(...),
    fields_json: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    started_at = time.perf_counter()
    request_id = _request_id_from_headers(request)
    try:
        try:
            parsed_fields = json.loads(_normalize_text(fields_json, "{}"))
        except Exception as exc:
            raise MailServiceError("fields_json must contain valid JSON object") from exc
        if not isinstance(parsed_fields, dict):
            raise MailServiceError("fields_json must be a JSON object")

        attachments: list[tuple[str, bytes]] = []
        for file in files:
            content = await file.read()
            if not content:
                continue
            attachments.append((file.filename or "attachment.bin", content))

        return mail_service.send_it_request(
            user_id=int(current_user.id),
            template_id=_normalize_text(template_id),
            fields=parsed_fields,
            attachments=attachments,
        )
    except MailPayloadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        _log_request_timing(
            "send_it_multipart",
            request_id,
            started_at,
            user_id=int(current_user.id),
            files=len(files or []),
            template_id_len=len(str(template_id or "")),
        )


@router.get("/templates")
async def list_it_templates(
    include_inactive: bool = Query(False),
    _: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    return {
        "items": mail_service.list_templates(active_only=not bool(include_inactive)),
    }


@router.post("/templates")
async def create_it_template(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_admin_user),
):
    try:
        return mail_service.create_template(
            payload=payload or {},
            actor={
                "id": int(current_user.id),
                "username": _normalize_text(current_user.username),
            },
        )
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/templates/{template_id}")
async def update_it_template(
    template_id: str,
    payload: dict = Body(...),
    current_user: User = Depends(get_current_admin_user),
):
    try:
        return mail_service.update_template(
            template_id=template_id,
            payload=payload or {},
            actor={
                "id": int(current_user.id),
                "username": _normalize_text(current_user.username),
            },
        )
    except MailServiceError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/templates/{template_id}")
async def delete_it_template(
    template_id: str,
    current_user: User = Depends(get_current_admin_user),
):
    ok = mail_service.delete_template(
        template_id=template_id,
        actor={
            "id": int(current_user.id),
            "username": _normalize_text(current_user.username),
        },
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"ok": True, "template_id": template_id}


@router.get("/config/me")
async def get_my_mail_config(
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    try:
        return mail_service.get_my_config(user_id=int(current_user.id))
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/config/user/{user_id}")
async def patch_user_mail_config(
    user_id: int,
    payload: UpdateMailConfigPayload,
    _: User = Depends(get_current_admin_user),
):
    try:
        payload_data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
        return mail_service.update_user_config(
            user_id=int(user_id),
            **payload_data,
        )
    except MailServiceError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/config/me")
async def patch_my_mail_config(
    payload: UpdateMyMailConfigPayload,
    current_user: User = Depends(require_permission(PERM_MAIL_ACCESS)),
):
    try:
        payload_data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
        return mail_service.update_user_config(
            user_id=int(current_user.id),
            **payload_data,
        )
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/test-connection")
async def post_mail_test_connection(
    payload: TestConnectionPayload,
    current_user: User = Depends(get_current_admin_user),
):
    target_user_id = int(payload.user_id or current_user.id)
    try:
        return mail_service.test_connection(user_id=target_user_id)
    except MailServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/health")
async def get_mail_health(
    _: User = Depends(get_current_active_user),
):
    return {
        "ok": True,
        "exchange_host": mail_service.exchange_host,
        "ews_url": mail_service.exchange_ews_url,
        "verify_tls": mail_service.verify_tls,
    }
