import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SECRET_KEY")
sb = create_client(url, key)
USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

resp = sb.table("progress_sync").select("word_key, status, next_review").eq("user_id", USER_ID).lte("next_review", "2026-03-28").execute()

red_count = sum(1 for r in resp.data if r['status'] == 'red')
green_count = sum(1 for r in resp.data if r['status'] == 'green')
print(f"Total red words due today: {red_count}")
print(f"Total green words due today: {green_count}")
