import os
from datetime import datetime, timezone, timedelta
from supabase import create_client

url = "https://uzpmpjkkwapaohleejtt.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Mjk3OTMyOSwiZXhwIjoyMDg4NTU1MzI5fQ.KTyO6-LtHEv1g4d-Sv7qvTE-bep82n-j9cXLXmg3Vkc"

sb = create_client(url, key)

MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

# Fetch all progress for the user
rows = sb.table("progress_sync") \
    .select("word_key, status, repetitions, last_studied, next_review") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .execute() \
    .data

now_jst = datetime.now(timezone(timedelta(hours=9)))
print(f"Current JST: {now_jst}\n")

studied_count = len(rows)
due_words = []
null_next_review_words = []

for r in rows:
    wk = r['word_key']
    nr = r.get('next_review')
    rep = r.get('repetitions', 0)
    ls = r.get('last_studied')
    
    # Check for null next_review in studied words
    if (rep > 0 or ls) and not nr:
        null_next_review_words.append(wk)
    
    # Check for due words (on or before 3/27 JST)
    if nr:
        try:
            nr_utc = datetime.fromisoformat(nr.replace('Z', '+00:00'))
            nr_jst = nr_utc.astimezone(timezone(timedelta(hours=9)))
            # If next_review is before 3/28 00:00 JST, it's due for 3/27
            if nr_jst < datetime(2026, 3, 28, 0, 0, 0, tzinfo=timezone(timedelta(hours=9))):
                due_words.append({
                    "word_key": wk,
                    "status": r['status'],
                    "next_review": nr_jst.strftime('%Y-%m-%d %H:%M JST'),
                    "rep": rep
                })
        except:
            continue

print(f"Total studied words: {studied_count}")
print(f"Words with NULL next_review (despite being studied): {len(null_next_review_words)}")
if null_next_review_words:
    print(f"  IDs: {sorted(null_next_review_words, key=int)}")

print(f"\nTotal due words for today (up to 3/27): {len(due_words)}")
if due_words:
    print("\nSample of due words (oldest first):")
    for dw in sorted(due_words, key=lambda x: x['next_review'])[:20]:
        print(f"  [{dw['word_key']}] status: {dw['status']}, due: {dw['next_review']}, rep: {dw['rep']}")

# Also check how many 'red' words exist
red_words = [dw for dw in due_words if dw['status'] == 'red']
print(f"\nOf which 'red' status: {len(red_words)}")
