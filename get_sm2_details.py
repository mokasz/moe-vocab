import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.append("/Users/shiwei.zhu/Claude/anki-studio/moe-vocab")
from scripts.generate_words import get_supabase, MOE_USER_ID, BOOK_KEY, load_master_csv

sb = get_supabase()
words_map = {str(w['id']): w for w in load_master_csv()}

# The 3 words we identified earlier were 1503, 1516, 1617
target_keys = ["1503", "1516", "1617"]

print("=== 現在のデータ（更新後） ===")
rows = sb.table("progress_sync") \
    .select("word_key, status, ease_factor, interval_days, repetitions, last_studied, next_review, last_session_version") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .in_("word_key", target_keys) \
    .execute() \
    .data

current_state = {r['word_key']: r for r in rows}
for wk in target_keys:
    print(f"[{wk}] {words_map[wk]['word']}: {current_state[wk]}")

print("\n=== 3/25の review_log ===")
logs = sb.table("review_log") \
    .select("word_key, rating, reviewed_at") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .in_("word_key", target_keys) \
    .order("reviewed_at", desc=True) \
    .execute() \
    .data

for log in logs:
    if "2026-03-25" in log['reviewed_at']:
        print(f"[{log['word_key']}] rating: {log['rating']}, at: {log['reviewed_at']}")
