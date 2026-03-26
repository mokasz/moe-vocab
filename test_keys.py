import json
import os
from supabase import create_client

env_vars = {}
with open(".env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            env_vars[k] = v.strip("\"'\n")

url = env_vars.get("SUPABASE_URL")
key = env_vars.get("SUPABASE_SERVICE_KEY")

sb = create_client(url, key)
MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

affected_keys = ["1507", "1511", "1523", "1526", "1527", "1528", "1529", "1608", "1617", "1630", "1631", "1637", "1638", "1639", "1640", "1641", "1642", "1643", "1644", "1645", "1646"]

rows = sb.table("progress_sync").select("word_key, status, ease_factor, interval_days, repetitions, last_studied, next_review, last_session_version").eq("user_id", MOE_USER_ID).eq("book_key", BOOK_KEY).in_("word_key", affected_keys).execute().data

print(f"Found {len(rows)} affected words:")
for r in rows:
    print(json.dumps(r, sort_keys=True))

