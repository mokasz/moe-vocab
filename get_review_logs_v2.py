import os
import sys
from datetime import datetime, timezone, timedelta
from supabase import create_client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_KEY")

if not url or not key:
    print(f"Error: Credentials missing. URL={url is not None}, KEY={key is not None}")
    sys.exit(1)

sb = create_client(url, key)
MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

# Fetch logs for today (2026-03-26)
# We fetch a larger amount and filter in Python for safety regarding timezones
rows = sb.table("review_log") \
    .select("word_key, rating, reviewed_at") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .order("reviewed_at", asc=True) \
    .limit(1000) \
    .execute() \
    .data

print(f"Total rows fetched: {len(rows)}")

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
    except Exception as e:
        print(f"Error parsing row: {e}")

if not results:
    print("No logs found for 2026-03-26.")
else:
    for wk in sorted(results.keys(), key=lambda x: int(x)):
        logs = results[wk]
        print(f"Word {wk}: {logs}")

