from datetime import date, timedelta
from pathlib import Path
import sys

# Append the project path to sys.path
sys.path.append("/Users/shiwei.zhu/Claude/anki-studio/moe-vocab")
from scripts.generate_words import load_master_csv, load_progress, get_supabase, update_sm2_and_save

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

print(f"Number of targets for SM-2 update: {len(targets)}")
for t in targets:
    print(f"Target: id={t['id']} word={t['word']} lastSeen={t['lastSeen']} nextReview={t['nextReview']}")
