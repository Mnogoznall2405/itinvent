#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pydantic models for JSON operations validation.

Defines request and response models for all JSON-based operations
including unfound equipment, transfers, and works.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


# ========== Unfound Equipment Models ==========

class UnfoundEquipmentCreate(BaseModel):
    """Request model for creating unfound equipment record."""
    serial_number: str = Field(..., min_length=1, description="Serial number of the equipment")
    model_name: str = Field(..., min_length=1, description="Model name")
    employee_name: str = Field(..., min_length=1, description="Employee name")
    brand_name: Optional[str] = Field(None, description="Brand/manufacturer name")
    location: Optional[str] = Field(None, description="Location code")
    equipment_type: Optional[str] = Field(None, description="Equipment type")
    description: Optional[str] = Field(None, description="Equipment description")
    inventory_number: Optional[str] = Field(None, description="Inventory number")
    batch_number: Optional[str] = Field(None, description="Batch number")
    ip_address: Optional[str] = Field(None, description="IP address")
    status: Optional[str] = Field(None, description="Equipment status")
    branch: Optional[str] = Field(None, description="Branch name")
    company: Optional[str] = Field(None, description="Company name")
    db_name: Optional[str] = Field(None, description="Database name")
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class UnfoundEquipmentResponse(BaseModel):
    """Response model for unfound equipment record."""
    serial_number: str
    model_name: str
    employee_name: str
    brand_name: Optional[str] = None
    location: Optional[str] = None
    equipment_type: Optional[str] = None
    description: Optional[str] = None
    inventory_number: Optional[str] = None
    batch_number: Optional[str] = None
    ip_address: Optional[str] = None
    status: Optional[str] = None
    branch: Optional[str] = None
    company: Optional[str] = None
    timestamp: str
    additional_data: Optional[Dict[str, Any]] = None
    db_name: Optional[str] = None


# ========== Transfer Models ==========

class TransferCreate(BaseModel):
    """Request model for creating equipment transfer record."""
    serial_number: str = Field(..., min_length=1, description="Serial number of the equipment")
    new_employee: str = Field(..., min_length=1, description="New employee name (recipient)")
    old_employee: Optional[str] = Field(None, description="Old employee name (sender)")
    inv_no: Optional[str] = Field(None, description="Inventory number")
    branch: Optional[str] = Field(None, description="Branch name")
    location: Optional[str] = Field(None, description="Location code")
    db_name: Optional[str] = Field(None, description="Database name")
    act_pdf_path: Optional[str] = Field(None, description="Path to PDF act document")
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class TransferResponse(BaseModel):
    """Response model for equipment transfer record."""
    serial_number: str
    new_employee: str
    old_employee: Optional[str] = None
    inv_no: Optional[str] = None
    timestamp: str
    db_name: Optional[str] = None
    act_pdf_path: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


# ========== Cartridge Replacement Models ==========

class CartridgeReplacementCreate(BaseModel):
    """Request model for creating cartridge replacement record."""
    printer_model: str = Field(..., min_length=1, description="Printer model")
    cartridge_color: str = Field(..., min_length=1, description="Cartridge color")
    component_type: Optional[str] = Field(default="cartridge", description="Component type")
    component_color: Optional[str] = Field(None, description="Component color")
    cartridge_model: Optional[str] = Field(None, description="Cartridge model")
    detection_source: Optional[str] = Field(None, description="Detection source")
    printer_is_color: Optional[bool] = Field(None, description="Whether printer is color")
    branch: str = Field(..., min_length=1, description="Branch name")
    location: str = Field(..., min_length=1, description="Location code")
    serial_number: Optional[str] = Field(None, description="Serial number of the printer")
    inv_no: Optional[str] = Field(None, description="Inventory number")
    db_name: Optional[str] = Field(None, description="Database name")
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    equipment_id: Optional[int] = Field(None, description="Equipment ID for SQL update")
    current_description: Optional[str] = Field(None, description="Current DESCRIPTION value for SQL update")
    hw_serial_no: Optional[str] = Field(None, description="Hardware serial number")
    model_name: Optional[str] = Field(None, description="Model name")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    employee: Optional[str] = Field(None, description="Employee name")


