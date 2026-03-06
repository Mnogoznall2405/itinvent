#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON Operations API endpoints.

Provides REST API endpoints for working with JSON data files
that are shared with the Telegram bot.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, status
from fastapi.responses import JSONResponse, StreamingResponse

from backend.models.json_operations import (
    # Unfound equipment
    UnfoundEquipmentCreate,
    UnfoundEquipmentResponse,
    # Transfers
    TransferCreate,
    TransferResponse,
    BulkTransferRequest,
    # Cartridge replacements
    CartridgeReplacementCreate,
    CartridgeReplacementResponse,
    # Battery replacements
    BatteryReplacementCreate,
    BatteryReplacementResponse,
    # Component replacements
    ComponentReplacementCreate,
    ComponentReplacementResponse,
    # PC cleanings
    PcCleaningCreate,
    PcCleaningResponse,
    PcCleaningHistoryResponse,
    PcCleaningStatisticsResponse,
    MfuStatisticsResponse,
    BatteryStatisticsResponse,
    PcComponentsStatisticsResponse,
    CartridgeReplacementHistoryResponse,
    BatteryReplacementHistoryResponse,
    ComponentReplacementHistoryResponse,
    # Cartridge database
    PrinterCompatibilityResponse,
    CartridgeColorsResponse,
    PrinterComponentsResponse,
    CartridgeInfoResponse,
    # Bulk operations
    BulkWorkRequest,
    BulkOperationResponse,
    # Statistics
    UnfoundStatisticsResponse,
    TransferStatisticsResponse,
    WorksStatisticsResponse,
)

from backend.json_db.unfound import UnfoundEquipmentManager
from backend.json_db.transfers import TransferManager
from backend.json_db.works import WorksManager
from backend.json_db.cartridges import CartridgeDatabase, CartridgeInfo
from backend.services.excel_export_service import build_statistics_excel
from backend.services.authorization_service import PERM_DATABASE_WRITE
from backend.models.auth import User

from backend.api.deps import get_current_active_user, get_current_database_id, require_permission

logger = logging.getLogger(__name__)

router = APIRouter()

# ========== Initialize Managers ==========

def get_unfound_manager():
    """Dependency injection for UnfoundEquipmentManager."""
    return UnfoundEquipmentManager()

def get_transfer_manager():
    """Dependency injection for TransferManager."""
    return TransferManager()

def get_works_manager():
    """Dependency injection for WorksManager."""
    return WorksManager()

def get_cartridge_database():
    """Dependency injection for CartridgeDatabase."""
    return CartridgeDatabase()


# ========== Unfound Equipment Endpoints ==========

