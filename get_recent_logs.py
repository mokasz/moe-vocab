import os
from collections import defaultdict
from pathlib import Path
from supabase import create_client
from dotenv import load_dotenv

# プロジェクトルートの1つ上の .env を読み込む
DOTENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=DOTENV_PATH)

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_SECRET_KEY not set.")
        return
    sb = create_client(url, key)
    
    user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
    book_key = "moe-target1900"
    
    print(f"Fetching logs for user {user_id}...")
    response = sb.table("review_log") \
                 .select("word_key, rating, reviewed_at") \
                 .eq("user_id", user_id) \
                 .eq("book_key", book_key) \
                 .execute()
    
    logs = response.data
    if not logs:
        print("No logs found for this user.")
        return

    dates = defaultdict(int)
    for log in logs:
        d = log['reviewed_at'][:10]
        dates[d] += 1
        
    print("Log counts by date:")
    for d, count in sorted(dates.items(), reverse=True):
        print(f"  {d}: {count} logs")

if __name__ == "__main__":
    main()