class CartridgeReplacementResponse(BaseModel):
    """Response model for cartridge replacement record."""
    printer_model: str
    component_type: Optional[str] = None
    component_color: Optional[str] = None
    cartridge_model: Optional[str] = None
    detection_source: Optional[str] = None
    printer_is_color: Optional[bool] = None
    cartridge_color: str
    branch: str
    location: str
    serial_number: Optional[str] = None
    serial_no: Optional[str] = None
    hw_serial_no: Optional[str] = None
    model_name: Optional[str] = None
    manufacturer: Optional[str] = None
    employee: Optional[str] = None
    inv_no: Optional[str] = None
    timestamp: str
    db_name: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


# ========== Battery Replacement Models ==========

class BatteryReplacementCreate(BaseModel):
    """Request model for creating battery replacement record."""
    serial_number: str = Field(..., min_length=1, description="Serial number of the equipment")
    branch: str = Field(..., min_length=1, description="Branch name")
    location: str = Field(..., min_length=1, description="Location code")
    inv_no: Optional[str] = Field(None, description="Inventory number")
    db_name: Optional[str] = Field(None, description="Database name")
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    equipment_id: Optional[int] = Field(None, description="Equipment ID for SQL update")
    current_description: Optional[str] = Field(None, description="Current DESCRIPTION value for SQL update")
    hw_serial_no: Optional[str] = Field(None, description="Hardware serial number")
    model_name: Optional[str] = Field(None, description="Model name")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    employee: Optional[str] = Field(None, description="Employee name")


class BatteryReplacementResponse(BaseModel):
    """Response model for battery replacement record."""
    serial_number: str
    inv_no: Optional[str] = None
    branch: str
    location: str
    timestamp: str
    db_name: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


# ========== Component Replacement Models ==========

class ComponentReplacementCreate(BaseModel):
    """Request model for creating component replacement record."""
    serial_number: str = Field(..., min_length=1, description="Serial number of the equipment")
    component_type: str = Field(..., min_length=1, description="Component type (fuser, drum, etc.)")
    component_model: str = Field(..., min_length=1, description="Component model")
    branch: str = Field(..., min_length=1, description="Branch name")
    location: str = Field(..., min_length=1, description="Location code")
    inv_no: Optional[str] = Field(None, description="Inventory number")
    db_name: Optional[str] = Field(None, description="Database name")
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    equipment_id: Optional[int] = Field(None, description="Equipment ID for SQL update")
    current_description: Optional[str] = Field(None, description="Current DESCRIPTION value for SQL update")
    hw_serial_no: Optional[str] = Field(None, description="Hardware serial number")
    model_name: Optional[str] = Field(None, description="Model name")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    employee: Optional[str] = Field(None, description="Employee name")
    component_name: Optional[str] = Field(None, description="Human-readable component name")
    equipment_kind: Optional[str] = Field(None, description="Equipment class: printer or pc")


class ComponentReplacementResponse(BaseModel):
    """Response model for component replacement record."""
    serial_number: str
    component_type: str
    component_model: str
    inv_no: Optional[str] = None
    branch: str
    location: str
    timestamp: str
    db_name: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


# ========== PC Cleaning Models ==========

class PcCleaningCreate(BaseModel):
    """Request model for creating PC cleaning record."""
    serial_number: str = Field(..., min_length=1, description="Serial number of the PC")
    employee: str = Field(default='Не указан', description="Employee name")
    branch: str = Field(..., min_length=1, description="Branch name")
    location: str = Field(..., min_length=1, description="Location code")
    inv_no: Optional[str] = Field(None, description="Inventory number")
    db_name: Optional[str] = Field(None, description="Database name")
    additional_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    equipment_id: Optional[int] = Field(None, description="Equipment ID for SQL update")
    current_description: Optional[str] = Field(None, description="Current DESCRIPTION value for SQL update")
    hw_serial_no: Optional[str] = Field(None, description="Hardware serial number for history lookup")
    model_name: Optional[str] = Field(None, description="Model name")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")


class PcCleaningResponse(BaseModel):
    """Response model for PC cleaning record."""
    serial_no: str
    hw_serial_no: Optional[str] = None
    model_name: Optional[str] = None
    manufacturer: Optional[str] = None
    branch: str
    location: str
    employee: str
    inv_no: Optional[str] = None
    db_name: Optional[str] = None
    timestamp: str


class PcCleaningHistoryResponse(BaseModel):
    """Response model for PC cleaning history."""
    last_date: Optional[str] = None
    count: int = 0
    time_ago_str: Optional[str] = None


class CartridgeReplacementHistoryResponse(BaseModel):
    """Response model for cartridge replacement history."""
    last_date: Optional[str] = None
    count: int = 0
    time_ago_str: Optional[str] = None
    cartridge_color: Optional[str] = None
    cartridge_model: Optional[str] = None