@router.post("/unfound", response_model=UnfoundEquipmentResponse, status_code=status.HTTP_201_CREATED)
async def add_unfound_equipment(
    data: UnfoundEquipmentCreate,
    manager: UnfoundEquipmentManager = Depends(get_unfound_manager),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Add a new unfound equipment record."""
    try:
        record = manager.add_unfound_equipment(
            serial_number=data.serial_number,
            model_name=data.model_name,
            employee_name=data.employee_name,
            brand_name=data.brand_name,
            location=data.location,
            equipment_type=data.equipment_type,
            description=data.description,
            inventory_number=data.inventory_number,
            batch_number=data.batch_number,
            ip_address=data.ip_address,
            status=data.status,
            branch=data.branch,
            company=data.company,
            db_name=data.db_name,
            additional_data=data.additional_data,
        )
        return UnfoundEquipmentResponse(**record)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding unfound equipment: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/unfound", response_model=List[UnfoundEquipmentResponse])
async def get_unfound_equipment(
    db_name: Optional[str] = None,
    branch: Optional[str] = None,
    employee: Optional[str] = None,
    limit: Optional[int] = None,
    manager: UnfoundEquipmentManager = Depends(get_unfound_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get unfound equipment records with optional filtering."""
    try:
        records = manager.get_unfound_equipment(
            db_name=db_name,
            branch=branch,
            employee=employee,
            limit=limit,
        )
        return [UnfoundEquipmentResponse(**r) for r in records]
    except Exception as e:
        logger.error(f"Error getting unfound equipment: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/unfound/statistics", response_model=UnfoundStatisticsResponse)
async def get_unfound_statistics(
    manager: UnfoundEquipmentManager = Depends(get_unfound_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get statistics about unfound equipment."""
    try:
        stats = manager.get_unfound_statistics()
        return UnfoundStatisticsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting unfound statistics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


# ========== Transfer Endpoints ==========

@router.post("/transfers", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
async def add_transfer(
    data: TransferCreate,
    manager: TransferManager = Depends(get_transfer_manager),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Add a new equipment transfer record."""
    try:
        record = manager.add_transfer(
            serial_number=data.serial_number,
            new_employee=data.new_employee,
            old_employee=data.old_employee,
            inv_no=data.inv_no,
            branch=data.branch,
            location=data.location,
            db_name=data.db_name,
            act_pdf_path=data.act_pdf_path,
            additional_data=data.additional_data,
        )
        return TransferResponse(**record)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding transfer: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/transfers", response_model=List[TransferResponse])
async def get_transfers(
    db_name: Optional[str] = None,
    branch: Optional[str] = None,
    employee: Optional[str] = None,
    serial_number: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: Optional[int] = None,
    manager: TransferManager = Depends(get_transfer_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get equipment transfer records with optional filtering."""
    try:
        records = manager.get_transfers(
            db_name=db_name,
            branch=branch,
            employee=employee,
            serial_number=serial_number,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )
        return [TransferResponse(**r) for r in records]
    except Exception as e:
        logger.error(f"Error getting transfers: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post("/transfers/bulk", response_model=BulkOperationResponse)
async def bulk_transfer(
    data: BulkTransferRequest,
    manager: TransferManager = Depends(get_transfer_manager),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Bulk transfer multiple items to a new employee."""
    success_count = 0
    failed_count = 0
    errors = []

    for item in data.items:
        try:
            manager.add_transfer(
                serial_number=item.get('serial_number', ''),
                new_employee=data.new_employee,
                old_employee=item.get('employee'),
                inv_no=item.get('inv_no'),
                branch=data.branch or item.get('branch'),
                location=data.location or item.get('location'),
                db_name=data.db_name,
                additional_data=item.get('additional_data', {}),
            )
            success_count += 1
        except Exception as e:
            failed_count += 1
            errors.append(f"{item.get('serial_number', 'unknown')}: {str(e)}")

    return BulkOperationResponse(
        success_count=success_count,
        failed_count=failed_count,
        errors=errors,
    )


@router.get("/transfers/statistics", response_model=TransferStatisticsResponse)
async def get_transfer_statistics(
    manager: TransferManager = Depends(get_transfer_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get statistics about equipment transfers."""
    try:
        stats = manager.get_transfer_statistics()
        return TransferStatisticsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting transfer statistics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


# ========== Cartridge Replacement Endpoints ==========

@router.post("/works/cartridge", response_model=CartridgeReplacementResponse, status_code=status.HTTP_201_CREATED)
async def add_cartridge_replacement(
    data: CartridgeReplacementCreate,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Add a cartridge replacement record."""
    try:
        record = manager.add_cartridge_replacement(
            printer_model=data.printer_model,
            cartridge_color=data.cartridge_color,
            component_type=data.component_type,
            component_color=data.component_color,
            cartridge_model=data.cartridge_model,
            detection_source=data.detection_source,
            printer_is_color=data.printer_is_color,
            branch=data.branch,
            location=data.location,
            serial_number=data.serial_number,
            inv_no=data.inv_no,
            db_name=data.db_name,
            additional_data=data.additional_data,
            equipment_id=data.equipment_id,
            current_description=data.current_description,
            hw_serial_no=data.hw_serial_no,
            model_name=data.model_name,
            manufacturer=data.manufacturer,
            employee=data.employee,
        )
        return CartridgeReplacementResponse(**record)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding cartridge replacement: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/cartridge", response_model=List[CartridgeReplacementResponse])
async def get_cartridge_replacements(
    db_name: Optional[str] = None,
    branch: Optional[str] = None,
    location: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: Optional[int] = None,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get cartridge replacement records with optional filtering."""
    try:
        records = manager.get_cartridge_replacements(
            db_name=db_name,
            branch=branch,
            location=location,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )
        return [CartridgeReplacementResponse(**r) for r in records]
    except Exception as e:
        logger.error(f"Error getting cartridge replacements: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/cartridge/history", response_model=CartridgeReplacementHistoryResponse)
async def get_cartridge_replacement_history(
    serial_number: Optional[str] = None,
    hw_serial_number: Optional[str] = None,
    inv_no: Optional[str] = None,
    cartridge_color: Optional[str] = None,
    cartridge_model: Optional[str] = None,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get cartridge replacement history for a specific equipment item."""
    try:
        history = manager.get_cartridge_replacement_history(
            serial_number=serial_number,
            hw_serial_number=hw_serial_number,
            inv_no=inv_no,
            cartridge_color=cartridge_color,
            cartridge_model=cartridge_model,
        )
        return CartridgeReplacementHistoryResponse(**history)
    except Exception as e:
        logger.error(f"Error getting cartridge replacement history: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


# ========== Battery Replacement Endpoints ==========

@router.post("/works/battery", response_model=BatteryReplacementResponse, status_code=status.HTTP_201_CREATED)
async def add_battery_replacement(
    data: BatteryReplacementCreate,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Add a battery replacement record."""
    try:
        record = manager.add_battery_replacement(
            serial_number=data.serial_number,
            branch=data.branch,
            location=data.location,
            inv_no=data.inv_no,
            db_name=data.db_name,
            additional_data=data.additional_data,
            equipment_id=data.equipment_id,
            current_description=data.current_description,
            hw_serial_no=data.hw_serial_no,
            model_name=data.model_name,
            manufacturer=data.manufacturer,
            employee=data.employee,
        )
        return BatteryReplacementResponse(**record)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding battery replacement: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/battery", response_model=List[BatteryReplacementResponse])
async def get_battery_replacements(
    db_name: Optional[str] = None,
    branch: Optional[str] = None,
    serial_number: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: Optional[int] = None,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get battery replacement records with optional filtering."""
    try:
        records = manager.get_battery_replacements(
            db_name=db_name,
            branch=branch,
            serial_number=serial_number,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )
        return [BatteryReplacementResponse(**r) for r in records]
    except Exception as e:
        logger.error(f"Error getting battery replacements: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/battery/history", response_model=BatteryReplacementHistoryResponse)
async def get_battery_replacement_history(
    serial_number: str,
    hw_serial_number: Optional[str] = None,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get battery replacement history for a specific serial number."""
    try:
        history = manager.get_battery_replacement_history(
            serial_number=serial_number,
            hw_serial_number=hw_serial_number,
        )
        return BatteryReplacementHistoryResponse(**history)
    except Exception as e:
        logger.error(f"Error getting battery replacement history: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


# ========== Component Replacement Endpoints ==========

@router.post("/works/component", response_model=ComponentReplacementResponse, status_code=status.HTTP_201_CREATED)
async def add_component_replacement(
    data: ComponentReplacementCreate,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Add a component replacement record."""
    try:
        record = manager.add_component_replacement(
            serial_number=data.serial_number,
            component_type=data.component_type,
            component_model=data.component_model,
            branch=data.branch,
            location=data.location,
            inv_no=data.inv_no,
            db_name=data.db_name,
            additional_data=data.additional_data,
            equipment_id=data.equipment_id,
            current_description=data.current_description,
            hw_serial_no=data.hw_serial_no,
            model_name=data.model_name,
            manufacturer=data.manufacturer,
            employee=data.employee,
            component_name=data.component_name,
            equipment_kind=data.equipment_kind,
        )
        return ComponentReplacementResponse(**record)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding component replacement: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/component", response_model=List[ComponentReplacementResponse])
async def get_component_replacements(
    db_name: Optional[str] = None,
    branch: Optional[str] = None,
    component_type: Optional[str] = None,
    serial_number: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: Optional[int] = None,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get component replacement records with optional filtering."""
    try:
        records = manager.get_component_replacements(
            db_name=db_name,
            branch=branch,
            component_type=component_type,
            serial_number=serial_number,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )
        return [ComponentReplacementResponse(**r) for r in records]
    except Exception as e:
        logger.error(f"Error getting component replacements: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/component/history", response_model=ComponentReplacementHistoryResponse)
async def get_component_replacement_history(
    serial_number: str,
    hw_serial_number: Optional[str] = None,
    component_type: Optional[str] = None,
    component_name: Optional[str] = None,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get component replacement history for a specific serial number and component."""
    try:
        history = manager.get_component_replacement_history(
            serial_number=serial_number,
            hw_serial_number=hw_serial_number,
            component_type=component_type,
            component_name=component_name,
        )
        return ComponentReplacementHistoryResponse(**history)
    except Exception as e:
        logger.error(f"Error getting component replacement history: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


# ========== PC Cleaning Endpoints ==========

@router.post("/works/cleaning", response_model=PcCleaningResponse, status_code=status.HTTP_201_CREATED)
async def add_pc_cleaning(
    data: PcCleaningCreate,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Add a PC cleaning record."""
    try:
        record = manager.add_pc_cleaning(
            serial_number=data.serial_number,
            employee=data.employee,
            branch=data.branch,
            location=data.location,
            inv_no=data.inv_no,
            db_name=data.db_name,
            additional_data=data.additional_data,
            equipment_id=data.equipment_id,
            current_description=data.current_description,
            hw_serial_no=data.hw_serial_no,
            model_name=data.model_name,
            manufacturer=data.manufacturer,
        )
        return PcCleaningResponse(**record)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding PC cleaning: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/cleaning", response_model=List[PcCleaningResponse])
async def get_pc_cleanings(
    db_name: Optional[str] = None,
    branch: Optional[str] = None,
    employee: Optional[str] = None,
    serial_number: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: Optional[int] = None,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get PC cleaning records with optional filtering."""
    try:
        records = manager.get_pc_cleanings(
            db_name=db_name,
            branch=branch,
            employee=employee,
            serial_number=serial_number,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )
        return [PcCleaningResponse(**r) for r in records]
    except Exception as e:
        logger.error(f"Error getting PC cleanings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/cleaning/statistics", response_model=PcCleaningStatisticsResponse)
async def get_pc_cleaning_statistics(
    period_days: int = Query(90, ge=1, le=3650),
    db_name: Optional[str] = None,
    manager: WorksManager = Depends(get_works_manager),
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(get_current_active_user),
):
    """Get PC cleaning coverage statistics by branch."""
    try:
        resolved_db = db_name or db_id
        stats = manager.get_pc_cleaning_statistics(
            period_days=period_days,
            db_name=resolved_db,
        )
        return PcCleaningStatisticsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting PC cleaning statistics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/mfu/statistics", response_model=MfuStatisticsResponse)
async def get_mfu_statistics(
    period_days: int = Query(90, ge=1, le=3650),
    db_name: Optional[str] = None,
    manager: WorksManager = Depends(get_works_manager),
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(get_current_active_user),
):
    """Get MFU/printer/plotter maintenance statistics by branch."""
    try:
        resolved_db = db_name or db_id
        stats = manager.get_mfu_statistics(
            period_days=period_days,
            db_name=resolved_db,
        )
        return MfuStatisticsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting MFU statistics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/battery/statistics", response_model=BatteryStatisticsResponse)
async def get_battery_statistics(
    period_days: int = Query(90, ge=1, le=3650),
    db_name: Optional[str] = None,
    manager: WorksManager = Depends(get_works_manager),
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(get_current_active_user),
):
    """Get UPS battery replacement statistics from JSON records."""
    try:
        resolved_db = db_name or db_id
        stats = manager.get_battery_statistics(
            period_days=period_days,
            db_name=resolved_db,
        )
        return BatteryStatisticsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting battery statistics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/pc-components/statistics", response_model=PcComponentsStatisticsResponse)
async def get_pc_components_statistics(
    period_days: int = Query(90, ge=1, le=3650),
    db_name: Optional[str] = None,
    manager: WorksManager = Depends(get_works_manager),
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(get_current_active_user),
):
    """Get PC component replacement statistics from JSON records."""
    try:
        resolved_db = db_name or db_id
        stats = manager.get_pc_components_statistics(
            period_days=period_days,
            db_name=resolved_db,
        )
        return PcComponentsStatisticsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting PC components statistics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/statistics/export")
async def export_statistics_excel(
    tab: str = Query(..., pattern="^(pc|mfu|battery|pc_components)$"),
    period_days: int = Query(90, ge=1, le=3650),
    db_name: Optional[str] = None,
    manager: WorksManager = Depends(get_works_manager),
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(get_current_active_user),
):
    """Export selected statistics tab as a single Excel list."""
    try:
        # Keep export global by default (all databases in JSON).
        # If db_name is explicitly provided, export only that database.
        resolved_db = db_name
        file_bytes, filename = build_statistics_excel(
            manager=manager,
            tab=tab,
            period_days=period_days,
            db_name=resolved_db,
        )
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
        return StreamingResponse(
            iter([file_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting statistics excel: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/works/cleaning/history", response_model=PcCleaningHistoryResponse)
async def get_pc_cleaning_history(
    serial_number: str,
    hw_serial_number: Optional[str] = None,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get PC cleaning history for a specific serial number."""
    try:
        history = manager.get_pc_cleaning_history(
            serial_number=serial_number,
            hw_serial_number=hw_serial_number,
        )
        return PcCleaningHistoryResponse(**history)
    except Exception as e:
        logger.error(f"Error getting PC cleaning history: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


# ========== All Works Endpoints ==========

@router.get("/works", response_model=WorksStatisticsResponse)
async def get_all_works(
    work_type: Optional[str] = None,
    db_name: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: Optional[int] = None,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Get all works with optional filtering."""
    try:
        works = manager.get_all_works(
            work_type=work_type,
            db_name=db_name,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )
        return WorksStatisticsResponse(
            cartridge={'total': len(works.get('cartridge', [])), 'by_branch': {}},
            battery={'total': len(works.get('battery', [])), 'by_branch': {}},
            component={'total': len(works.get('component', [])), 'by_type': {}, 'by_branch': {}},
            cleaning={'total': len(works.get('cleaning', [])), 'by_branch': {}},
            total_all=sum(len(v) for v in works.values()),
        )
    except Exception as e:
        logger.error(f"Error getting all works: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post("/works/bulk", response_model=BulkOperationResponse)
async def bulk_work(
    data: BulkWorkRequest,
    manager: WorksManager = Depends(get_works_manager),
    current_user: User = Depends(require_permission(PERM_DATABASE_WRITE)),
):
    """Bulk work operation for multiple items."""
    success_count = 0
    failed_count = 0
    errors = []

    for item in data.items:
        try:
            if data.work_type == 'cartridge':
                printer_model = item.get('model_name', item.get('printer_model', ''))
                manager.add_cartridge_replacement(
                    printer_model=printer_model,
                    cartridge_color=data.cartridge_color or '',
                    component_type=item.get('component_type', 'cartridge'),
                    component_color=item.get('component_color'),
                    cartridge_model=item.get('cartridge_model'),
                    detection_source=item.get('detection_source'),
                    printer_is_color=item.get('printer_is_color'),
                    branch=data.branch,
                    location=data.location,
                    serial_number=item.get('serial_number') or item.get('serial_no'),
                    inv_no=item.get('inv_no'),
                    db_name=data.db_name,
                    equipment_id=item.get('equipment_id'),
                    current_description=item.get('current_description'),
                    hw_serial_no=item.get('hw_serial_no'),
                    model_name=item.get('model_name'),
                    manufacturer=item.get('manufacturer'),
                    employee=item.get('employee'),
                )
            elif data.work_type == 'battery':
                manager.add_battery_replacement(
                    serial_number=item.get('serial_number') or item.get('serial_no', ''),
                    branch=data.branch,
                    location=data.location,
                    inv_no=item.get('inv_no'),
                    db_name=data.db_name,
                    equipment_id=item.get('equipment_id'),
                    current_description=item.get('current_description'),
                    hw_serial_no=item.get('hw_serial_no'),
                    model_name=item.get('model_name'),
                    manufacturer=item.get('manufacturer'),
                    employee=item.get('employee'),
                )
            elif data.work_type == 'component':
                manager.add_component_replacement(
                    serial_number=item.get('serial_number') or item.get('serial_no', ''),
                    component_type=data.component_type or '',
                    component_model=data.component_model or '',
                    branch=data.branch,
                    location=data.location,
                    inv_no=item.get('inv_no'),
                    db_name=data.db_name,
                    equipment_id=item.get('equipment_id'),
                    current_description=item.get('current_description'),
                    hw_serial_no=item.get('hw_serial_no'),
                    model_name=item.get('model_name'),
                    manufacturer=item.get('manufacturer'),
                    employee=item.get('employee'),
                    component_name=item.get('component_name'),
                    equipment_kind=item.get('equipment_kind'),
                )
            elif data.work_type == 'cleaning':
                manager.add_pc_cleaning(
                    serial_number=item.get('serial_number', ''),
                    employee=data.employee or item.get('employee', ''),
                    branch=data.branch,
                    location=data.location,
                    inv_no=item.get('inv_no'),
                    db_name=data.db_name,
                )
            success_count += 1
        except Exception as e:
            failed_count += 1
            errors.append(f"{item.get('serial_number', 'unknown')}: {str(e)}")

    return BulkOperationResponse(
        success_count=success_count,
        failed_count=failed_count,
        errors=errors,
    )


# ========== Cartridge Database Endpoints ==========

@router.get("/cartridges/compatibility/{printer_model}", response_model=PrinterCompatibilityResponse)
async def get_printer_compatibility(
    printer_model: str,
    cartridge_db: CartridgeDatabase = Depends(get_cartridge_database),
    current_user: User = Depends(get_current_active_user),
):
    """Get cartridge compatibility information for a printer model."""
    try:
        compatibility = cartridge_db.find_printer_compatibility(printer_model)

        if compatibility is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No compatibility information found for printer: {printer_model}"
            )

        compatible_models = [
            CartridgeInfoResponse(
                model=c.model,
                description=c.description,
                color=c.color,
                page_yield=c.page_yield,
                oem_part=c.oem_part,
            )
            for c in compatibility.compatible_models
        ]

        return PrinterCompatibilityResponse(
            printer_model=printer_model,
            oem_cartridge=compatibility.oem_cartridge,
            compatible_models=compatible_models,
            is_color=compatibility.is_color,
            components=compatibility.components,
            fuser_models=compatibility.fuser_models or [],
            photoconductor_models=compatibility.photoconductor_models or [],
            waste_toner_models=compatibility.waste_toner_models or [],
            transfer_belt_models=compatibility.transfer_belt_models or [],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting printer compatibility: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/cartridges/colors/{printer_model}", response_model=CartridgeColorsResponse)
async def get_cartridge_colors(
    printer_model: str,
    cartridge_db: CartridgeDatabase = Depends(get_cartridge_database),
    current_user: User = Depends(get_current_active_user),
):
    """Get available cartridge colors for a printer model."""
    try:
        colors = cartridge_db.get_cartridge_colors(printer_model)
        return CartridgeColorsResponse(printer_model=printer_model, colors=colors)
    except Exception as e:
        logger.error(f"Error getting cartridge colors: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/cartridges/components/{printer_model}", response_model=PrinterComponentsResponse)
async def get_printer_components(
    printer_model: str,
    cartridge_db: CartridgeDatabase = Depends(get_cartridge_database),
    current_user: User = Depends(get_current_active_user),
):
    """Get available component types for a printer model."""
    try:
        components = cartridge_db.get_printer_components(printer_model)
        return PrinterComponentsResponse(printer_model=printer_model, components=components)
    except Exception as e:
        logger.error(f"Error getting printer components: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/cartridges/is-color/{printer_model}")
async def is_color_printer(
    printer_model: str,
    cartridge_db: CartridgeDatabase = Depends(get_cartridge_database),
    current_user: User = Depends(get_current_active_user),
):
    """Check if a printer model is color."""
    try:
        is_color = cartridge_db.is_color_printer(printer_model)
        return {"printer_model": printer_model, "is_color": is_color}
    except Exception as e:
        logger.error(f"Error checking if printer is color: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
