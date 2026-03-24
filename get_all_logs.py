import os
from supabase import create_client

def main():
    url = "https://uzpmpjkkwapaohleejtt.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5NzkzMjksImV4cCI6MjA4ODU1NTMyOX0.vnmV6eC05k4BRMR3SgrJBrn5x0gb0_4wI9_L39pGfl0"
    sb = create_client(url, key)
    
    print("Fetching ALL logs from review_log (no user_id filter)...")
    try:
        response = sb.table("review_log").select("user_id, word_key, rating, reviewed_at").execute()
        logs = response.data
        if not logs:
            print("No logs returned (RLS might be blocking or table is empty).")
        else:
            print(f"Found {len(logs)} logs.")
            for log in logs[:10]: # Just first 10
                print(log)
            # Find unique user_ids
            uids = list(set(log['user_id'] for log in logs))
            print(f"Unique User IDs: {uids}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
