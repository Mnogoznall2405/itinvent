import os
import asyncio
import logging
from typing import List, Dict, Optional
from ldap3 import Server, Connection, ALL, SUBTREE
from backend.config import config
from backend.database.connection import get_db
from backend.database.queries import AVAILABLE_DATABASES

logger = logging.getLogger("ad_sync")
# Configure simple logging if not already configured
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def fetch_ad_users() -> List[Dict]:
    """Fetch active users from Active Directory."""
    server_host = os.getenv("LDAP_SERVER", config.app.ldap_server)
    if not server_host:
        logger.warning("LDAP_SERVER not set. Skipping AD sync.")
        return []
        
    sync_user = os.getenv("LDAP_SYNC_USER", "")
    sync_password = os.getenv("LDAP_SYNC_PASSWORD", "")
    
    server = Server(server_host, get_info=ALL)
    
    # Try binding
    if sync_user and sync_password:
        conn = Connection(server, user=sync_user, password=sync_password, auto_bind=True)
    else:
        # Try anonymous or NTLM current context bind (works if running on Windows domain joined machine)
        try:
            conn = Connection(server, auto_bind=True)
        except Exception as e:
            logger.error(f"Failed to bind anonymously. Set LDAP_SYNC_USER and LDAP_SYNC_PASSWORD in .env: {e}")
            return []
            
    base_dn = os.getenv("LDAP_BASE_DN", "")
    if not base_dn:
        # guess base_dn from domain
        domain = os.getenv("LDAP_DOMAIN", config.app.ldap_domain)
        if domain:
            base_dn = ",".join(f"dc={part}" for part in domain.split("."))
        else:
            base_dn = "dc=zsgp,dc=corp"
            
    # Filter only active users with sAMAccountName and displayName
    search_filter = "(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2))(sAMAccountName=*)(displayName=*))"
    attributes = ['sAMAccountName', 'sn', 'givenName', 'middleName', 'displayName', 'department', 'title', 'mail', 'telephoneNumber']
    
    try:
        conn.search(search_base=base_dn, search_filter=search_filter, attributes=attributes, search_scope=SUBTREE)
    except Exception as e:
        logger.error(f"AD Search failed: {e}")
        conn.unbind()
        return []
    
    users = []
    for entry in conn.entries:
        try:
            users.append({
                "login": str(entry.sAMAccountName.value) if 'sAMAccountName' in entry and entry.sAMAccountName else "",
                "lname": str(entry.sn.value) if 'sn' in entry and entry.sn else "",
                "fname": str(entry.givenName.value) if 'givenName' in entry and entry.givenName else "",
                "mname": str(entry.middleName.value) if 'middleName' in entry and entry.middleName else "",
                "display_name": str(entry.displayName.value) if 'displayName' in entry and entry.displayName else "",
                "department": str(entry.department.value) if 'department' in entry and entry.department else "",
                "title": str(entry.title.value) if 'title' in entry and entry.title else "",
                "mail": str(entry.mail.value) if 'mail' in entry and entry.mail else "",
                "phone": str(entry.telephoneNumber.value) if 'telephoneNumber' in entry and entry.telephoneNumber else "",
            })
        except Exception as e:
            logger.debug(f"Failed to parse AD entry: {e}")
            
    conn.unbind()
    
    # Filter out empty logins
    return [u for u in users if u.get("login") and u.get("display_name")]


