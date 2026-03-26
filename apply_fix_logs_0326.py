import os
import json
from supabase import create_client

url = "https://uzpmpjkkwapaohleejtt.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjk3OTMyOSwiZXhwIjoyMDg4NTU1MzI5fQ.KTyO6-LtHEv1g4d-Sv7qvTE-bep82n-j9cXLXmg3Vkc"

sb = create_client(url, key)

backup_file = "backup_review_log_0326.json"
try:
    with open(backup_file, "r") as f:
        update_targets = json.load(f)
except Exception as e:
    print(f"Error loading backup file: {e}")
    exit(1)

print(f"Loaded {len(update_targets)} records from backup for update.")

success_count = 0
error_count = 0

for target in update_targets:
    record_id = target['id']
    word_key = target['word_key']
    try:
        # Update the rating to 4
        result = sb.table("review_log").update({"rating": 4}).eq("id", record_id).execute()
        
        # Checking if the update was actually applied by looking at the returned data
        if result.data and len(result.data) > 0 and result.data[0]['rating'] == 4:
            success_count += 1
        else:
            print(f"Failed to update record {record_id} for word {word_key}")
            error_count += 1
            
    except Exception as e:
        print(f"Error updating record {record_id} for word {word_key}: {e}")
        error_count += 1

print(f"\nUpdate completed.")
print(f"Successfully updated: {success_count}")
print(f"Failed to update: {error_count}")
