from fastapi import APIRouter, Depends, Request, HTTPException
from typing import Optional, List, Dict, Any
import logging

from backend.api.deps import get_current_active_user, get_current_database_id
from backend.models.auth import User
from backend.database.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

def get_client_ip(request: Request) -> str:
    """Extract client IP from request headers or socket."""
    # First, try standard X-Forwarded-For (if behind proxy/nginx)
    x_forwarded_for = request.headers.get("x-forwarded-for")
    ip = ""
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    
    # Fallback to direct client host
    elif request.client and request.client.host:
        ip = request.client.host
        
    # Strip port if present (e.g. 10.105.0.42:51019 -> 10.105.0.42)
    if ip and ":" in ip:
        # Check if it's an IPv6 address, they have multiple colons. 
        # IPv4 with port has only one colon.
        if ip.count(":") == 1:
            ip = ip.split(":")[0]
            
    return ip

@router.get("/identify-workspace")
async def identify_workspace(
    request: Request,
    db_id: Optional[str] = Depends(get_current_database_id),
    current_user: User = Depends(get_current_active_user)
):
    """
    Identifies the user's PC by their IP address, finds the owner, 
    and returns all equipment associated with that owner,
    highlighting equipment that historically moved together.
    """
    if not db_id:
        raise HTTPException(status_code=400, detail="Database ID is required")
        
    db = get_db(db_id)
    client_ip = get_client_ip(request)
    
    # DEBUG OVERRIDE: For testing locally where IP is 127.0.0.1
    # client_ip = "10.105.0.42"  # Uncomment to test with a specific IP
    
    if not client_ip or client_ip in ("127.0.0.1", "::1"):
        # If testing locally, we might not find anything by localhost IP.
        # But we'll still execute the query just in case.
        logger.warning(f"Client IP is local or empty: {client_ip}")

    # 1. Find the PC by IP address
    # Type 1 is usually "Компьютеры" or similar main CI_TYPE
    pc_query = """
        SELECT TOP 1
            i.INV_NO, i.ID, i.CI_TYPE, i.EMPL_NO, i.IP_ADDRESS,
            m.MODEL_NAME, t.TYPE_NAME,
            o.OWNER_DISPLAY_NAME as owner_name
        FROM ITEMS i
        LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
        LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
        LEFT JOIN OWNERS o ON i.EMPL_NO = o.OWNER_NO
        WHERE i.IP_ADDRESS = ? AND i.STATUS_NO = 1 -- Status 1 is usually 'Active/In use'
        ORDER BY i.ID DESC
    """
    pc_result = db.execute_query(pc_query, (client_ip,))
    
    if not pc_result:
        return {
            "success": False,
            "message": f"Ваш IP-адрес ({client_ip}) не найден среди активного оборудования в базе.",
            "client_ip": client_ip
        }
        
    pc_info = pc_result[0]
    owner_no = pc_info.get("EMPL_NO")
    owner_name = pc_info.get("owner_name")
    
    if not owner_no:
        return {
            "success": True, # Technically we found the PC
            "message": f"Ваш ПК найден (IP: {client_ip}), но за ним не закреплен владелец.",
            "client_ip": client_ip,
            "pc_info": pc_info,
            "owner_info": None,
            "linked_items": []
        }

    # 2. Get the latest history record for the found PC to know where it came from
    pc_history_query = """
        SELECT TOP 1 EMPL_NO_OLD, EMPL_NO_NEW, CH_DATE, CH_USER
        FROM CI_HISTORY
        WHERE ITEM_ID = ?
        ORDER BY HIST_ID DESC
    """
    pc_hist = db.execute_query(pc_history_query, (pc_info["ID"],))
    pc_prev_owner = pc_hist[0].get("EMPL_NO_OLD") if pc_hist else None
    
    # 3. Find ALL active equipment belonging to this owner
    owner_items_query = """
        SELECT 
            i.INV_NO, i.ID, i.CI_TYPE, i.SERIAL_NO,
            m.MODEL_NAME, t.TYPE_NAME, t.TYPE_NO
        FROM ITEMS i
        LEFT JOIN CI_MODELS m ON i.MODEL_NO = m.MODEL_NO AND i.CI_TYPE = m.CI_TYPE
        LEFT JOIN CI_TYPES t ON i.CI_TYPE = t.CI_TYPE AND i.TYPE_NO = t.TYPE_NO
        WHERE i.EMPL_NO = ? AND i.STATUS_NO = 1
    """
    owner_items = db.execute_query(owner_items_query, (owner_no,))
    
    # 4. Analyze history for each item to find "Linked" equipment (same previous owner)
    linked_inv_nos = []
    
    if pc_prev_owner is not None:
        for item in owner_items:
            # Skip the PC itself, we know it's linked to itself
            if item["ID"] == pc_info["ID"] and item["CI_TYPE"] == pc_info["CI_TYPE"]:
                linked_inv_nos.append(item["INV_NO"])
                continue
                
            item_hist_query = """
                SELECT TOP 1 EMPL_NO_OLD
                FROM CI_HISTORY
                WHERE ITEM_ID = ?
                ORDER BY HIST_ID DESC
            """
            item_hist = db.execute_query(item_hist_query, (item["ID"],))
            
            if item_hist:
                item_prev_owner = item_hist[0].get("EMPL_NO_OLD")
                # If they both came from the exact same previous owner, they are likely a set
                if item_prev_owner == pc_prev_owner:
                    linked_inv_nos.append(item["INV_NO"])

    # Fallback: if we couldn't link anything by history (e.g. fresh items), 
    # we at least link the PC itself.
    if not linked_inv_nos:
         linked_inv_nos.append(pc_info["INV_NO"])

    return {
        "success": True,
        "message": f"Определено рабочее место: {owner_name}",
        "client_ip": client_ip,
        "pc_info": {
            "inv_no": pc_info.get("INV_NO"),
            "model_name": pc_info.get("MODEL_NAME"),
            "type_name": pc_info.get("TYPE_NAME")
        },
        "owner_info": {
            "owner_no": owner_no,
            "owner_name": owner_name
        },
        "total_items_count": len(owner_items),
        "linked_inv_nos": linked_inv_nos # Array of INVs that should be auto-checked
    }