class BatteryReplacementHistoryResponse(BaseModel):
    """Response model for battery replacement history."""
    last_date: Optional[str] = None
    count: int = 0
    time_ago_str: Optional[str] = None


class ComponentReplacementHistoryResponse(BaseModel):
    """Response model for component replacement history."""
    last_date: Optional[str] = None
    count: int = 0
    time_ago_str: Optional[str] = None
    component_type: Optional[str] = None
    component_name: Optional[str] = None


# ========== Cartridge Database Models ==========

class CartridgeInfoResponse(BaseModel):
    """Response model for cartridge information."""
    model: str
    description: str
    color: str
    page_yield: Optional[int] = None
    oem_part: Optional[str] = None


class PrinterCompatibilityResponse(BaseModel):
    """Response model for printer compatibility information."""
    printer_model: str
    oem_cartridge: str
    compatible_models: List[CartridgeInfoResponse]
    is_color: bool
    components: List[str]
    fuser_models: List[str] = []
    photoconductor_models: List[str] = []
    waste_toner_models: List[str] = []
    transfer_belt_models: List[str] = []


class CartridgeColorsResponse(BaseModel):
    """Response model for cartridge colors."""
    printer_model: str
    colors: List[str]


class PrinterComponentsResponse(BaseModel):
    """Response model for printer components."""
    printer_model: str
    components: List[str]


# ========== Statistics Models ==========

class UnfoundStatisticsResponse(BaseModel):
    """Response model for unfound equipment statistics."""
    total: int
    by_type: Dict[str, int]
    by_branch: Dict[str, int]


class TransferStatisticsResponse(BaseModel):
    """Response model for transfer statistics."""
    total: int
    unique_employees: int
    top_employees: Dict[str, int]


class WorksStatisticsResponse(BaseModel):
    """Response model for works statistics."""
    cartridge: Dict[str, Any]
    battery: Dict[str, Any]
    component: Dict[str, Any]
    cleaning: Dict[str, Any]
    total_all: int


class PcCleaningBranchStatistics(BaseModel):
    """PC cleaning statistics row for a branch."""
    branch: str
    total_pc: int
    cleaned_pc: int
    remaining_pc: int
    coverage_percent: float
    cleanings_total: int
    cleanings_period: int


class PcCleaningTotalsStatistics(BaseModel):
    """Top-level totals for PC cleaning statistics."""
    total_pc: int
    cleaned_pc: int
    remaining_pc: int
    coverage_percent: float
    cleanings_total: int
    cleanings_period: int


class PcCleaningStatisticsResponse(BaseModel):
    """Response model for PC cleaning statistics."""
    generated_at: str
    period_days: int
    start_date: str
    end_date: str
    totals: PcCleaningTotalsStatistics
    branches: List[PcCleaningBranchStatistics]


class MfuTotalsStatistics(BaseModel):
    """Top-level totals for MFU/printer/plotter maintenance statistics."""
    total_operations: int
    unique_branches: int
    unique_locations: int


class MfuModelStat(BaseModel):
    """Top model statistics item."""
    model: str
    count: int


class MfuLocationItemStat(BaseModel):
    """Top used item in a location."""
    name: str
    count: int


class MfuLocationStatistics(BaseModel):
    """MFU/printer/plotter maintenance statistics row for a branch/location."""
    branch: str
    location: str
    operations: int
    last_timestamp: str
    by_type: Dict[str, int]
    top_items: List[MfuLocationItemStat]


class MfuRecentReplacement(BaseModel):
    """Recent replacement event."""
    timestamp: str
    branch: str
    location: str
    printer_model: str
    component_type: str
    replacement_item: str
    db_name: Optional[str] = None
    employee: Optional[str] = None
    inv_no: Optional[str] = None
    serial_no: Optional[str] = None


class MfuStatisticsResponse(BaseModel):
    """Response model for MFU/printer/plotter maintenance statistics."""
    generated_at: str
    period_days: int
    start_date: str
    end_date: str
    totals: MfuTotalsStatistics
    by_type_period: Dict[str, int]
    by_item_period: Dict[str, int]
    by_branch_period: Dict[str, int]
    by_model_period: List[MfuModelStat]
    by_location_period: List[MfuLocationStatistics]
    recent_replacements: List[MfuRecentReplacement]


class BatteryTotalsStatistics(BaseModel):
    """Top-level totals for UPS battery replacement statistics."""
    total_operations: int
    unique_branches: int
    unique_locations: int


