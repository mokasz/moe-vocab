import json
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
BOOK_KEY = "moe-target1900"

# Find words reviewed multiple times on 3/27 (between 3/27 23:42 JST and now)
# which is roughly the last 6 hours
since = datetime.now(timezone.utc) - timedelta(hours=6)
log_response = sb.table("review_log") \
                 .select("word_key, rating") \
                 .eq("user_id", USER_ID) \
                 .gte("reviewed_at", since.isoformat()) \
                 .execute()

log_counts = defaultdict(int)
for r in log_response.data:
    log_counts[r['word_key']] += 1

multi_click_words = [k for k, v in log_counts.items() if v > 1]
print(f"Found {len(multi_click_words)} words reviewed multiple times recently.")

if multi_click_words:
    prog_resp = sb.table("progress_sync") \
                  .select("word_key, status, ease_factor, interval_days, repetitions, next_review, last_session_version, last_studied") \
                  .eq("user_id", USER_ID) \
                  .in_("word_key", multi_click_words) \
                  .execute()
    
    print("\nState of these words in progress_sync:")
    for r in prog_resp.data[:10]:
        print(f"  Word: {r['word_key']}, status={r['status']}, interval={r['interval_days']}, reps={r['repetitions']}, next_review={r['next_review']}")
        
    # Let's check why they didn't make it into today's selection
    now_iso = datetime.now(timezone.utc).isoformat()
    print(f"\nCurrent time (UTC): {now_iso}")
    
    for r in prog_resp.data[:5]:
        next_rev = r['next_review']
        if next_rev:
            print(f"  Word {r['word_key']} next_review ({next_rev}) <= now ({now_iso}) ? {next_rev <= now_iso}")
