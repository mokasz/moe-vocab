import os
import json
from datetime import datetime, timezone, timedelta
from supabase import create_client

url = "https://uzpmpjkkwapaohleejtt.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjk3OTMyOSwiZXhwIjoyMDg4NTU1MzI5fQ.KTyO6-LtHEv1g4d-Sv7qvTE-bep82n-j9cXLXmg3Vkc"

sb = create_client(url, key)

MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"
AFFECTED_KEYS = [
    "1507", "1511", "1523", "1526", "1527", "1528", "1529", "1608", "1617", "1630",
    "1631", "1637", "1638", "1639", "1640", "1641", "1642", "1643", "1644", "1645", "1646"
]

# Fetch all logs for 3/26
rows = sb.table("review_log") \
    .select("*") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .order("reviewed_at", desc=False) \
    .execute() \
    .data

# Group by word_key and filter by date
logs_by_word = {}
for r in rows:
    try:
        dt_str = r['reviewed_at'].replace('Z', '+00:00')
        dt_utc = datetime.fromisoformat(dt_str)
        dt_jst = dt_utc.astimezone(timezone(timedelta(hours=9)))
        if dt_jst.strftime('%Y-%m-%d') == '2026-03-26':
            wk = str(r['word_key'])
            if wk not in logs_by_word:
                logs_by_word[wk] = []
            logs_by_word[wk].append(r)
    except:
        continue

update_targets = []
backup_data = []

print(f"--- Dry Run: Review Log Fix for 2026-03-26 ---")
print(f"Targeting {len(AFFECTED_KEYS)} words.\n")

for wk in sorted(logs_by_word.keys(), key=lambda x: int(x)):
    word_logs = logs_by_word[wk]
    
    # We only care about words in AFFECTED_KEYS or words with multiple logs
    if wk not in AFFECTED_KEYS and len(word_logs) == 1:
        continue
        
    print(f"[{wk}] Logs found: {len(word_logs)}")
    
    for i, log in enumerate(word_logs):
        dt_str = log['reviewed_at'].replace('Z', '+00:00')
        dt_jst = datetime.fromisoformat(dt_str).astimezone(timezone(timedelta(hours=9)))
        time_jst = dt_jst.strftime('%H:%M:%S')
        
        status_str = "KEEP (1st)" if i == 0 else "UPDATE (2nd+)"
        action_note = ""
        
        if i > 0 and log['rating'] == 1:
            # This is a target for update
            update_targets.append(log['id'])
            backup_data.append(log)
            action_note = f"--> rating 1 to 4"
        elif i == 0:
            action_note = f"(stays {log['rating']})"
        else:
            action_note = f"(already {log['rating']})"

        print(f"  {i+1}. {time_jst} (ID: {str(log['id'])[:8]}...) rating: {log['rating']} {action_note}")

# Save backup
backup_file = "backup_review_log_0326.json"
with open(backup_file, "w") as f:
    json.dump(backup_data, f, indent=2)

print(f"\nTotal records to update: {len(update_targets)}")
print(f"Backup saved to: {backup_file}")
print("\nNo database changes have been made.")
