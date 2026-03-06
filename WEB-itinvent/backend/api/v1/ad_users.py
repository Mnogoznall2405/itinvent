from typing import List, Dict, Any
from fastapi import APIRouter, Depends

from backend.api.deps import require_permission
from pydantic import BaseModel
from backend.services.authorization_service import PERM_AD_USERS_READ, PERM_AD_USERS_MANAGE
from backend.services.ad_users_service import get_ad_users_password_status, set_ad_user_branch

router = APIRouter()

class AssignBranchRequest(BaseModel):
    login: str
    branch_no: int | None = None

@router.get("/password-status", response_model=List[Dict[str, Any]])
def get_password_status(
    current_user=Depends(require_permission(PERM_AD_USERS_READ))
):
    """
    Returns a list of AD users from 'Users standart'/'Users Objects'
    along with their password expiration status (40 days policy).
    """
    return get_ad_users_password_status()

@router.post("/assign-branch")
def assign_user_branch(
    req: AssignBranchRequest,
    current_user=Depends(require_permission(PERM_AD_USERS_MANAGE))
):
    """
    Manually assign a branch to an AD user.
    """
    success = set_ad_user_branch(req.login, req.branch_no)
    if not success:
         from fastapi import HTTPException
         raise HTTPException(status_code=400, detail="Failed to assign branch")
    return {"success": True}
