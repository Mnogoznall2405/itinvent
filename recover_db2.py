import os
import json

db_path = "C:/Project/Image_scan/data/local_store.db"
wal_path = "C:/Project/Image_scan/data/local_store.db-wal"

def recover_json_from_file(file_path):
    print(f"Scanning {file_path} for lost JSON...")
    if not os.path.exists(file_path):
        return []
    
    with open(file_path, "rb") as f:
        data = f.read()
        
    results = []
    decoder = json.JSONDecoder()
    
    # We look for utf-8 encoded "Первомайская" or "19/21" 
    # Actually, let's just find every occurence of '{"' and try to parse it as JSON
    # It might be very slow but it'll find everything.
    # To speed it up, we only try parsing if the block contains our target string.
    
    # Step 1: Find all indices of target strings
    search_bytes = [b"\xd0\x9f\xd0\xb5\xd1\x80\xd0\xb2\xd0\xbe\xd0\xbc\xd0\xb0\xd0\xb9\xd1\x81\xd0\xba\xd0\xb0\xd1\x8f", b"19/21"]
    
    target_indices = []
    for sb in search_bytes:
        idx = 0
        while True:
            idx = data.find(sb, idx)
            if idx == -1: break
            target_indices.append(idx)
            idx += 1
            
    target_indices = sorted(list(set(target_indices)))
    
    # For each index, scan backwards to find the nearest '{"' that might be the start
    seen_starts = set()
    for idx in target_indices:
        # scan backwards up to 3000 bytes
        start_scan = max(0, idx - 3000)
        chunk = data[start_scan:idx]
        
        # find all '{"' in this chunk
        pos = 0
        while True:
            pos = chunk.find(b'{"', pos)
            if pos == -1: break
            
            actual_start = start_scan + pos
            if actual_start not in seen_starts:
                seen_starts.add(actual_start)
                
                # Extract a big enough string to decode
                try_chunk = data[actual_start:actual_start+8000]
                try:
                    text_chunk = try_chunk.decode('utf-8', errors='ignore')
                    obj, end_idx = decoder.raw_decode(text_chunk)
                    if isinstance(obj, dict):
                        # Ensure it's related
                        if 'branch' in obj or '19/21' in json.dumps(obj, ensure_ascii=False):
                            if obj not in results:
                                results.append(obj)
                except json.JSONDecodeError:
                    pass
            pos += 1
            
    return results

recovered = recover_json_from_file(db_path)
recovered.extend(recover_json_from_file(wal_path))

# Also, there's a JSON backup from Feb 17! Let's read from the zip!
import zipfile
zip_path = "C:/Project/Image_scan/backups/json/json_backup_20260217_195859.zip"
if os.path.exists(zip_path):
    print("Reading from zip backup...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith('.json'):
                    text = zf.read(name).decode('utf-8')
                    try:
                        arr = json.loads(text)
                        if isinstance(arr, list):
                            for obj in arr:
                                if isinstance(obj, dict):
                                    br = str(obj.get('branch', ''))
                                    if 'Первомайская' in br or '19/21' in br:
                                        if obj not in recovered:
                                            recovered.append(obj)
                        elif isinstance(arr, dict):
                            for k, obj in arr.items():
                                if isinstance(obj, dict):
                                    br = str(obj.get('branch', ''))
                                    if 'Первомайская' in br or '19/21' in br:
                                        if obj not in recovered:
                                            recovered.append(obj)
                    except Exception:
                        pass
    except Exception as e:
        print(e)
else:
    print("Zip not found.")
    

unique_recovered = []
# Need a stable hash, but `obj` might have floating point? Just use sort_keys.
hashes = set()
for r in recovered:
    s = json.dumps(r, sort_keys=True, ensure_ascii=False)
    if s not in hashes:
        hashes.add(s)
        unique_recovered.append(r)

print(f"Recovered {len(unique_recovered)} unique JSON records!")
with open("C:/Project/Image_scan/recovered_records2.json", "w", encoding="utf-8") as f:
    json.dump(unique_recovered, f, ensure_ascii=False, indent=2)

print("Saved to recovered_records2.json")
