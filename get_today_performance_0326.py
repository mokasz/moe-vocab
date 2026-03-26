import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.append("/Users/shiwei.zhu/Claude/anki-studio/moe-vocab")
from scripts.generate_words import get_supabase, MOE_USER_ID, BOOK_KEY, load_master_csv

sb = get_supabase()
words = {str(w['id']): w['word'] for w in load_master_csv()}

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
                results[wk] = {'correct': 0, 'incorrect': 0}
            if r['rating'] == 4:
                results[wk]['correct'] += 1
            elif r['rating'] == 1:
                results[wk]['incorrect'] += 1
    except Exception as e:
        continue

if not results:
    print("本日の学習記録はまだありません。")
else:
    for wk, counts in sorted(results.items(), key=lambda x: int(x[0])):
        word = words.get(wk, 'Unknown')
        print(f"[{wk}] {word}: 正解 {counts['correct']} 回, 不正解 {counts['incorrect']} 回")
