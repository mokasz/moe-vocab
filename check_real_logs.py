import os
import sys
import json
from datetime import datetime, timezone, timedelta
from supabase import create_client

# Explicitly load the keys from the parent directory .env
env_vars = {}
with open("../.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            env_vars[k] = v.strip("\"'\n")

url = env_vars.get("SUPABASE_URL")
key = env_vars.get("SUPABASE_SERVICE_ROLE_KEY") or env_vars.get("SUPABASE_SERVICE_KEY")

if not url or not key:
    print("Failed to load Supabase credentials.")
    sys.exit(1)

sb = create_client(url, key)
MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

# Fetch today's logs specifically
rows = sb.table("review_log") \
    .select("word_key, rating, reviewed_at") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .order("reviewed_at", desc=True) \
    .limit(1000) \
    .execute() \
    .data

results = {}
for r in rows:
    try:
        dt_str = r['reviewed_at'].replace('Z', '+00:00')
        dt_utc = datetime.fromisoformat(dt_str)
        dt_jst = dt_utc.astimezone(timezone(timedelta(hours=9)))
        if dt_jst.strftime('%Y-%m-%d') == '2026-03-26':
            wk = r['word_key']
            if wk not in results:
                results[wk] = []
            results[wk].append({"rating": r['rating'], "time": dt_jst.strftime('%H:%M:%S')})
    except Exception:
        continue

print(f"Found logs for {len(results)} words today.")
for wk, logs in sorted(results.items(), key=lambda x: int(x[0])):
    print(f"[{wk}]: {logs}")
