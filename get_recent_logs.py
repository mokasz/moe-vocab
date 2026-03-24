import os
from collections import defaultdict
from supabase import create_client

def main():
    url = "https://uzpmpjkkwapaohleejtt.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5NzkzMjksImV4cCI6MjA4ODU1NTMyOX0.vnmV6eC05k4BRMR3SgrJBrn5x0gb0_4wI9_L39pGfl0"
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
