from datetime import date, timedelta
import json
from pathlib import Path
import os
import sys

# Append the project path to sys.path
sys.path.append("/Users/shiwei.zhu/Claude/anki-studio/moe-vocab")
from scripts.generate_words import load_master_csv, load_progress, get_supabase, MOE_USER_ID, BOOK_KEY

sb = get_supabase()
words = load_master_csv()
words = load_progress(sb, words)

today = date.today().isoformat()
targets = [
    w for w in words
    if w.get("lastSeen")                        # 未回答はスキップ
    and w.get("lastSeen", "")[:10] < today      # 今日の回答は翌朝に処理
    and w.get("status") in ("green", "red")     # new はスキップ
    and (                                        # SM-2 未反映のみ
        w.get("nextReview") is None
        or w.get("nextReview") <= w.get("lastSeen", "")[:10]
    )
]

print(f"Found {len(targets)} words matching SM-2 update condition:")
for w in targets:
    print(json.dumps({k: v for k, v in w.items() if k in ("id", "word", "status", "lastSeen", "nextReview", "last_session_version")}, ensure_ascii=False))

# Check what was recently logged in review_log for these 3
word_keys = [str(w["id"]) for w in targets]
if word_keys:
    log_rows = (
        sb.table("review_log")
        .select("word_key, rating, reviewed_at")
        .eq("user_id", MOE_USER_ID)
        .eq("book_key", BOOK_KEY)
        .in_("word_key", word_keys)
        .execute()
        .data
    )
    print("Recent review logs for these words:")
    for log in log_rows:
        print(log)

