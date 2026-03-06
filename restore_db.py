import json
import sys
import os

sys.path.append(os.path.abspath('.'))
from local_store import get_local_store

store = get_local_store()

with open("C:/Project/Image_scan/recovered_records2.json", "r", encoding="utf-8") as f:
    records = json.load(f)

def infer_file_name(r):
    wt = str(r.get("work_type", "")).lower()
    
    # equipment_transfers
    if "old_employee" in r or "new_employee" in r or "transfer_date" in r:
        return "equipment_transfers.json"
        
    # cartridge_replacements
    if wt == "cartridge" or "cartridge_color" in r or "картридж" in wt:
        return "cartridge_replacements.json"
        
    # pc_cleanings
    if "чистка" in wt or "пыли" in wt or "системный блок" in str(r.get("equipment_model", "")).lower() or "системный блок" in str(r.get("equipment_type", "")).lower() or "сб " in str(r.get("equipment_type", "")).lower() or "pc_cleaning" in wt:
        return "pc_cleanings.json"
        
    # component_replacements
    if "replaced_part" in r or "component_replacement" in wt:
        return "component_replacements.json"
        
    # battery_replacements
    if "аккумулятор" in wt or "battery" in str(r.get("component_type", "")).lower() or "battery" in wt:
        return "battery_replacements.json"

    # unfound_equipment
    if "INV_NO" in r or "inventory_number" in r:
        if "TYPE_NAME" in r or "equipment_type" in r:
            if "EMPLOYEE_NAME" in r or "employee_name" in r:
                return "unfound_equipment.json"
                
    if "db_name" in r and "branch" in r and "location" in r:
        if "PART_NO" in r or "CI_TYPE" in r:
            return "unfound_equipment.json"

    # The rest goes to pc_cleanings.json as per our count alignment
    return "UNKNOWN"

stats = {}

for r in records:
    fn = infer_file_name(r)
    if fn == "UNKNOWN":
        fn = "pc_cleanings.json"
        
    res = store.merge_json_payload(fn, [r], conflict_policy="keep_sqlite")
    if fn not in stats:
        stats[fn] = 0
    stats[fn] += res.get("imported", 0) + res.get("updated", 0)
    
print("Restored records by file:")
for k, v in stats.items():
    print(f"{k}: {v}")
