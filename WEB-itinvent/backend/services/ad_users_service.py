import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict

from ldap3 import Server, Connection, ALL, SUBTREE
from backend.config import config
from backend.database.connection import get_db
from local_store import get_local_store

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# 100-nanosecond intervals from Jan 1, 1601 to Jan 1, 1970
epoch_diff = 116444736000000000

def decode_cp1251(val):
    if not val: return None
    try:
        if isinstance(val, str):
            return val.encode('latin1').decode('cp1251')
    except:
        pass
    return str(val)

def get_ad_users_password_status() -> List[Dict]:
    """Fetch active users from AD and calculate password expiration days."""
    server_host = os.getenv("LDAP_SERVER", config.app.ldap_server)
    if not server_host:
        logger.warning("LDAP_SERVER not set. Skipping AD query.")
        return []
        
    sync_user = os.getenv("LDAP_SYNC_USER", "")
    sync_password = os.getenv("LDAP_SYNC_PASSWORD", "")
    
    server = Server(server_host, get_info=ALL)
    
    if sync_user and sync_password:
        conn = Connection(server, user=sync_user, password=sync_password, auto_bind=True)
    else:
        try:
            conn = Connection(server, auto_bind=True)
        except Exception as e:
            logger.error(f"Failed to bind anonymously. Set LDAP_SYNC_USER and LDAP_SYNC_PASSWORD: {e}")
            return []
            
    base_dn = os.getenv("LDAP_BASE_DN", "")
    if not base_dn:
        domain = os.getenv("LDAP_DOMAIN", config.app.ldap_domain)
        if domain:
            base_dn = ",".join(f"dc={part}" for part in domain.split("."))
        else:
            base_dn = "dc=zsgp,dc=corp"
            
    # Search specifically within the 'Users Objects' OU which is inside 'Users standart'
    search_base = f"OU=Users Objects,OU=Users standart,{base_dn}"
    search_filter = "(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"
    attributes = ['sAMAccountName', 'displayName', 'department', 'title', 'pwdLastSet']
    
    try:
        conn.search(search_base=search_base, search_filter=search_filter, attributes=attributes, search_scope=SUBTREE)
    except Exception as e:
        logger.error(f"AD Search failed: {e}")
        conn.unbind()
        return []
        
    entries = conn.entries
    conn.unbind()
    
    # Try mapping users to branches via IT-Invent Database
    branch_map = {}
    try:
        db = get_db('OBJ-ITINVENT')
        query = '''
            SELECT 
                o.OWNER_LOGIN, 
                b.BRANCH_NO,
                b.BRANCH_NAME
            FROM OWNERS o
            LEFT JOIN (
                SELECT EMPL_NO, MAX(BRANCH_NO) as BRANCH_NO 
                FROM ITEMS 
                WHERE EMPL_NO IS NOT NULL AND BRANCH_NO IS NOT NULL AND BRANCH_NO > 0
                GROUP BY EMPL_NO
            ) as i ON i.EMPL_NO = o.OWNER_NO
            LEFT JOIN BRANCHES b ON b.BRANCH_NO = i.BRANCH_NO
            WHERE o.OWNER_LOGIN IS NOT NULL AND b.BRANCH_NAME IS NOT NULL
        '''
        res = db.execute_query(query)
        for r in res:
            login = str(r['OWNER_LOGIN']).lower().strip()
            branch_map[login] = {
                'branch_no': r['BRANCH_NO'],
                'branch_name': decode_cp1251(r['BRANCH_NAME']) or 'Неотсортированные'
            }
    except Exception as e:
        logger.error(f"Failed to fetch branch mappings from DB: {e}")

    users_list = []
    now_utc = datetime.now(timezone.utc)
    
    # Load custom branches from local store
    try:
        store = get_local_store()
        custom_branches = store.load_json('ad_user_branches.json', default_content={})
    except Exception as e:
        logger.error(f"Failed to load custom branch mappings from local_store: {e}")
        custom_branches = {}

    # Fetch all branches from DB to ensure we can map custom branches correctly
    all_branches = {}
    try:
        from backend.database.equipment_db import get_all_branches
        db_id = 'OBJ-ITINVENT' # We use the same hardcoded one
        branches_list = get_all_branches(db_id)
        for b in branches_list:
            b_no = b.get('BRANCH_NO') or b.get('branch_no')
            b_name = b.get('BRANCH_NAME') or b.get('branch_name')
            if b_name and isinstance(b_name, str):
                b_name = decode_cp1251(b_name)
            if b_no:
                all_branches[b_no] = b_name or 'Неотсортированные'
    except Exception as e:
        logger.error(f"Failed to fetch all branches for mapping: {e}")

    for entry in entries:
        try:
            display_name = str(entry.displayName.value) if 'displayName' in entry and entry.displayName else ""
            if not display_name:
                continue
            
            login = str(entry.sAMAccountName.value) if 'sAMAccountName' in entry and entry.sAMAccountName else ""
            department = str(entry.department.value) if 'department' in entry and entry.department else ""
            title = str(entry.title.value) if 'title' in entry and entry.title else ""
                
            pwd_last_set_raw = int(entry.pwdLastSet.raw_values[0]) if entry.pwdLastSet else 0
            
            days_to_expire = 0
            pwd_last_set_date = None
            expiration_date = None
            
            if pwd_last_set_raw == 0:
                # Password must be changed at next logon
                days_to_expire = 0
                pwd_last_set_date = None
            else:
                # Convert active directory time to UTC datetime
                timestamp = (pwd_last_set_raw - epoch_diff) / 10000000
                pwd_last_set_date = datetime.fromtimestamp(timestamp, timezone.utc)
                
                # Expiration is 40 days after pwdLastSet
                expiration_date = pwd_last_set_date + timedelta(days=40)
                
                # Calculate remaining days
                delta = expiration_date - now_utc
                days_to_expire = max(0, delta.days)
                
                # If password already expired based on strictly 40 days
                if delta.total_seconds() < 0:
                    days_to_expire = 0
            
            login_lower = str(login).lower().strip()
            mapped_branch = branch_map.get(login_lower, {})
            
            # Use local_store mapping if exists, else fallback to IT-Invent db mapping
            local_branch_no = custom_branches.get(login_lower)
            if local_branch_no:
                branch_no = local_branch_no
                branch_name = all_branches.get(local_branch_no, 'Неотсортированные')
            else:
                branch_no = mapped_branch.get('branch_no', None)
                branch_name = mapped_branch.get('branch_name', 'Неотсортированные')

            users_list.append({
                "login": login,
                "display_name": display_name,
                "department": department,
                "title": title,
                "pwd_last_set": pwd_last_set_raw,
                "pwd_last_set_date": pwd_last_set_date.isoformat() if pwd_last_set_date else None,
                "expiration_date": expiration_date.isoformat() if expiration_date else None,
                "days_to_expire": days_to_expire,
                "branch_name": branch_name,
                "branch_no": branch_no
            })
        except Exception as e:
            logger.debug(f"Failed to parse AD entry: {e}")
            
    # Sort users by branch_name then days_to_expire, then display_name
    users_list.sort(key=lambda x: (x["branch_name"] == "Неотсортированные", x["branch_name"], x["days_to_expire"], x["display_name"]))
    
    return users_list

def set_ad_user_branch(login: str, branch_no: int | None) -> bool:
    """Manually set or update a user's branch in the local store."""
    login_lower = str(login).lower().strip()
    if not login_lower:
        return False
        
    try:
        store = get_local_store()
        custom_branches = store.load_json('ad_user_branches.json', default_content={})
        
        if branch_no is None or branch_no == 0:
            if login_lower in custom_branches:
                del custom_branches[login_lower]
        else:
            custom_branches[login_lower] = branch_no
            
        store.save_json('ad_user_branches.json', custom_branches)
            
        return True
    except Exception as e:
        logger.error(f"Failed to save local branch mapping for AD user {login}: {e}")
        return False
