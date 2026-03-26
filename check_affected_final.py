import sys
import json
from pathlib import Path
sys.path.append("/Users/shiwei.zhu/Claude/anki-studio/moe-vocab")
from scripts.generate_words import get_supabase, MOE_USER_ID, BOOK_KEY, load_master_csv

sb = get_supabase()
words_map = {str(w['id']): w['word'] for w in load_master_csv()}

affected_keys = ["1507", "1511", "1523", "1526", "1527", "1528", "1529", "1608", "1617", "1630", "1631", "1637", "1638", "1639", "1640", "1641", "1642", "1643", "1644", "1645", "1646"]

rows = sb.table("progress_sync").select("word_key, status, ease_factor, interval_days, repetitions, last_studied, next_review, last_session_version").eq("user_id", MOE_USER_ID).eq("book_key", BOOK_KEY).in_("word_key", affected_keys).execute().data

print(f"Found {len(rows)} affected words:")
for r in rows:
    r['word'] = words_map.get(r['word_key'])
    print(json.dumps(r, sort_keys=True, ensure_ascii=False))

