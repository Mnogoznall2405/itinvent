"""
Equipment API endpoints - search, retrieve and update equipment information.
"""
from typing import Optional, Any, List

from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel, Field
import os
import re

from backend.api.deps import get_current_active_user, get_current_database_id, require_permission
from backend.database import queries
from backend.database.connection import get_db
from backend.models.auth import User
from backend.services.authorization_service import PERM_DATABASE_WRITE
from backend.models.equipment import (
    EquipmentSearchResponse,
    EmployeeSearchResponse,
    EquipmentListResponse,
    Branch,
    Location,
    EquipmentType,
    EquipmentStatus,
    EquipmentCreateRequest,
    EquipmentCreateResponse,
    ConsumableCreateRequest,
    ConsumableCreateResponse,
    ConsumableLookupItem,
    ConsumableConsumeRequest,
    ConsumableConsumeResponse,
    ConsumableQtyUpdateRequest,
    ConsumableQtyUpdateResponse,
    TransferExecuteRequest,
    TransferExecuteResponse,
    TransferEmailRequest,
    TransferEmailResult,
    UploadedActDraftResponse,
    UploadedActCommitRequest,
    UploadedActCommitResponse,
    UploadedActEmailSendRequest,
    UploadedActEmailSendResponse,
)
from backend.services.transfer_service import (
    generate_transfer_acts,
    get_act_record,
    send_transfer_acts_email,
    send_binary_file_email,
)
from backend.services.act_upload_service import (
    DraftNotFoundError,
    DraftValidationError,
    DuplicateActError,
    create_uploaded_act_draft,
    get_uploaded_act_draft,
    commit_uploaded_act_draft,
)
import urllib.parse


router = APIRouter()


def _to_int(value: Any) -> Optional[int]:
    """Safely convert value to int."""
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ascii_safe_filename(file_name: str) -> str:
    """
    Build latin-1-safe fallback filename for HTTP headers.
    Keep original UTF-8 name in filename* parameter.
    """
    name = str(file_name or "").strip() or "act_file.bin"
    base, ext = os.path.splitext(name)
    safe_base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-") or "act_file"
    safe_ext = re.sub(r"[^A-Za-z0-9.]+", "", ext)
    if not safe_ext:
        safe_ext = ".bin"
    return f"{safe_base}{safe_ext}"


def _infer_mime_from_bytes(file_bytes: bytes) -> Optional[str]:
    """Best-effort MIME detection by magic bytes."""
    if not file_bytes:
        return None
    head = file_bytes[:16]
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xFF\xD8\xFF"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    return None


def _is_valid_mime_type(value: Optional[str]) -> bool:
    text = str(value or "").strip().lower()
    return bool(text and "/" in text and " " not in text)


def _normalize_local_file_path(raw_path: str) -> str:
    """
    Normalize file path from DB for local filesystem access.
    Supports plain paths and file:// URI format from legacy desktop app.
    """
    text = str(raw_path or "").strip()
    if not text:
        return ""

    lowered = text.lower()
    if lowered.startswith("file://"):
        parsed = urllib.parse.urlparse(text)
        path = urllib.parse.unquote(parsed.path or "")
        netloc = str(parsed.netloc or "").strip()

        # file://server/share/path -> UNC
        if netloc and netloc.lower() != "localhost":
            unc = f"\\\\{netloc}{path}"
            return os.path.normpath(unc.replace("/", "\\"))

        # file:///C:/path -> C:\path
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        return os.path.normpath(path.replace("/", os.sep))

    # Also decode URL-escaped plain path fragments, if present.
    return os.path.normpath(urllib.parse.unquote(text))


def _resolve_owner_no_by_name(owner_name: str, db_id: Optional[str]) -> Optional[int]:
    name = str(owner_name or "").strip()
    if not name:
        return None
    owner_no = queries.get_owner_no_by_name(name, strict=True, db_id=db_id)
    if owner_no is None:
        owner_no = queries.get_owner_no_by_name(name, strict=False, db_id=db_id)
    return int(owner_no) if owner_no is not None else None


class EquipmentUpdateRequest(BaseModel):
    """Partial update payload for equipment card."""
    serial_no: Optional[str] = Field(default=None)
    hw_serial_no: Optional[str] = Field(default=None)
    part_no: Optional[str] = Field(default=None)
    ip_address: Optional[str] = Field(default=None)
    mac_address: Optional[str] = Field(default=None)
    network_name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    status_no: Optional[int] = Field(default=None)
    empl_no: Optional[int] = Field(default=None)
    branch_no: Optional[Any] = Field(default=None)
    loc_no: Optional[Any] = Field(default=None)
    type_no: Optional[int] = Field(default=None)
    model_no: Optional[int] = Field(default=None)


class EquipmentByInvNosRequest(BaseModel):
    """Batch load equipment cards by inventory numbers."""
    inv_nos: List[str] = Field(..., min_length=1, max_length=500)


