import os
import json
from datetime import datetime, timezone, timedelta
from supabase import create_client

url = "https://uzpmpjkkwapaohleejtt.supabase.co"
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")

if not key:
    # Use the key found in .bashrc if not in env
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjk3OTMyOSwiZXhwIjoyMDg4NTU1MzI5fQ.KTyO6-LtHEv1g4d-Sv7qvTE-bep82n-j9cXLXmg3Vkc"

sb = create_client(url, key)

MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

affected_keys = [
    "1507", "1511", "1523", "1526", "1527", "1528", "1529", "1608", "1617", "1630",
    "1631", "1637", "1638", "1639", "1640", "1641", "1642", "1643", "1644", "1645", "1646"
]

# Fetch the current state from progress_sync
rows = sb.table("progress_sync") \
    .select("word_key, status, ease_factor, interval_days, repetitions, last_studied, next_review, last_session_version") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .in_("word_key", affected_keys) \
    .execute() \
    .data

print(f"--- progress_sync current state for {len(rows)} affected words ---")
for r in sorted(rows, key=lambda x: int(x['word_key'])):
    
    # Convert timestamps to JST for easier reading
    ls_jst = ""
    if r.get('last_studied'):
        try:
            ls_utc = datetime.fromisoformat(r['last_studied'].replace('Z', '+00:00'))
            ls_jst = ls_utc.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S JST')
        except:
            ls_jst = r['last_studied']

    nr_jst = ""
    if r.get('next_review'):
        try:
            nr_utc = datetime.fromisoformat(r['next_review'].replace('Z', '+00:00'))
            nr_jst = nr_utc.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S JST')
        except:
            nr_jst = r['next_review']
            
    print(f"[{r['word_key']}] status: {r['status']}, ease: {r['ease_factor']}, int: {r['interval_days']}, rep: {r['repetitions']}, ls: {ls_jst}, nr: {nr_jst}, ver: {r['last_session_version']}")
