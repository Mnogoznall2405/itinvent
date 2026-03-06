import os
import re
import json

db_path = "C:/Project/Image_scan/data/local_store.db"
wal_path = "C:/Project/Image_scan/data/local_store.db-wal"

def recover_json_from_file(file_path):
    print(f"Scanning {file_path} for lost JSON...")
    if not os.path.exists(file_path):
        return []
    
    with open(file_path, "rb") as f:
        data = f.read()
        
    # We want to find JSON objects that contain "Первомайская" or "19/21" 
    # Usually the JSON is encoded in utf-8, and looks like {"db_name": ... "branch": "Первомайская 19/21" ...}
    # It might be enclosed in SQLite text structures but the raw JSON string is just bytes.
    # Searching for json-like structures that have branch info:
    results = []
    
    # Simple regex to extract JSON objects. Because JSON may contain nested structures or brackets, 
    # it's tricky, but since they are flat or semi-flat objects, we can look for "{" ... "}"
    # Let's find index of "Первомайская 19/21" and trace back to the closest "{" and forward to closest "}"
    # Wait, the string was just "Первомайская" or "19/21". Let's look for "19/21" and "Первомайская"
    search_bytes = [b"\xd0\x9f\xd0\xb5\xd1\x80\xd0\xb2\xd0\xbe\xd0\xbc\xd0\xb0\xd0\xb9\xd1\x81\xd0\xba\xd0\xb0\xd1\x8f", b"19/21"]
    
    for s_byte in search_bytes:
        idx = 0
        while True:
            idx = data.find(s_byte, idx)
            if idx == -1:
                break
            
            # Find the start of JSON
            start_idx = data.rfind(b'{"', 0, idx)
            if start_idx != -1 and (idx - start_idx) < 1000:
                # Find end of JSON
                end_idx = data.find(b'}', idx)
                if end_idx != -1 and (end_idx - start_idx) < 2500:
                    json_bytes = data[start_idx:end_idx+1]
                    try:
                        json_str = json_bytes.decode('utf-8')
                        obj = json.loads(json_str)
                        if isinstance(obj, dict) and 'branch' in obj:
                            # It's a valid local_records JSON!
                            if obj not in results:
                                results.append(obj)
                    except Exception:
                        pass
            idx += 1
            
    return results

recovered = recover_json_from_file(db_path)
recovered.extend(recover_json_from_file(wal_path))

# Deduplicate
unique_recovered = []
hashes = set()
for r in recovered:
    s = json.dumps(r, sort_keys=True)
    if s not in hashes:
        hashes.add(s)
        unique_recovered.append(r)

print(f"Recovered {len(unique_recovered)} unique JSON records!")
with open("C:/Project/Image_scan/recovered_records.json", "w", encoding="utf-8") as f:
    json.dump(unique_recovered, f, ensure_ascii=False, indent=2)

print("Saved to recovered_records.json")
