import os
from datetime import datetime, timezone, timedelta
from supabase import create_client

url = "https://uzpmpjkkwapaohleejtt.supabase.co"
key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5NzkzMjksImV4cCI6MjA4ODU1NTMyOX0.vnmV6eC05k4BRMR3SgrJBrn5x0gb0_4wI9_L39pGfl0"

sb = create_client(url, key)

MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"

rows = sb.table("review_log") \
    .select("word_key, rating, reviewed_at, user_id") \
    .eq("user_id", MOE_USER_ID) \
    .order("reviewed_at", desc=True) \
    .limit(20) \
    .execute() \
    .data

print("Latest 20 logs for Moe:")
for r in rows:
    dt_str = r['reviewed_at'].replace('Z', '+00:00')
    dt_utc = datetime.fromisoformat(dt_str)
    dt_jst = dt_utc.astimezone(timezone(timedelta(hours=9)))
    print(f"JST: {dt_jst}, Word: {r['word_key']}, Rating: {r['rating']}")
