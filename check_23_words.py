import json

# The 23 words we identified earlier as having been reviewed multiple times (failed on 3/27)
failed_words_327 = [
    "1507", "1527", "1528", "1529", "1540", "1546", "1549", "1551", "1554", "1640",
    "1641", "1642", "1643", "1644", "1645", "1646", "1647", "1648", "1649", "1650",
    "1652", "1653", "1654", "1655", "1656" # wait, that's 25. Let me just check all of them.
]
# I'll just load the exact 23 words from the DB again to be 100% sure.
from supabase import create_client
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import os
from dotenv import load_dotenv
load_dotenv(dotenv_path="../.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SECRET_KEY")
sb = create_client(url, key)
USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"

since = datetime.now(timezone.utc) - timedelta(hours=6)
log_response = sb.table("review_log").select("word_key, rating").eq("user_id", USER_ID).gte("reviewed_at", since.isoformat()).execute()
log_counts = defaultdict(int)
for r in log_response.data: log_counts[r['word_key']] += 1
multi_click_words = [k for k, v in log_counts.items() if v > 1]
print(f"Verified {len(multi_click_words)} retry words from 3/27.")

with open("data/words.json", "r") as f:
    words_data = json.load(f)
    current_words = {str(w["id"]): w for w in words_data["words"]}

red_bucket = []
due_bucket = []
missing = []

for wk in multi_click_words:
    if wk in current_words:
        w = current_words[wk]
        # In check_categories.py, red=interval:1, due=interval>1
        if w.get("interval", 1) == 1:
            red_bucket.append(wk)
        else:
            due_bucket.append(wk)
    else:
        missing.append(wk)

print(f"Out of the 23 failed words:")
print(f"  - In ❌ 復習枠 (Interval=1): {len(red_bucket)}")
print(f"  - In ✅ 復習枠 (Interval>1): {len(due_bucket)}")
print(f"  - Missing from today's 50 words: {len(missing)}")

if missing:
    print(f"Missing word IDs: {missing}")
    # Let's check their next_review in DB
    resp = sb.table("progress_sync").select("word_key, next_review, status").eq("user_id", USER_ID).in_("word_key", missing).execute()
    for r in resp.data:
        print(f"  DB state for missing word {r['word_key']}: next_review={r['next_review']}, status={r['status']}")