@router.get("/search/serial", response_model=EquipmentSearchResponse)
async def search_by_serial(
    q: str = Query(..., min_length=1, description="Serial number or inventory number to search"),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Search equipment by serial number, hardware serial, or inventory number.

    Args:
        q: Search term - serial number or inventory number

    Returns:
        EquipmentSearchResponse with found flag and equipment list
    """
    if not q or len(q.strip()) == 0:
        return EquipmentSearchResponse(found=False, equipment=[])

    results = queries.search_equipment_by_serial(q, db_id)

    return EquipmentSearchResponse(
        found=len(results) > 0,
        equipment=results
    )


@router.get("/search/universal")
async def search_universal(
    q: str = Query(..., min_length=1, description="Search term"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Universal search across all equipment fields.

    Args:
        q: Search term
        page: Page number
        limit: Results per page

    Returns:
        Equipment list with pagination
    """
    if not q or len(q.strip()) == 0:
        return {"equipment": [], "total": 0, "page": 1, "pages": 0}

    return queries.search_equipment_universal(q, page, limit, db_id)


@router.get("/search/employee", response_model=EmployeeSearchResponse)
async def search_by_employee(
    q: str = Query(..., min_length=1, description="Employee name or department"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Search employees by name or department.

    Args:
        q: Search term - employee name or department
        page: Page number (1-indexed)
        limit: Number of results per page

    Returns:
        EmployeeSearchResponse with paginated results
    """
    if not q or len(q.strip()) == 0:
        return EmployeeSearchResponse(employees=[], total=0, page=page, pages=0)

    results = queries.search_employees(q, page, limit, db_id)

    return EmployeeSearchResponse(**results)


@router.get("/employee/{owner_no}/items", response_model=EquipmentSearchResponse)
async def get_employee_equipment(
    owner_no: int,
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get all equipment assigned to a specific employee.

    Args:
        owner_no: Employee ID (OWNER_NO)

    Returns:
        EquipmentSearchResponse with employee's equipment
    """
    equipment = queries.get_equipment_by_owner(owner_no, db_id)

    return EquipmentSearchResponse(
        found=len(equipment) > 0,
        equipment=equipment
    )


@router.get("/database", response_model=EquipmentListResponse)
async def get_all_equipment(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get all equipment from database with pagination.

    Args:
        page: Page number (1-indexed)
        limit: Number of results per page

    Returns:
        EquipmentListResponse with paginated equipment list
    """
    result = queries.get_all_equipment(page, limit, db_id)

    return EquipmentListResponse(**result)


@router.post("/by-inv-nos")
async def get_equipment_by_inv_nos(
    payload: EquipmentByInvNosRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user),
):
    """
    Batch load equipment cards by inventory numbers.
    Used by frontend bulk operations to avoid N+1 requests.
    """
    normalized_inv_nos: List[str] = []
    for raw_inv_no in payload.inv_nos or []:
        inv_no = str(raw_inv_no or "").strip()
        if inv_no and inv_no not in normalized_inv_nos:
            normalized_inv_nos.append(inv_no)

    if not normalized_inv_nos:
        return {"equipment": [], "not_found": [], "requested": 0}

    equipment: List[dict] = []
    not_found: List[str] = []
    for inv_no in normalized_inv_nos:
        row = queries.get_equipment_by_inv(inv_no, db_id)
        if row:
            equipment.append(row)
        else:
            not_found.append(inv_no)

    return {
        "equipment": equipment,
        "not_found": not_found,
        "requested": len(normalized_inv_nos),
    }


@router.get("/branches", response_model=list[Branch])
async def get_branches(
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get all available branches.

    Returns:
        List of branches
    """
    return queries.get_all_branches(db_id)


@router.get("/locations/{branch_id}", response_model=list[Location])
async def get_locations(
    branch_id: str,
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get locations for a specific branch.

    Args:
        branch_id: Branch ID

    Returns:
        List of locations for the branch
    """
    return queries.get_locations_by_branch(branch_id, db_id)


@router.get("/types")
async def get_equipment_types(
    ci_type: Optional[int] = Query(None, ge=1, le=20, description="Filter by CI_TYPE"),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get all equipment types.

    Returns:
        List of equipment types
    """
    from backend.database.equipment_db import get_all_equipment_types
    types = get_all_equipment_types(db_id)
    if ci_type is not None:
        filtered = []
        for entry in types or []:
            current_ci_type = _to_int(entry.get("CI_TYPE") if isinstance(entry, dict) else None)
            if current_ci_type is None:
                current_ci_type = _to_int(entry.get("ci_type") if isinstance(entry, dict) else None)
            if current_ci_type == ci_type:
                filtered.append(entry)
        return filtered
    return types


@router.get("/models")
async def get_models_by_type(
    type_no: int = Query(..., ge=1, description="Equipment TYPE_NO"),
    ci_type: int = Query(1, ge=1, le=20, description="CI_TYPE category"),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user),
):
    """
    Get equipment models for a selected type.
    """
    return {"models": queries.get_models_by_type(type_no, db_id, ci_type=ci_type)}


@router.get("/types-raw")
async def get_equipment_types_raw(
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get all equipment types using direct SQL query.
    Returns raw data from CI_TYPES table.

    SQL Query:
        SELECT CI_TYPE, TYPE_NO, TYPE_NAME
        FROM CI_TYPES
        ORDER BY TYPE_NAME
    """
    from backend.database.connection import get_db
    db = get_db(db_id)

    # Прямой SQL запрос для получения типов оборудования
    query = """
        SELECT
            CI_TYPE,
            TYPE_NO,
            TYPE_NAME
        FROM CI_TYPES
        ORDER BY TYPE_NAME
    """

    try:
        results = db.execute_query(query, ())
        return {
            "success": True,
            "query": query.strip(),
            "count": len(results),
            "types": results
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error fetching types: {e}")
        return {
            "success": False,
            "error": str(e),
            "types": []
        }


@router.get("/statuses", response_model=list[EquipmentStatus])
async def get_statuses(
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get all equipment statuses.

    Returns:
        List of equipment statuses
    """
    return queries.get_all_statuses(db_id)


@router.get("/owners/search")
async def search_owners(
    q: str = Query(..., min_length=1, description="Owner name or department"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user),
):
    """
    Search owners for equipment reassignment/autocomplete.
    """
    term = (q or "").strip()
    if not term:
        return {"owners": []}
    return {"owners": queries.search_owners(term, limit, db_id)}


@router.get("/owners/departments")
async def get_owner_departments(
    limit: int = Query(500, ge=1, le=2000, description="Maximum number of departments"),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user),
):
    """
    Get distinct owner departments for dropdown controls.
    """
    return {"departments": queries.get_owner_departments(limit, db_id)}


@router.get("/all-grouped")
async def get_all_equipment_grouped(
    page: int = Query(1, ge=1),
    limit: int = Query(1000, ge=1, le=10000),
    branch: Optional[str] = Query(None),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get all equipment grouped by branch and location.

    Args:
        page: Page number
        limit: Results per page
        branch: Filter by branch name (optional)

    Returns:
        Equipment grouped by branch and location
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.debug("get_all_equipment_grouped branch=%s db_id=%s", branch, db_id)

    from backend.database.equipment_db import get_equipment_grouped, get_equipment_by_branch

    try:
        if branch:
            logger.debug("Fetching equipment for branch=%s", branch)
            result = get_equipment_by_branch(branch, page, limit, db_id)
            grouped_by_location = {}
            for item in result['equipment']:
                location = item.get('location') or 'Не указано'
                if location not in grouped_by_location:
                    grouped_by_location[location] = []
                grouped_by_location[location].append(item)

            grouped = {
                branch: grouped_by_location
            }
            logger.debug("Returning grouped data branch=%s locations=%s", branch, len(grouped_by_location))
            return {
                'grouped': grouped,
                'total': result['total'],
                'page': result['page'],
                'pages': result['pages']
            }

        logger.debug("Fetching all equipment grouped")
        return get_equipment_grouped(page, limit, db_id)
    except Exception as e:
        logger.error(f"Error in get_all_equipment_grouped: {e}", exc_info=True)
        raise


@router.get("/consumables-grouped")
async def get_all_consumables_grouped(
    page: int = Query(1, ge=1),
    limit: int = Query(1000, ge=1, le=10000),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get consumables (CI_TYPE = 4) grouped by branch and location.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.debug("get_all_consumables_grouped db_id=%s", db_id)

    from backend.database.equipment_db import get_consumables_grouped

    try:
        return get_consumables_grouped(page, limit, db_id)
    except Exception as e:
        logger.error(f"Error in get_all_consumables_grouped: {e}", exc_info=True)
        raise


@router.get("/consumables/lookup", response_model=List[ConsumableLookupItem])
async def get_consumables_lookup(
    type_no: Optional[int] = Query(None, ge=1),
    model_name: Optional[str] = Query(None, min_length=1),
    branch_no: Optional[str] = Query(None),
    loc_no: Optional[str] = Query(None),
    only_positive_qty: bool = Query(True),
    limit: int = Query(300, ge=1, le=1000),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user),
):
    """Lookup consumables with branch and location metadata."""
    import logging
    logger = logging.getLogger(__name__)

    def _to_int_like(value: Any) -> Optional[int]:
        if value in (None, "", "null"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(str(value).strip()))
            except (TypeError, ValueError):
                return None

    def _to_opt_str(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    def _normalize_lookup_row(row: Any) -> Optional[dict]:
        if not isinstance(row, dict):
            return None

        raw_id = row.get("id", row.get("ID"))
        normalized_id = _to_int_like(raw_id)
        if normalized_id is None:
            return None

        raw_branch_no = row.get("branch_no", row.get("BRANCH_NO"))
        raw_loc_no = row.get("loc_no", row.get("LOC_NO"))
        branch_as_int = _to_int_like(raw_branch_no)
        loc_as_int = _to_int_like(raw_loc_no)

        qty_value = _to_int_like(row.get("qty", row.get("QTY")))
        if qty_value is None:
            qty_value = 0

        return {
            "id": normalized_id,
            "inv_no": _to_opt_str(row.get("inv_no", row.get("INV_NO"))),
            "type_no": _to_int_like(row.get("type_no", row.get("TYPE_NO"))),
            "type_name": _to_opt_str(row.get("type_name", row.get("TYPE_NAME"))),
            "model_no": _to_int_like(row.get("model_no", row.get("MODEL_NO"))),
            "model_name": _to_opt_str(row.get("model_name", row.get("MODEL_NAME"))),
            "qty": qty_value,
            "branch_no": branch_as_int if branch_as_int is not None else _to_opt_str(raw_branch_no),
            "branch_name": _to_opt_str(row.get("branch_name", row.get("BRANCH_NAME"))),
            "loc_no": loc_as_int if loc_as_int is not None else _to_opt_str(raw_loc_no),
            "location_name": _to_opt_str(
                row.get("location_name", row.get("LOCATION_NAME", row.get("location", row.get("LOCATION"))))
            ),
            "part_no": _to_opt_str(row.get("part_no", row.get("PART_NO"))),
            "description": _to_opt_str(row.get("description", row.get("DESCRIPTION"))),
        }

    def _normalize_rows(rows: Any) -> List[dict]:
        normalized: List[dict] = []
        for row in rows or []:
            parsed = _normalize_lookup_row(row)
            if parsed:
                normalized.append(parsed)
        return normalized

    branch_value: Optional[Any] = branch_no
    loc_value: Optional[Any] = loc_no

    if branch_no not in (None, ""):
        branch_int = _to_int(branch_no)
        branch_value = branch_int if branch_int is not None else branch_no
    if loc_no not in (None, ""):
        loc_int = _to_int(loc_no)
        loc_value = loc_int if loc_int is not None else loc_no

    rows: List[dict] = []
    try:
        lookup_rows = queries.get_consumables_lookup(
            db_id=db_id,
            type_no=type_no,
            model_name=(model_name or "").strip() or None,
            branch_no=branch_value,
            loc_no=loc_value,
            only_positive_qty=only_positive_qty,
            limit=limit,
        )
        rows = _normalize_rows(lookup_rows)
    except Exception as exc:
        logger.warning("consumables_lookup primary query failed db_id=%s: %s", db_id, exc, exc_info=True)

    if rows:
        return rows

    # Fallback: use grouped consumables source and flatten to lookup shape.
    try:
        from backend.database.equipment_db import get_consumables_grouped

        grouped_payload = get_consumables_grouped(page=1, limit=1000, db_id=db_id)
        grouped = grouped_payload.get("grouped") if isinstance(grouped_payload, dict) else {}
        flat_rows: List[dict] = []
        if isinstance(grouped, dict):
            for locations in grouped.values():
                if not isinstance(locations, dict):
                    continue
                for items in locations.values():
                    if isinstance(items, list):
                        flat_rows.extend(items)
        return _normalize_rows(flat_rows)
    except Exception as exc:
        logger.error("consumables_lookup fallback failed db_id=%s: %s", db_id, exc, exc_info=True)
        return []


@router.post("/consumables/create", response_model=ConsumableCreateResponse)
async def create_consumable(
    payload: ConsumableCreateRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Create new consumable item (CI_TYPE=4)."""
    branch_no = payload.branch_no
    loc_no = payload.loc_no
    type_no = _to_int(payload.type_no)
    status_no = _to_int(payload.status_no)
    model_no = _to_int(payload.model_no)
    model_name = str(payload.model_name or "").strip()
    qty = _to_int(payload.qty)

    if type_no is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="type_no is required")
    if qty is None or qty <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="qty must be greater than 0")
    if model_no is None and not model_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model_name is required when model_no is not provided")

    branch_row = queries.get_branch_by_no(branch_no, db_id)
    if not branch_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid branch_no")

    location_row = queries.get_location_by_no(loc_no, db_id)
    if not location_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid loc_no")

    if not queries.is_location_in_branch(loc_no, branch_no, db_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="loc_no does not belong to selected branch_no")

    type_row = queries.get_type_by_no(type_no, db_id, ci_type=4)
    if not type_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid type_no for consumables")

    if status_no is not None:
        status_row = queries.get_status_by_no(status_no, db_id)
        if not status_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status_no")

    if model_no is not None:
        model_row = queries.get_model_by_no(model_no, db_id, ci_type=4)
        if not model_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid model_no")
        model_type_no = _to_int(model_row.get("TYPE_NO") or model_row.get("type_no"))
        if model_type_no is not None and model_type_no != type_no:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model_no does not belong to selected type_no")

    changed_by = current_user.username if current_user else "IT-WEB"
    result = queries.create_consumable_item(
        branch_no=branch_no,
        loc_no=loc_no,
        type_no=type_no,
        qty=qty,
        model_name=model_name or None,
        model_no=model_no,
        status_no=status_no,
        part_no=(payload.part_no or "").strip() or None,
        description=(payload.description or "").strip() or None,
        changed_by=changed_by,
        db_id=db_id,
    )
    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message") or "Failed to create consumable")
    return ConsumableCreateResponse(**result)


@router.post("/consumables/consume", response_model=ConsumableConsumeResponse)
async def consume_consumable(
    payload: ConsumableConsumeRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Decrease consumable stock by qty."""
    item_id = _to_int(payload.item_id)
    inv_no = str(payload.inv_no or "").strip()
    qty = _to_int(payload.qty)
    if qty is None or qty <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="qty must be greater than 0")
    if item_id is None and not inv_no:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="item_id or inv_no is required")

    changed_by = current_user.username if current_user else "IT-WEB"
    result = queries.consume_consumable_stock(
        db_id=db_id,
        item_id=item_id,
        inv_no=inv_no or None,
        qty=qty,
        changed_by=changed_by,
    )
    if result.get("success"):
        return ConsumableConsumeResponse(**result)

    message = str(result.get("message") or "Failed to consume consumable")
    if message == "Consumable not found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    if message == "Insufficient consumable quantity":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


@router.patch("/consumables/qty", response_model=ConsumableQtyUpdateResponse)
async def update_consumable_qty(
    payload: ConsumableQtyUpdateRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Set exact consumable quantity."""
    item_id = _to_int(payload.item_id)
    inv_no = str(payload.inv_no or "").strip()
    qty = _to_int(payload.qty)
    if qty is None or qty < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="qty must be 0 or greater")
    if item_id is None and not inv_no:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="item_id or inv_no is required")

    changed_by = current_user.username if current_user else "IT-WEB"
    result = queries.set_consumable_stock_qty(
        db_id=db_id,
        item_id=item_id,
        inv_no=inv_no or None,
        qty=qty,
        changed_by=changed_by,
    )
    if result.get("success"):
        return ConsumableQtyUpdateResponse(**result)

    message = str(result.get("message") or "Failed to update consumable quantity")
    if message == "Consumable not found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


@router.get("/branches-list")
async def get_branches_list(
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get list of all branches.

    Returns:
        List of branches with BRANCH_NO and BRANCH_NAME
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.debug("Fetching branches for db_id=%s", db_id)
    from backend.database.equipment_db import get_all_branches
    branches = get_all_branches(db_id)
    logger.debug("Found %s branches", len(branches))
    return branches

@router.post("/create", response_model=EquipmentCreateResponse)
async def create_equipment(
    payload: EquipmentCreateRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """
    Create new equipment in ITEMS with automatic inventory number generation.
    Creates missing employee/model when needed.
    """
    serial_no = str(payload.serial_no or "").strip()
    employee_name = str(payload.employee_name or "").strip()
    model_name = str(payload.model_name or "").strip()
    branch_no = payload.branch_no
    loc_no = payload.loc_no
    type_no = _to_int(payload.type_no)
    status_no = _to_int(payload.status_no)
    model_no = _to_int(payload.model_no)
    employee_no = _to_int(payload.employee_no)

    if not serial_no:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="serial_no is required")
    if len(employee_name) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="employee_name is required")
    if type_no is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="type_no is required")
    if status_no is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status_no is required")
    if model_no is None and not model_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model_name is required when model_no is not provided")

    branch_row = queries.get_branch_by_no(branch_no, db_id)
    if not branch_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid branch_no")

    location_row = queries.get_location_by_no(loc_no, db_id)
    if not location_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid loc_no")

    if not queries.is_location_in_branch(loc_no, branch_no, db_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="loc_no does not belong to selected branch_no")

    type_row = queries.get_type_by_no(type_no, db_id)
    if not type_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid type_no")

    status_row = queries.get_status_by_no(status_no, db_id)
    if not status_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status_no")

    if model_no is not None:
        model_row = queries.get_model_by_no(model_no, db_id)
        if not model_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid model_no")
        model_type_no = _to_int(model_row.get("TYPE_NO") or model_row.get("type_no"))
        if model_type_no is not None and model_type_no != type_no:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model_no does not belong to selected type_no")

    if employee_no is not None:
        owner_row = queries.get_owner_by_no(employee_no, db_id)
        if not owner_row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid employee_no")

    changed_by = current_user.username if current_user else "IT-WEB"
    result = queries.create_equipment_item(
        serial_no=serial_no,
        employee_name=employee_name,
        branch_no=branch_no,
        loc_no=loc_no,
        type_no=type_no,
        status_no=status_no,
        model_name=model_name or None,
        model_no=model_no,
        employee_no=employee_no,
        employee_dept=(payload.employee_dept or "").strip() or None,
        hw_serial_no=(payload.hw_serial_no or "").strip() or None,
        part_no=(payload.part_no or "").strip() or None,
        description=(payload.description or "").strip() or None,
        ip_address=(payload.ip_address or "").strip() or None,
        changed_by=changed_by,
        db_id=db_id,
    )

    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message") or "Failed to create equipment")

    return EquipmentCreateResponse(**result)


@router.patch("/{inv_no}", response_model=dict)
async def update_equipment_by_inv(
    inv_no: str,
    payload: EquipmentUpdateRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """
    Partially update equipment card fields by inventory number.
    """
    if hasattr(payload, "model_dump"):
        updates = payload.model_dump(exclude_unset=True)  # Pydantic v2
    else:
        updates = payload.dict(exclude_unset=True)  # Pydantic v1 fallback

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    equipment = queries.get_equipment_by_inv(inv_no, db_id)
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment with inventory number {inv_no} not found",
        )

    # Validate status
    if "status_no" in updates and updates["status_no"] is not None:
        status_row = queries.get_status_by_no(int(updates["status_no"]), db_id)
        if not status_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status_no",
            )

    # Validate type
    if "type_no" in updates and updates["type_no"] is not None:
        type_row = queries.get_type_by_no(int(updates["type_no"]), db_id)
        if not type_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid type_no",
            )

    # Validate owner
    if "empl_no" in updates and updates["empl_no"] is not None:
        owner_row = queries.get_owner_by_no(int(updates["empl_no"]), db_id)
        if not owner_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid empl_no",
            )

    # Validate branch
    if "branch_no" in updates and updates["branch_no"] is not None:
        branch_row = queries.get_branch_by_no(updates["branch_no"], db_id)
        if not branch_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid branch_no",
            )

    # Validate location and branch-location pair
    if "loc_no" in updates and updates["loc_no"] is not None:
        location_row = queries.get_location_by_no(updates["loc_no"], db_id)
        if not location_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid loc_no",
            )

        target_branch = updates.get("branch_no")
        if target_branch is None:
            target_branch = equipment.get("branch_no")

        if target_branch is not None and not queries.is_location_in_branch(updates["loc_no"], target_branch, db_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="loc_no does not belong to selected branch_no",
            )

    # Validate model and type-model pair
    if "model_no" in updates and updates["model_no"] is not None:
        model_row = queries.get_model_by_no(int(updates["model_no"]), db_id)
        if not model_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid model_no",
            )

        target_type = _to_int(updates.get("type_no"))
        if target_type is None:
            target_type = _to_int(equipment.get("type_no"))

        model_type_no = _to_int(model_row.get("TYPE_NO") or model_row.get("type_no"))
        if target_type is not None and model_type_no is not None and target_type != model_type_no:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="model_no does not belong to selected type_no",
            )

    # If type changes and model is not explicitly set, clear model to avoid invalid pair
    if "type_no" in updates and "model_no" not in updates:
        current_model_no = _to_int(equipment.get("model_no"))
        target_type = _to_int(updates.get("type_no"))
        if current_model_no is not None and target_type is not None:
            current_model_row = queries.get_model_by_no(current_model_no, db_id)
            current_model_type_no = _to_int(
                (current_model_row or {}).get("TYPE_NO") or (current_model_row or {}).get("type_no")
            )
            if current_model_type_no is not None and current_model_type_no != target_type:
                updates["model_no"] = None

    # If branch changes and location is not explicitly set, keep data consistent
    if "branch_no" in updates and "loc_no" not in updates:
        current_loc_no = equipment.get("loc_no")
        target_branch = updates.get("branch_no")
        if current_loc_no is not None and target_branch is not None:
            if not queries.is_location_in_branch(current_loc_no, target_branch, db_id):
                updates["loc_no"] = None

    changed_by = current_user.username if current_user else "IT-WEB"
    updated = queries.update_equipment_fields(inv_no, updates, changed_by=changed_by, db_id=db_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update equipment",
        )

    equipment_after = queries.get_equipment_by_inv(inv_no, db_id)
    if not equipment_after:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Equipment updated but failed to read updated data",
        )

    return equipment_after


@router.post("/transfer", response_model=TransferExecuteResponse)
async def transfer_equipment(
    payload: TransferExecuteRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """
    Transfer one or multiple equipment items to another employee with CI_HISTORY logging.
    Generates transfer acts grouped by old employee.
    """
    inv_nos = []
    for raw in payload.inv_nos or []:
        normalized = str(raw or "").strip()
        if normalized and normalized not in inv_nos:
            inv_nos.append(normalized)
    if not inv_nos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No inventory numbers provided",
        )

    target_employee_name = (payload.new_employee or "").strip()
    target_employee_dept_input = (payload.new_employee_dept or "").strip()
    if len(target_employee_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="new_employee is required",
        )

    # Resolve/create target owner
    target_employee_no: Optional[int] = _to_int(payload.new_employee_no)
    if target_employee_no is not None:
        owner_row = queries.get_owner_by_no(target_employee_no, db_id)
        if not owner_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid new_employee_no",
            )
        target_employee_name = (
            owner_row.get("OWNER_DISPLAY_NAME")
            or owner_row.get("owner_display_name")
            or owner_row.get("employee_name")
            or target_employee_name
        )
    else:
        target_employee_no = queries.get_owner_no_by_name(target_employee_name, strict=True, db_id=db_id)
        if target_employee_no is None:
            target_employee_no = queries.get_owner_no_by_name(target_employee_name, strict=False, db_id=db_id)
        if target_employee_no is None:
            target_employee_no = queries.create_owner(
                target_employee_name,
                department=(target_employee_dept_input or None),
                db_id=db_id,
            )
        if target_employee_no is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to resolve or create target employee",
            )

    target_owner = queries.get_owner_by_no(target_employee_no, db_id) or {}
    target_employee_dept = (
        target_owner.get("OWNER_DEPT")
        or target_owner.get("owner_dept")
        or target_owner.get("employee_dept")
        or target_employee_dept_input
        or ""
    )
    target_employee_email = queries.get_owner_email_by_no(target_employee_no, db_id)

    target_branch_no = payload.branch_no
    target_loc_no = payload.loc_no

    if target_branch_no is not None:
        branch_row = queries.get_branch_by_no(target_branch_no, db_id)
        if not branch_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid branch_no",
            )

    if target_loc_no is not None:
        location_row = queries.get_location_by_no(target_loc_no, db_id)
        if not location_row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid loc_no",
            )
        if target_branch_no is not None and not queries.is_location_in_branch(target_loc_no, target_branch_no, db_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="loc_no does not belong to selected branch_no",
            )

    changed_by = current_user.username if current_user else "IT-WEB"
    transferred: list[dict] = []
    failed: list[dict] = []

    for inv_no in inv_nos:
        transfer_result = queries.transfer_equipment_by_inv_with_history(
            inv_no=inv_no,
            new_employee_no=target_employee_no,
            new_employee_name=target_employee_name,
            new_branch_no=target_branch_no,
            new_loc_no=target_loc_no,
            changed_by=changed_by,
            comment=payload.comment,
            db_id=db_id,
        )
        if transfer_result.get("success"):
            old_employee_no = transfer_result.get("old_employee_no")
            old_email = None
            if old_employee_no is not None:
                old_email = queries.get_owner_email_by_no(int(old_employee_no), db_id)
            transfer_result["old_employee_email"] = old_email
            transferred.append(transfer_result)
        else:
            failed.append(
                {
                    "inv_no": inv_no,
                    "error": transfer_result.get("message") or "Transfer failed",
                }
            )

    acts = []
    if transferred:
        acts = generate_transfer_acts(
            transferred_items=transferred,
            new_employee_name=target_employee_name,
            new_employee_dept=str(target_employee_dept or ""),
            new_employee_email=target_employee_email,
            db_id=db_id,
        )

    return TransferExecuteResponse(
        success_count=len(transferred),
        failed_count=len(failed),
        transferred=transferred,
        failed=failed,
        acts=acts,
    )


@router.post("/transfer/email", response_model=TransferEmailResult)
async def send_transfer_acts(
    payload: TransferEmailRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """
    Send generated transfer acts by email.
    """
    employee_email = None
    if payload.mode == "employee":
        owner_no = _to_int(payload.owner_no)
        if owner_no is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_no is required for employee mode",
            )
        employee_email = queries.get_owner_email_by_no(owner_no, db_id)
        if not employee_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected employee has no email",
            )

    result = await send_transfer_acts_email(
        act_ids=payload.act_ids,
        mode=payload.mode,
        manual_email=payload.manual_email,
        employee_email=employee_email,
    )
    return TransferEmailResult(**result)


@router.post("/acts/upload/parse", response_model=UploadedActDraftResponse)
async def parse_uploaded_act(
    file: UploadFile = File(..., description="Signed transfer act PDF"),
    manual_mode: bool = Query(
        False,
        description="Создать черновик без внешнего API-распознавания (ручное заполнение).",
    ),
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """
    Upload signed transfer act PDF and build parse draft.
    """
    file_name = str(file.filename or "").strip()
    if not file_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Имя файла не определено",
        )

    lower_name = file_name.lower()
    if not lower_name.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поддерживается только PDF",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл пустой",
        )

    max_size_mb = int(os.getenv("ACT_UPLOAD_MAX_SIZE_MB", "15"))
    max_size_bytes = max_size_mb * 1024 * 1024
    if len(file_bytes) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Размер файла превышает лимит {max_size_mb} МБ",
        )

    created_by = current_user.username if current_user else "IT-WEB"
    payload = create_uploaded_act_draft(
        file_bytes=file_bytes,
        file_name=file_name,
        db_id=db_id,
        created_by=created_by,
        skip_llm=manual_mode,
    )
    return UploadedActDraftResponse(**payload)


@router.get("/acts/upload/draft/{draft_id}", response_model=UploadedActDraftResponse)
async def get_uploaded_act_parse_draft(
    draft_id: str,
    db_id: Optional[str] = Depends(get_current_database_id),
    _: Optional[User] = Depends(get_current_active_user),
):
    """
    Get current parse draft payload.
    """
    try:
        payload = get_uploaded_act_draft(draft_id=draft_id, db_id=db_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DraftValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return UploadedActDraftResponse(**payload)


@router.post("/acts/upload/commit", response_model=UploadedActCommitResponse)
async def commit_uploaded_act(
    payload: UploadedActCommitRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """
    Commit uploaded act draft into DOCS + DOCS_LIST + FILES.
    """
    committed_by = current_user.username if current_user else "IT-WEB"
    if hasattr(payload, "model_dump"):
        payload_data = payload.model_dump()
    else:
        payload_data = payload.dict()
    try:
        result = commit_uploaded_act_draft(
            draft_id=payload.draft_id,
            payload=payload_data,
            db_id=db_id,
            committed_by=committed_by,
        )
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateActError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DraftValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    response_payload = {
        "success": True,
        "doc_no": int(result["doc_no"]),
        "doc_number": str(result["doc_number"]),
        "file_no": int(result["file_no"]),
        "linked_item_ids": [int(x) for x in result.get("linked_item_ids") or []],
        "linked_inv_nos": [str(x) for x in result.get("linked_inv_nos") or []],
        "message": "Акт успешно загружен и записан в базу",
    }
    return UploadedActCommitResponse(**response_payload)


@router.post("/acts/upload/email", response_model=UploadedActEmailSendResponse)
async def send_uploaded_act_email(
    payload: UploadedActEmailSendRequest,
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """
    Send uploaded act PDF by email.

    modes:
      - auto: recipients resolved by from_employee/to_employee
      - selected: recipients resolved by owner_nos list
    """
    doc_no = int(payload.doc_no)
    act_file_payload = queries.get_equipment_act_file(doc_no=doc_no, db_id=db_id)
    if not act_file_payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл акта не найден",
        )

    file_name = str(act_file_payload.get("file_name") or f"act_{doc_no}.pdf").strip()
    file_bytes = act_file_payload.get("file_bytes") or b""
    if not file_bytes:
        file_path = str(act_file_payload.get("file_path") or "").strip()
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as stream:
                file_bytes = stream.read()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не удалось получить бинарное содержимое акта для отправки",
            )

    subject = str(payload.subject or "").strip() or f"Акт №{doc_no}"
    body = str(payload.body or "").strip() or (
        f"Во вложении акт №{doc_no}.\n\nПисьмо сформировано автоматически системой IT Invent."
    )

    statuses: list[dict[str, Any]] = []
    resolved_recipients: list[tuple[int, str]] = []

    if payload.mode == "auto":
        employee_names = []
        for raw in [payload.from_employee, payload.to_employee]:
            name = str(raw or "").strip()
            if not name:
                continue
            if name.lower() not in [existing.lower() for existing in employee_names]:
                employee_names.append(name)

        if not employee_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Для авто-отправки укажите from_employee/to_employee",
            )

        for name in employee_names:
            owner_no = _resolve_owner_no_by_name(name, db_id)
            if owner_no is None:
                statuses.append(
                    {
                        "owner_no": None,
                        "employee_name": name,
                        "email": None,
                        "status": "not_found",
                        "detail": "Сотрудник не найден в базе",
                    }
                )
                continue
            owner_payload = queries.get_owner_by_no(owner_no, db_id) or {}
            owner_name = str(
                owner_payload.get("OWNER_DISPLAY_NAME")
                or owner_payload.get("owner_display_name")
                or name
            ).strip() or name
            resolved_recipients.append((int(owner_no), owner_name))
    else:
        normalized_owner_nos: list[int] = []
        for raw_owner_no in payload.owner_nos or []:
            owner_no = _to_int(raw_owner_no)
            if owner_no is None or owner_no <= 0:
                continue
            if owner_no not in normalized_owner_nos:
                normalized_owner_nos.append(owner_no)

        if not normalized_owner_nos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Выберите хотя бы одного сотрудника",
            )

        for owner_no in normalized_owner_nos:
            owner_payload = queries.get_owner_by_no(owner_no, db_id)
            if not owner_payload:
                statuses.append(
                    {
                        "owner_no": int(owner_no),
                        "employee_name": f"OWNER_NO {owner_no}",
                        "email": None,
                        "status": "not_found",
                        "detail": "Сотрудник не найден",
                    }
                )
                continue
            owner_name = str(
                owner_payload.get("OWNER_DISPLAY_NAME")
                or owner_payload.get("owner_display_name")
                or f"OWNER_NO {owner_no}"
            ).strip() or f"OWNER_NO {owner_no}"
            resolved_recipients.append((int(owner_no), owner_name))

    sent_owner_nos: set[int] = set()
    for owner_no, owner_name in resolved_recipients:
        if owner_no in sent_owner_nos:
            continue
        sent_owner_nos.add(owner_no)

        owner_email = queries.get_owner_email_by_no(owner_no, db_id)
        if not owner_email:
            statuses.append(
                {
                    "owner_no": int(owner_no),
                    "employee_name": owner_name,
                    "email": None,
                    "status": "missing_email",
                    "detail": "У сотрудника не указан email",
                }
            )
            continue

        sent = await send_binary_file_email(
            recipient_email=owner_email,
            file_name=file_name,
            file_bytes=bytes(file_bytes),
            subject=subject,
            body=body,
        )
        if sent:
            statuses.append(
                {
                    "owner_no": int(owner_no),
                    "employee_name": owner_name,
                    "email": owner_email,
                    "status": "sent",
                    "detail": "Отправлено",
                }
            )
        else:
            statuses.append(
                {
                    "owner_no": int(owner_no),
                    "employee_name": owner_name,
                    "email": owner_email,
                    "status": "error",
                    "detail": "Ошибка отправки SMTP",
                }
            )

    success_count = sum(1 for row in statuses if row.get("status") == "sent")
    failed_count = len(statuses) - success_count

    return UploadedActEmailSendResponse(
        doc_no=doc_no,
        subject=subject,
        success_count=success_count,
        failed_count=failed_count,
        recipients=statuses,
    )


@router.get("/acts/{doc_no}/file")
async def download_equipment_act_file(
    doc_no: str,
    item_id: Optional[int] = Query(None, description="Optional ITEM_ID for precise file lookup"),
    inv_no: Optional[str] = Query(None, description="Optional INV_NO for fallback item lookup"),
    db_override: Optional[str] = Query(None, alias="db_id", description="Admin-only DB override"),
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(get_current_active_user),
):
    """
    Download/open physical file linked to act/document.
    """
    effective_db_id = db_id
    if current_user.role == "admin" and db_override and db_override.strip():
        effective_db_id = db_override.strip()

    payload = queries.get_equipment_act_file(
        doc_no=doc_no,
        item_id=item_id,
        inv_no=inv_no,
        db_id=effective_db_id,
    )
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл для выбранного акта не найден",
        )

    file_path_raw = str(payload.get("file_path") or "").strip()
    if file_path_raw:
        candidate_paths: list[str] = []
        for candidate in (file_path_raw, _normalize_local_file_path(file_path_raw)):
            normalized = str(candidate or "").strip()
            if normalized and normalized not in candidate_paths:
                candidate_paths.append(normalized)

        for candidate in candidate_paths:
            if os.path.exists(candidate):
                file_name = str(payload.get("file_name") or os.path.basename(candidate) or f"act_{doc_no}.bin")
                return FileResponse(path=candidate, filename=file_name)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Файл не найден по пути: {file_path_raw}",
        )

    file_url = str(payload.get("file_url") or "").strip()
    if file_url:
        return RedirectResponse(url=file_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    file_bytes = payload.get("file_bytes") or b""
    file_name = str(payload.get("file_name") or f"act_{doc_no}.bin")
    content_type = str(payload.get("content_type") or "application/octet-stream")
    inferred_type = _infer_mime_from_bytes(file_bytes)
    if inferred_type and (
        (not _is_valid_mime_type(content_type))
        or content_type.startswith("text/")
        or content_type == "application/octet-stream"
    ):
        content_type = inferred_type
    if inferred_type == "application/pdf" and "." not in os.path.basename(file_name):
        file_name = f"{file_name}.pdf"

    ascii_name = _ascii_safe_filename(file_name)
    encoded_name = urllib.parse.quote(file_name, safe="")
    headers = {
        "Content-Disposition": f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}",
        "X-Act-Source": str(payload.get("source_table") or ""),
        "X-Act-Storage": str(payload.get("storage") or ""),
    }
    return StreamingResponse(iter([file_bytes]), media_type=content_type, headers=headers)


@router.get("/acts/{doc_no}/inspect")
async def inspect_equipment_act_file(
    doc_no: str,
    item_id: Optional[int] = Query(None, description="Optional ITEM_ID for precise file lookup"),
    inv_no: Optional[str] = Query(None, description="Optional INV_NO for fallback item lookup"),
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user),
):
    """
    Debug endpoint: inspect FILES/DOCS storage for act/document.
    """
    return queries.inspect_equipment_act_storage(
        doc_no=doc_no,
        item_id=item_id,
        inv_no=inv_no,
        db_id=db_id,
    )


@router.get("/{inv_no}/acts")
async def get_equipment_acts(
    inv_no: str,
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user),
):
    """
    Get acts/documents linked to an equipment item by inventory number.
    """
    equipment = queries.get_equipment_by_inv(inv_no, db_id)
    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment with inventory number {inv_no} not found",
        )

    acts_payload = queries.get_equipment_acts_by_inv(inv_no, db_id)
    acts = acts_payload.get("acts") or []
    return {
        "inv_no": str(inv_no),
        "item_id": acts_payload.get("item_id"),
        "total": len(acts),
        "current_act": acts[0] if acts else None,
        "acts": acts,
    }


@router.get("/transfer/act/{act_id}")
async def download_transfer_act(
    act_id: str,
    _: Optional[User] = Depends(get_current_active_user),
):
    """
    Download generated transfer act file by act_id.
    """
    record = get_act_record(act_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Act not found",
        )

    file_path = str(record.get("file_path") or "")
    file_name = str(record.get("file_name") or "transfer_act")
    file_type = str(record.get("file_type") or "").lower()
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Act file path is empty",
        )

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Act file not found on disk",
        )

    media_type = (
        "application/pdf"
        if file_type == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path=file_path, filename=file_name, media_type=media_type)


# IMPORTANT: This catch-all route must be LAST to avoid intercepting other routes
@router.get("/{inv_no}", response_model=dict)
async def get_equipment_by_inv(
    inv_no: str,
    db_id: Optional[str] = Depends(get_current_database_id),
    _: User = Depends(get_current_active_user)
):
    """
    Get detailed equipment information by inventory number.

    Args:
        inv_no: Inventory number

    Returns:
        Equipment details dict

    Raises:
        HTTPException 404 if equipment not found
    """
    equipment = queries.get_equipment_by_inv(inv_no, db_id)

    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment with inventory number {inv_no} not found"
        )

    return equipment
