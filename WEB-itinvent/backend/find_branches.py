import os
import sys

sys.path.append(os.path.abspath('.'))

from backend.database.connection import db_manager

def investigate_branches():
    print("Testing SQL Server connection...")
    if not db_manager.test_connection():
        print("Failed to connect to DB.")
        return

    print("Fetching branches...")
    rows = db_manager.execute_query("SELECT id, name, city_code FROM dev_branches")
    
    print(f"Total branches: {len(rows)}")
    for r in rows:
        if "первомайская" in str(r.get("name", "")).lower() or "19/21" in str(r.get("name", "")):
            print(f"FOUND SUSPECT: {r}")

if __name__ == "__main__":
    investigate_branches()
