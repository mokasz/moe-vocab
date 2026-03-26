import os
import sys
from datetime import datetime, timezone, timedelta
from supabase import create_client

url = "https://uzpmpjkkwapaohleejtt.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjk3OTMyOSwiZXhwIjoyMDg4NTU1MzI5fQ.KTyO6-LtHEv1g4d-Sv7qvTE-bep82n-j9cXLXmg3Vkc"

sb = create_client(url, key)

MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

# 3/26 JST corresponds to 3/25 15:00 UTC to 3/26 15:00 UTC
# But we can just filter by JST after fetching or use range if possible.
# review_log might have many entries, so let's try to fetch recent ones.

rows = sb.table("review_log") \
    .select("word_key, rating, reviewed_at") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .order("reviewed_at", desc=True) \
    .limit(1000) \
    .execute() \
    .data

# Get word list for mapping ID to word
import csv
from pathlib import Path
CSV_PATH = Path("data/target1900_master_enriched.csv")
words_map = {}
if CSV_PATH.exists():
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            words_map[row["id"]] = row["word"]

results = {}
count_total = 0
for r in rows:
    try:
        dt_str = r['reviewed_at'].replace('Z', '+00:00')
        dt_utc = datetime.fromisoformat(dt_str)
        dt_jst = dt_utc.astimezone(timezone(timedelta(hours=9)))
        if dt_jst.strftime('%Y-%m-%d') == '2026-03-26':
            wk = str(r['word_key'])
            if wk not in results:
                results[wk] = {'correct': 0, 'incorrect': 0}
            if r['rating'] == 4:
                results[wk]['correct'] += 1
            elif r['rating'] == 1:
                results[wk]['incorrect'] += 1
            count_total += 1
    except Exception as e:
        continue

if not results:
    print("2026-03-26の学習記録は見つかりませんでした。")
else:
    print(f"2026-03-26の学習記録 ({count_total}件):")
    for wk, counts in sorted(results.items(), key=lambda x: int(x[0])):
        word = words_map.get(wk, 'Unknown')
        print(f"[{wk}] {word}: 正解 {counts['correct']} 回, 不正解 {counts['incorrect']} 回")
