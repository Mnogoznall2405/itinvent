import sqlite3
from pathlib import Path

db_path = Path("C:/Project/Image_scan/data/local_store.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. Start by finding the branch in network_branches
cursor.execute("SELECT id, name, branch_code FROM network_branches WHERE name LIKE '%Первомайская%' OR name LIKE '%19/21%' OR branch_code LIKE '%p19-21%'")
branches = cursor.fetchall()
print(f"Found {len(branches)} matching branches in network_branches.")

total_deleted = 0
for b in branches:
    b_id = b["id"]
    print(f"Deleting branch ID: {b_id}, Name: {b['name']}, Code: {b['branch_code']}")
    
    # Since foreign keys are ON by default in standard setup? Let's turn them ON just in case so ON DELETE CASCADE works.
    conn.execute("PRAGMA foreign_keys=ON;")
    
    cursor.execute("DELETE FROM network_branches WHERE id=?", (b_id,))
    total_deleted += cursor.rowcount
    print(f"Deleted {cursor.rowcount} branch records. Cascades should have deleted ports, sockets, maps, etc.")

conn.commit()
conn.close()
print("Relational cleanup done.")