class BatteryModelStat(BaseModel):
    """Top UPS model statistics item."""
    model: str
    count: int


class BatteryLocationItemStat(BaseModel):
    """Top used item in a location."""
    name: str
    count: int


class BatteryLocationStatistics(BaseModel):
    """UPS battery replacement statistics row for a branch/location."""
    branch: str
    location: str
    operations: int
    last_timestamp: str
    top_items: List[BatteryLocationItemStat]


class BatteryRecentReplacement(BaseModel):
    """Recent UPS battery replacement event."""
    timestamp: str
    branch: str
    location: str
    model_name: str
    manufacturer: str
    replacement_item: str
    db_name: Optional[str] = None
    employee: Optional[str] = None
    inv_no: Optional[str] = None
    serial_no: Optional[str] = None


class BatteryStatisticsResponse(BaseModel):
    """Response model for UPS battery replacement statistics."""
    generated_at: str
    period_days: int
    start_date: str
    end_date: str
    totals: BatteryTotalsStatistics
    by_branch_period: Dict[str, int]
    by_model_period: List[BatteryModelStat]
    by_manufacturer_period: Dict[str, int]
    by_item_period: Dict[str, int]
    by_location_period: List[BatteryLocationStatistics]
    recent_replacements: List[BatteryRecentReplacement]


class PcComponentsTotalsStatistics(BaseModel):
    """Top-level totals for PC component replacement statistics."""
    total_operations: int
    unique_branches: int
    unique_locations: int


class PcComponentsModelStat(BaseModel):
    """Top PC model statistics item."""
    model: str
    count: int


class PcComponentsLocationItemStat(BaseModel):
    """Top used component item in a location."""
    name: str
    count: int


class PcComponentsLocationStatistics(BaseModel):
    """PC component replacement statistics row for a branch/location."""
    branch: str
    location: str
    operations: int
    last_timestamp: str
    top_items: List[PcComponentsLocationItemStat]


class PcComponentsRecentReplacement(BaseModel):
    """Recent PC component replacement event."""
    timestamp: str
    branch: str
    location: str
    model_name: str
    manufacturer: str
    component_name: str
    replacement_item: str
    db_name: Optional[str] = None
    employee: Optional[str] = None
    inv_no: Optional[str] = None
    serial_no: Optional[str] = None


class PcComponentsStatisticsResponse(BaseModel):
    """Response model for PC component replacement statistics."""
    generated_at: str
    period_days: int
    start_date: str
    end_date: str
    totals: PcComponentsTotalsStatistics
    by_component_period: Dict[str, int]
    by_item_period: Dict[str, int]
    by_branch_period: Dict[str, int]
    by_model_period: List[PcComponentsModelStat]
    by_location_period: List[PcComponentsLocationStatistics]
    recent_replacements: List[PcComponentsRecentReplacement]


# ========== Bulk Operations ==========

class BulkTransferRequest(BaseModel):
    """Request model for bulk transfer operation."""
    items: List[Dict[str, Any]] = Field(..., min_length=1, description="List of items to transfer")
    new_employee: str = Field(..., min_length=1, description="Target employee name")
    branch: Optional[str] = Field(None, description="Branch name")
    location: Optional[str] = Field(None, description="Location code")
    db_name: Optional[str] = Field(None, description="Database name")


class BulkWorkRequest(BaseModel):
    """Request model for bulk work operation."""
    work_type: str = Field(..., description="Type of work: cartridge, battery, component, cleaning")
    items: List[Dict[str, Any]] = Field(..., min_length=1, description="List of items")
    branch: str = Field(..., min_length=1, description="Branch name")
    location: str = Field(..., min_length=1, description="Location code")
    db_name: Optional[str] = Field(None, description="Database name")
    # Work-specific fields
    cartridge_color: Optional[str] = Field(None, description="Cartridge color (for cartridge work)")
    component_type: Optional[str] = Field(None, description="Component type (for component work)")
    component_model: Optional[str] = Field(None, description="Component model (for component work)")
    employee: Optional[str] = Field(None, description="Employee name (for cleaning work)")

    @field_validator('work_type')
    @classmethod
    def validate_work_type(cls, v):
        allowed_types = ['cartridge', 'battery', 'component', 'cleaning']
        if v not in allowed_types:
            raise ValueError(f'work_type must be one of {allowed_types}')
        return v


class BulkOperationResponse(BaseModel):
    """Response model for bulk operation result."""
    success_count: int
    failed_count: int
    errors: List[str] = []