def sync_users_to_db(ad_users: List[Dict], db_id: str, force_update: bool = False) -> dict:
    """
    Sync AD users into a specific IT-Invent database.
    Does NOT delete any existing users. Only performs INSERTs for new users.
    Optionally updates existing users if force_update=True.
    """
    db = get_db(db_id)
    stats = {"added": 0, "updated": 0, "errors": 0}
    
    try:
        # Get existing users logically by login (case insensitive)
        existing = db.execute_query("SELECT OWNER_NO, OWNER_LOGIN, OWNER_EMAIL FROM OWNERS WHERE OWNER_LOGIN IS NOT NULL OR OWNER_EMAIL IS NOT NULL")
        
        login_map = {str(row.get("OWNER_LOGIN", "")).lower(): row for row in existing if row.get("OWNER_LOGIN")}
        
        # We need the max owner_no to insert new ones
        max_no_res = db.execute_query("SELECT ISNULL(MAX(OWNER_NO), 0) as max_no FROM OWNERS")
        next_owner_no: int = int(max_no_res[0]["max_no"]) + 1 if max_no_res else 1
        
        for u in ad_users:
            login = u["login"].lower()
            if not login:
                continue
                
            if login in login_map:
                if force_update:
                    # Optional: Update existing user (department, title, phone, email) if we want to sync changes
                    # But per user request: "Главное чтобы он не удалял из базы пользователей"
                    owner_no = login_map[login]["OWNER_NO"]
                    try:
                        update_query = """
                        UPDATE OWNERS SET
                            OWNER_DEPT = ?, 
                            OWNER_POSITION = ?, 
                            OWNER_PHONE = ?, 
                            OWNER_EMAIL = ?
                        WHERE OWNER_NO = ?
                        """
                        db.execute_update(update_query, (
                            u["department"][:255] if u["department"] else "",
                            u["title"][:255] if u["title"] else "",
                            u["phone"][:255] if u["phone"] else "",
                            u["mail"][:255] if u["mail"] else "",
                            owner_no
                        ))
                        stats["updated"] += 1
                    except Exception as e:
                        logger.error(f"Failed to update user {login} in {db_id}: {e}")
                        stats["errors"] += 1
            else:
                # Insert new user
                query = """
                INSERT INTO OWNERS (
                    OWNER_NO, OWNER_LNAME, OWNER_FNAME, OWNER_MNAME,
                    OWNER_DISPLAY_NAME, OWNER_DEPT, OWNER_EMAIL, 
                    OWNER_LOGIN, OWNER_POSITION, OWNER_PHONE, OWNER_DISMISS
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """
                params = (
                    next_owner_no,
                    u["lname"][:255] if u["lname"] else "",
                    u["fname"][:255] if u["fname"] else "",
                    u["mname"][:255] if u["mname"] else "",
                    u["display_name"][:255] if u["display_name"] else "",
                    u["department"][:255] if u["department"] else "",
                    u["mail"][:255] if u["mail"] else "",
                    u["login"][:255] if u["login"] else "",
                    u["title"][:255] if u["title"] else "",
                    u["phone"][:255] if u["phone"] else "",
                )
                try:
                    db.execute_update(query, params)
                    next_owner_no += 1
                    stats["added"] += 1
                except Exception as e:
                    logger.error(f"Failed to insert user {login} in {db_id}: {e}")
                    stats["errors"] += 1
                    
    except Exception as e:
        logger.error(f"DB sync failed for {db_id}: {e}")
        
    return stats


def run_ad_sync(force_update: bool = False) -> dict:
    """Run full AD sync across all configured databases."""
    try:
        logger.info("Fetching users from Active Directory...")
        users = fetch_ad_users()
        if not users:
            return {"status": "error", "message": "No users found in AD or failed to bind. Check LDAP_SYNC_USER/PASSWORD."}
            
        logger.info(f"Found {len(users)} active users in AD. Syncing to databases...")
        results = {}
        for db_id in AVAILABLE_DATABASES.keys():
            logger.info(f"Syncing to database: {db_id}...")
            results[db_id] = sync_users_to_db(users, db_id, force_update=force_update)
            
        return {"status": "success", "results": results, "total_ad_users": len(users)}
    except Exception as e:
        logger.exception("Unexpected error during AD sync")
        return {"status": "error", "message": str(e)}


async def background_ad_sync_loop():
    """Background task to run AD sync periodically."""
    # Run by default every 24 hours (86400 seconds), wait 1 minute before first run
    sync_interval = int(os.getenv("LDAP_SYNC_INTERVAL_SECONDS", "86400"))
    await asyncio.sleep(60)
    
    while True:
        try:
            logger.info("Starting scheduled background AD sync...")
            # Run blocking I/O in thread pool
            await asyncio.to_thread(run_ad_sync, True)
            logger.info("Scheduled background AD sync finished.")
            await asyncio.sleep(sync_interval)
        except asyncio.CancelledError:
            logger.info("Background AD sync loop cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in background AD sync loop: {e}")
            await asyncio.sleep(300) # Wait 5 minutes on error
