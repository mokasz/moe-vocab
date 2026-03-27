import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SECRET_KEY")
sb = create_client(url, key)
USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
BOOK_KEY = "moe-target1900"

resp = sb.table("progress_sync").select("word_key, next_review").eq("user_id", USER_ID).eq("word_key", "1507").execute()
print(f"Exact next_review for 1507: {resp.data[0]['next_review']}")
