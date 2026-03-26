import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.append("/Users/shiwei.zhu/Claude/anki-studio/moe-vocab")

env_vars = {}
try:
    with open("../.env") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env_vars[k] = v.strip("\"'\n")
except:
    pass

url = env_vars.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
key = env_vars.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")

if not url or not key:
    print("Keys not found")
    sys.exit(1)

from supabase import create_client
sb = create_client(url, key)

MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

from scripts.generate_words import load_master_csv
words = {str(w['id']): w['word'] for w in load_master_csv()}

rows = sb.table("review_log") \
    .select("word_key, rating, reviewed_at") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .order("reviewed_at", desc=True) \
    .limit(100) \
    .execute() \
    .data

print(f"Fetched {len(rows)} rows.")
for r in rows[:10]:
    print(r)
