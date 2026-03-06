import sqlite3
import json
from pathlib import Path

db_path = Path("C:/Project/Image_scan/data/local_store.db")

if not db_path.exists():
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Find rows related to 'Первомайская'
cursor.execute("SELECT id, file_name, branch, payload_json FROM local_records WHERE branch LIKE '%Первомайская%' OR branch LIKE '%19/21%'")
rows = cursor.fetchall()

print(f"Found {len(rows)} records with branch matching target:")
for r in rows:
    print(f"ID: {r['id']}, File: {r['file_name']}, Branch: {r['branch']}")

# Delete them
cursor.execute("DELETE FROM local_records WHERE branch LIKE '%Первомайская%' OR branch LIKE '%19/21%'")
deleted = cursor.rowcount
print(f"Deleted {deleted} rows by branch name.")

# Also let's check if there's any file named 'networks_branches.json' or something similar in local_store?
# Actually, branches are typically in MS SQL `dev_branches`. But wait! 
# Let's see what distinct files are in local_records
cursor.execute("SELECT DISTINCT file_name FROM local_records")
files = [r['file_name'] for r in cursor.fetchall()]
print(f"Files in local_store.db: {files}")

conn.commit()
conn.close()
print("Done mapping local_store.db")
