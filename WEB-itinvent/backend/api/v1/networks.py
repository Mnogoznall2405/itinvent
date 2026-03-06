from __future__ import annotations

import sqlite3
import urllib.parse
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.deps import ensure_user_permission, get_current_active_user
from backend.models.auth import User
from backend.services.authorization_service import PERM_NETWORKS_WRITE
from backend.services.network_service import NetworkConflictError, network_service


router = APIRouter()


def _ensure_write_role(user: User) -> None:
    ensure_user_permission(user, PERM_NETWORKS_WRITE)


def _payload(model: BaseModel, *, exclude_unset: bool = False) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def _raise_network_http(exc: ValueError) -> None:
    if isinstance(exc, NetworkConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


class DeviceCreateRequest(BaseModel):
    branch_id: int
    device_code: str = Field(..., min_length=1)
    device_type: str = Field(default="switch")
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    sheet_name: Optional[str] = None
    mgmt_ip: Optional[str] = None
    notes: Optional[str] = None


class DeviceUpdateRequest(BaseModel):
    device_code: Optional[str] = None
    device_type: Optional[str] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    sheet_name: Optional[str] = None
    mgmt_ip: Optional[str] = None
    notes: Optional[str] = None


class PortCreateRequest(BaseModel):
    device_id: int
    port_name: str = Field(..., min_length=1)
    patch_panel_port: Optional[str] = None
    location_code: Optional[str] = None
    vlan_raw: Optional[str] = None
    endpoint_name_raw: Optional[str] = None
    endpoint_ip_raw: Optional[str] = None
    endpoint_mac_raw: Optional[str] = None
    row_source_hash: Optional[str] = None


class PortUpdateRequest(BaseModel):
    port_name: Optional[str] = None
    patch_panel_port: Optional[str] = None
    location_code: Optional[str] = None
    vlan_raw: Optional[str] = None
    endpoint_name_raw: Optional[str] = None
    endpoint_ip_raw: Optional[str] = None
    endpoint_mac_raw: Optional[str] = None
    row_source_hash: Optional[str] = None


class MapUpdateRequest(BaseModel):
    title: Optional[str] = None
    floor_label: Optional[str] = None
    site_code: Optional[str] = None
    site_name: Optional[str] = None


class MapPointCreateRequest(BaseModel):
    branch_id: int
    map_id: int
    x_ratio: float
    y_ratio: float
    device_id: Optional[int] = None
    port_id: Optional[int] = None
    socket_id: Optional[int] = None
    label: Optional[str] = None
    note: Optional[str] = None
    color: Optional[str] = None


class MapPointUpdateRequest(BaseModel):
    map_id: Optional[int] = None
    x_ratio: Optional[float] = None
    y_ratio: Optional[float] = None
    device_id: Optional[int] = None
    port_id: Optional[int] = None
    socket_id: Optional[int] = None
    label: Optional[str] = None
    note: Optional[str] = None
    color: Optional[str] = None


class PanelDefinition(BaseModel):
    panel_index: int = Field(..., ge=1, le=200)
    port_count: int = Field(..., ge=1, le=512)


class BranchCreateRequest(BaseModel):
    city_code: str = Field(default="tmn", min_length=1)
    branch_code: Optional[str] = Field(default=None)
    branch_name: str = Field(..., min_length=1)

    # Legacy uniform mode
    panel_count: Optional[int] = Field(default=None, ge=1, le=200)
    ports_per_panel: Optional[int] = Field(default=None, ge=1, le=512)

    # New heterogeneous mode
    panels: Optional[list[PanelDefinition]] = Field(default=None, min_length=1, max_length=200)

    # NEW: Default site code and database for FIO lookup
    default_site_code: Optional[str] = None
    db_id: Optional[str] = None


class SocketUpdateRequest(BaseModel):
    socket_code: Optional[str] = None
    port_id: Optional[int] = None
    mac_address: Optional[str] = None


class SocketCreateRequest(BaseModel):
    socket_code: str = Field(..., min_length=1)
    mac_address: Optional[str] = None


class SocketBootstrapRequest(BaseModel):
    panel_count: Optional[int] = Field(default=None, ge=1, le=200)
    ports_per_panel: Optional[int] = Field(default=None, ge=1, le=512)


class BranchDbMappingRequest(BaseModel):
    db_id: str = Field(..., min_length=1)


class SocketResolveRequest(BaseModel):
    socket_ids: Optional[list[int]] = None


class BranchUpdateRequest(BaseModel):
    branch_name: Optional[str] = None
    default_site_code: Optional[str] = None
    db_id: Optional[str] = None


@router.get("/branches")
async def get_branches(
    city: str = Query("tmn", min_length=1),
    _: User = Depends(get_current_active_user),
):
    return {"branches": network_service.list_branches(city)}


@router.post("/branches")
async def create_branch(
    payload: BranchCreateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)

    # Validate: either uniform mode (panel_count + ports_per_panel) or heterogeneous mode (panels)
    is_uniform = payload.panels is None or len(payload.panels) == 0

    if is_uniform and (payload.panel_count is not None or payload.ports_per_panel is not None):
        if payload.panel_count is None or payload.ports_per_panel is None:
            raise HTTPException(
                status_code=400,
                detail="Both panel_count and ports_per_panel required for uniform mode if provided"
            )
    else:
        # Heterogeneous mode: validate panels
        if payload.panel_count is not None or payload.ports_per_panel is not None:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both panel_count/ports_per_panel and panels"
            )

    try:
        # Convert panels to list of dicts if using heterogeneous mode
        panels_list = None
        if not is_uniform:
            panels_list = [
                {"panel_index": p.panel_index, "port_count": p.port_count}
                for p in payload.panels
            ]

        return network_service.create_branch_with_profile(
            city_code=payload.city_code,
            branch_code=payload.branch_code,
            name=payload.branch_name,
            panel_count=payload.panel_count,
            ports_per_panel=payload.ports_per_panel,
            panels=panels_list,
            default_site_code=payload.default_site_code,
            db_id=payload.db_id,
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/branches/{branch_id}")
async def update_branch(
    branch_id: int,
    payload: BranchUpdateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        updated = network_service.update_branch(
            branch_id=branch_id,
            branch_name=payload.branch_name,
            default_site_code=payload.default_site_code,
            db_id=payload.db_id,
            updated_by=getattr(current_user, "username", None),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
        return {"success": True, "branch": updated}
    except ValueError as exc:
        if str(exc) == "Branch not found":
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/branches/{branch_id}")
async def delete_branch(
    branch_id: int,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        network_service.delete_branch(
            branch_id=branch_id,
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
        return {"success": True}
    except ValueError as exc:
        if str(exc) == "Branch not found":
            return {"success": True, "note": "Already deleted"}
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/branches/{branch_id}/overview")
async def get_branch_overview(
    branch_id: int,
    _: User = Depends(get_current_active_user),
):
    try:
        return network_service.get_branch_overview(branch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/branches/{branch_id}/devices")
async def get_devices(
    branch_id: int,
    _: User = Depends(get_current_active_user),
):
    return {"devices": network_service.list_devices(branch_id)}


@router.get("/devices/{device_id}/ports")
async def get_ports(
    device_id: int,
    search: str = Query("", min_length=0),
    vlan: str = Query("", min_length=0),
    occupied: Optional[bool] = Query(None),
    location: str = Query("", min_length=0),
    _: User = Depends(get_current_active_user),
):
    return {
        "ports": network_service.list_ports(
            device_id,
            search=search,
            vlan=vlan,
            occupied=occupied,
            location=location,
        )
    }


@router.get("/branches/{branch_id}/ports")
async def get_branch_ports(
    branch_id: int,
    search: str = Query("", min_length=0),
    vlan: str = Query("", min_length=0),
    occupied: Optional[bool] = Query(None),
    location: str = Query("", min_length=0),
    limit: int = Query(5000, ge=1, le=10000),
    _: User = Depends(get_current_active_user),
):
    return {
        "ports": network_service.list_ports_by_branch(
            branch_id,
            search=search,
            vlan=vlan,
            occupied=occupied,
            location=location,
            limit=limit,
        )
    }


@router.get("/branches/{branch_id}/sockets")
async def get_branch_sockets(
    branch_id: int,
    search: str = Query("", min_length=0),
    limit: int = Query(5000, ge=1, le=10000),
    _: User = Depends(get_current_active_user),
):
    return {
        "sockets": network_service.list_sockets(
            branch_id,
            search=search,
            limit=limit,
        )
    }


@router.post("/branches/{branch_id}/sockets")
async def create_branch_socket(
    branch_id: int,
    payload: SocketCreateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.create_socket(
            branch_id=branch_id,
            payload=_payload(payload),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        _raise_network_http(exc)


@router.patch("/sockets/{socket_id}")
async def update_socket(
    socket_id: int,
    payload: SocketUpdateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.update_socket(
            socket_id=socket_id,
            payload=_payload(payload, exclude_unset=True),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        _raise_network_http(exc)


@router.delete("/sockets/{socket_id}")
async def delete_socket(
    socket_id: int,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    ok = network_service.delete_socket(
        socket_id=socket_id,
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Socket not found")
    return {"success": True}


@router.post("/branches/{branch_id}/sockets/bootstrap")
async def bootstrap_branch_sockets(
    branch_id: int,
    payload: SocketBootstrapRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.bootstrap_branch_sockets(
            branch_id=branch_id,
            panel_count=payload.panel_count,
            ports_per_panel=payload.ports_per_panel,
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/branches/{branch_id}/sockets/sync-host-context")
async def sync_branch_socket_host_context(
    branch_id: int,
    payload: Optional[SocketResolveRequest] = None,
    current_user: User = Depends(get_current_active_user),
):
    """Sync socket/port IP+MAC+FIO by strict MAC matching in linked SQL DB."""
    _ensure_write_role(current_user)
    try:
        return network_service.sync_socket_host_context(
            branch_id=branch_id,
            socket_ids=(payload.socket_ids if payload else None),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/branches/{branch_id}/sockets/import")
async def import_branch_sockets_template(
    branch_id: int,
    template_file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    template_bytes = await template_file.read()
    try:
        return network_service.import_sockets_template(
            branch_id=branch_id,
            file_name=template_file.filename or "socket_template.xlsx",
            file_bytes=template_bytes,
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/branches/{branch_id}/equipment/import")
async def import_branch_equipment_excel(
    branch_id: int,
    excel_file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    """Import switches/devices and their ports from a multi-sheet Excel file into an existing branch.
    Links ports to existing sockets via 'Port P/P' column."""
    _ensure_write_role(current_user)
    file_bytes = await excel_file.read()
    try:
        return network_service.import_equipment_from_excel(
            branch_id=branch_id,
            file_name=excel_file.filename or "equipment.xlsx",
            file_bytes=file_bytes,
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@router.get("/branches/{branch_id}/db-mapping")
async def get_branch_db_mapping(
    branch_id: int,
    _: User = Depends(get_current_active_user),
):
    try:
        return network_service.get_branch_db_mapping(branch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/branches/{branch_id}/db-mapping")
async def patch_branch_db_mapping(
    branch_id: int,
    payload: BranchDbMappingRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.update_branch_db_mapping(
            branch_id=branch_id,
            db_id=payload.db_id,
            updated_by=getattr(current_user, "username", None),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/branches/{branch_id}/sockets/resolve-fio")
async def resolve_branch_socket_fio(
    branch_id: int,
    payload: Optional[SocketResolveRequest] = None,
    current_user: User = Depends(get_current_active_user),
):
    """Backward-compatible alias for legacy clients."""
    _ensure_write_role(current_user)
    try:
        return network_service.sync_socket_host_context(
            branch_id=branch_id,
            socket_ids=(payload.socket_ids if payload else None),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/branches/{branch_id}/maps")
async def get_maps(
    branch_id: int,
    _: User = Depends(get_current_active_user),
):
    return {"maps": network_service.list_maps(branch_id)}


@router.get("/branches/{branch_id}/map-points")
async def get_map_points(
    branch_id: int,
    map_id: Optional[int] = Query(None),
    _: User = Depends(get_current_active_user),
):
    return {"points": network_service.list_map_points(branch_id=branch_id, map_id=map_id)}


@router.get("/maps/{map_id}/file")
async def download_map_file(
    map_id: int,
    render: str = Query("auto"),
    _: User = Depends(get_current_active_user),
):
    try:
        data = network_service.get_map_file_for_view(map_id, render_mode=render)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not data:
        raise HTTPException(status_code=404, detail="Map file not found")
    file_name = str(data.get("file_name") or f"map_{map_id}.bin")
    mime_type = str(data.get("mime_type") or "application/octet-stream")
    file_blob = data.get("file_blob") or b""
    rendered_from = str(data.get("rendered_from") or "").strip()
    headers = {
        "Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(file_name)}",
    }
    if rendered_from:
        headers["X-Map-Rendered-From"] = rendered_from
    return StreamingResponse(BytesIO(file_blob), media_type=mime_type, headers=headers)


@router.get("/audit")
async def get_audit(
    branch_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(get_current_active_user),
):
    return {"items": network_service.list_audit(branch_id=branch_id, limit=limit)}


@router.post("/import")
async def import_network_data(
    city_code: str = Form("tmn"),
    branch_code: str = Form("tmn-p19-21"),
    branch_name: str = Form("Первомайская 19/21"),
    excel_file: UploadFile = File(...),
    map_files: Optional[list[UploadFile]] = File(None),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    excel_bytes = await excel_file.read()
    maps_payload = []
    for map_file in map_files or []:
        map_bytes = await map_file.read()
        maps_payload.append(
            {
                "file_name": map_file.filename,
                "mime_type": map_file.content_type,
                "file_bytes": map_bytes,
            }
        )
    try:
        return network_service.import_branch_data(
            city_code=city_code,
            branch_code=branch_code,
            branch_name=branch_name,
            excel_file_name=excel_file.filename or "network.xlsx",
            excel_file_bytes=excel_bytes,
            map_files=maps_payload,
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/devices")
async def create_device(
    payload: DeviceCreateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.create_device(
            branch_id=payload.branch_id,
            payload=_payload(payload),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="Device already exists") from exc


@router.patch("/devices/{device_id}")
async def update_device(
    device_id: int,
    payload: DeviceUpdateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.update_device(
            device_id=device_id,
            payload=_payload(payload, exclude_unset=True),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: int,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    ok = network_service.delete_device(
        device_id=device_id,
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True}


class DeviceBootstrapPortsRequest(BaseModel):
    port_count: int = Field(..., ge=1, le=512)


@router.post("/devices/{device_id}/bootstrap-ports")
async def bootstrap_device_ports(
    device_id: int,
    payload: DeviceBootstrapPortsRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.bootstrap_device_ports(
            device_id=device_id,
            port_count=payload.port_count,
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ports")
async def create_port(
    payload: PortCreateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.create_port(
            device_id=payload.device_id,
            payload=_payload(payload),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        _raise_network_http(exc)


@router.patch("/ports/{port_id}")
async def update_port(
    port_id: int,
    payload: PortUpdateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.update_port(
            port_id=port_id,
            payload=_payload(payload, exclude_unset=True),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        _raise_network_http(exc)


@router.delete("/ports/{port_id}")
async def delete_port(
    port_id: int,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    ok = network_service.delete_port(
        port_id=port_id,
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Port not found")
    return {"success": True}


@router.post("/maps/upload")
async def upload_map(
    branch_id: int = Form(...),
    file: UploadFile = File(...),
    site_code: Optional[str] = Form(None),
    site_name: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    floor_label: Optional[str] = Form(None),
    source_path: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    file_bytes = await file.read()
    try:
        return network_service.upload_map(
            branch_id=branch_id,
            file_name=file.filename or "map.bin",
            mime_type=file.content_type or "application/octet-stream",
            file_bytes=file_bytes,
            site_code=site_code,
            site_name=site_name,
            title=title,
            floor_label=floor_label,
            source_path=source_path,
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/maps/{map_id}")
async def update_map(
    map_id: int,
    payload: MapUpdateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.update_map_meta(
            map_id=map_id,
            payload=_payload(payload, exclude_unset=True),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/maps/{map_id}")
async def delete_map(
    map_id: int,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    ok = network_service.delete_map(
        map_id=map_id,
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Map not found")
    return {"success": True}


@router.post("/map-points")
async def create_map_point(
    payload: MapPointCreateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.create_map_point(
            payload=_payload(payload),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        _raise_network_http(exc)


@router.patch("/map-points/{point_id}")
async def update_map_point(
    point_id: int,
    payload: MapPointUpdateRequest,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    try:
        return network_service.update_map_point(
            point_id=point_id,
            payload=_payload(payload, exclude_unset=True),
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
        )
    except ValueError as exc:
        _raise_network_http(exc)


@router.delete("/map-points/{point_id}")
async def delete_map_point(
    point_id: int,
    current_user: User = Depends(get_current_active_user),
):
    _ensure_write_role(current_user)
    ok = network_service.delete_map_point(
        point_id=point_id,
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Map point not found")
    return {"success": True}
