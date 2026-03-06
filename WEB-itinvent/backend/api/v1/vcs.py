import logging
import uuid
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, constr

from backend.api.deps import require_permission
from backend.services.authorization_service import PERM_VCS_READ, PERM_VCS_MANAGE
from backend.services.secret_crypto_service import encrypt_secret, decrypt_secret
from local_store import get_local_store

logger = logging.getLogger(__name__)

router = APIRouter()

VCS_STORE_KEY = "vcs_computers.json"
VCS_CONFIG_KEY = "vcs_config.json"

class VcsComputer(BaseModel):
    id: str
    name: str
    ip_address: str
    location: Optional[str] = ""
    created_at: str
    updated_at: str

class VcsComputerCreate(BaseModel):
    name: str = constr(min_length=1, max_length=100)
    ip_address: str = constr(min_length=7, max_length=50) 
    location: Optional[str] = ""

class VcsComputerUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    location: Optional[str] = None

class VcsConfig(BaseModel):
    password_hex: str = ""
    
class VcsConfigUpdate(BaseModel):
    password_hex: str

class VcsInfo(BaseModel):
    content: str = ""

class VcsInfoUpdate(BaseModel):
    content: str

def _get_all_computers() -> List[dict]:
    store = get_local_store()
    data = store.load_json(VCS_STORE_KEY, default_content=[])
    if not isinstance(data, list):
         return []
    return data

def _save_all_computers(data: List[dict]) -> bool:
    store = get_local_store()
    return store.save_json(VCS_STORE_KEY, data)

def _get_vcs_config() -> dict:
    store = get_local_store()
    data = store.load_json(VCS_CONFIG_KEY, default_content={"password_hex_encrypted": ""})
    if not isinstance(data, dict):
        return {"password_hex_encrypted": ""}
    return data

def _save_vcs_config(data: dict) -> bool:
    store = get_local_store()
    return store.save_json(VCS_CONFIG_KEY, data)

VCS_INFO_KEY = "vcs_info.json"

def _get_vcs_info() -> dict:
    store = get_local_store()
    data = store.load_json(VCS_INFO_KEY, default_content={"content": ""})
    if not isinstance(data, dict):
        return {"content": ""}
    return data

def _save_vcs_info(data: dict) -> bool:
    store = get_local_store()
    return store.save_json(VCS_INFO_KEY, data)


@router.get("/computers", response_model=List[VcsComputer])
async def get_vcs_computers(
    current_user=Depends(require_permission(PERM_VCS_READ))
):
    """Get list of all VCS terminal computers"""
    computers = _get_all_computers()
    return computers

@router.post("/computers", response_model=VcsComputer)
async def create_vcs_computer(
    computer: VcsComputerCreate,
    current_user=Depends(require_permission(PERM_VCS_MANAGE))
):
    """Add a new VCS terminal computer"""
    computers = _get_all_computers()
    
    now = datetime.now(timezone.utc).isoformat()
    new_comp = {
        "id": str(uuid.uuid4()),
        "name": computer.name.strip(),
        "ip_address": computer.ip_address.strip(),
        "location": computer.location.strip() if computer.location else "",
        "created_at": now,
        "updated_at": now
    }
    
    computers.append(new_comp)
    if not _save_all_computers(computers):
        raise HTTPException(status_code=500, detail="Failed to save data")
        
    return new_comp

@router.put("/computers/{computer_id}", response_model=VcsComputer)
async def update_vcs_computer(
    computer_id: str,
    update_data: VcsComputerUpdate,
    current_user=Depends(require_permission(PERM_VCS_MANAGE))
):
    """Update an existing VCS terminal computer"""
    computers = _get_all_computers()
    
    for i, c in enumerate(computers):
        if c.get("id") == computer_id:
            if update_data.name is not None:
                c["name"] = update_data.name.strip()
            if update_data.ip_address is not None:
                c["ip_address"] = update_data.ip_address.strip()
            if update_data.location is not None:
                c["location"] = update_data.location.strip()
                
            c["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            if not _save_all_computers(computers):
                raise HTTPException(status_code=500, detail="Failed to save data")
            return c
            
    raise HTTPException(status_code=404, detail="Computer not found")

@router.delete("/computers/{computer_id}")
async def delete_vcs_computer(
    computer_id: str,
    current_user=Depends(require_permission(PERM_VCS_MANAGE))
):
    """Delete a VCS terminal computer"""
    computers = _get_all_computers()
    
    filtered_computers = [c for c in computers if c.get("id") != computer_id]
    
    if len(filtered_computers) == len(computers):
        raise HTTPException(status_code=404, detail="Computer not found")
        
    if not _save_all_computers(filtered_computers):
        raise HTTPException(status_code=500, detail="Failed to save data")
        
    return {"success": True}

@router.get("/config", response_model=VcsConfig)
async def get_vcs_config(
    current_user=Depends(require_permission(PERM_VCS_READ))
):
    """Get global VCS configuration, containing the decrypted password_hex"""
    config_data = _get_vcs_config()
    encrypted_hex = config_data.get("password_hex_encrypted", "")
    decrypted_hex = ""
    if encrypted_hex:
        try:
            decrypted_hex = decrypt_secret(encrypted_hex)
        except Exception as e:
            logger.error(f"Failed to decrypt VCS password_hex: {e}")
            
    return VcsConfig(password_hex=decrypted_hex)

@router.put("/config", response_model=VcsConfig)
async def update_vcs_config(
    config_update: VcsConfigUpdate,
    current_user=Depends(require_permission(PERM_VCS_MANAGE))
):
    """Update global VCS configuration, encrypting the password_hex before storing"""
    plain_hex = config_update.password_hex.strip().lower()
    
    # Encrypt
    encrypted_hex = ""
    if plain_hex:
        try:
            encrypted_hex = encrypt_secret(plain_hex)
        except Exception as e:
            logger.error(f"Failed to encrypt VCS password_hex: {e}")
            raise HTTPException(status_code=500, detail="Encryption failed")
            
    # Save
    config_data = _get_vcs_config()
    config_data["password_hex_encrypted"] = encrypted_hex
    if not _save_vcs_config(config_data):
        raise HTTPException(status_code=500, detail="Failed to save config data")
        
    return VcsConfig(password_hex=plain_hex)

@router.get("/info", response_model=VcsInfo)
async def get_vcs_info(
    current_user=Depends(require_permission(PERM_VCS_READ))
):
    """Get global VCS info (markdown content)"""
    info_data = _get_vcs_info()
    return VcsInfo(content=info_data.get("content", ""))

@router.put("/info", response_model=VcsInfo)
async def update_vcs_info(
    info_update: VcsInfoUpdate,
    current_user=Depends(require_permission(PERM_VCS_MANAGE))
):
    """Update global VCS info (markdown content)"""
    info_data = _get_vcs_info()
    info_data["content"] = info_update.content
    
    if not _save_vcs_info(info_data):
        raise HTTPException(status_code=500, detail="Failed to save VCS info")
        
    return VcsInfo(content=info_update.content)
