import sys
from datetime import datetime, timezone, timedelta
from supabase import create_client

sb = create_client(
    "https://uzpmpjkkwapaohleejtt.supabase.co",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5NzkzMjksImV4cCI6MjA4ODU1NTMyOX0.vnmV6eC05k4BRMR3SgrJBrn5x0gb0_4wI9_L39pGfl0"
)

MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

affected_keys = [
    "1507", "1511", "1523", "1526", "1527", "1528", "1529", "1608", "1617", "1630",
    "1631", "1637", "1638", "1639", "1640", "1641", "1642", "1643", "1644", "1645", "1646"
]

rows = sb.table("progress_sync") \
    .select("word_key, status, ease_factor, interval_days, repetitions, last_studied, next_review, last_session_version") \
    .eq("user_id", MOE_USER_ID) \
    .eq("book_key", BOOK_KEY) \
    .in_("word_key", affected_keys) \
    .execute() \
    .data

for r in rows:
    print(r)
