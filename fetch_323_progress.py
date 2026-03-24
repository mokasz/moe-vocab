import os
import csv
from collections import defaultdict
from pathlib import Path
from supabase import create_client

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not set in environment.")
        return
        
    sb = create_client(url, key)
    
    user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
    book_key = "moe-target1900"
    target_date = "2026-03-23"
    
    print(f"Fetching logs for user {user_id} on {target_date} using SERVICE_KEY...")
    response = sb.table("review_log") \
                 .select("word_key, rating, reviewed_at") \
                 .eq("user_id", user_id) \
                 .eq("book_key", book_key) \
                 .execute()
    
    logs = response.data
    # Filter logs for the specific date (JST is assumed based on previous context, but DB stores UTC or JST depending on setup)
    # The app code uses Date.now() + 9 hours for JST mapping in some places, 
    # but review_log inserts usually use DB default which might be UTC.
    # Let's check all logs and filter in Python.
    
    date_logs = [log for log in logs if log['reviewed_at'].startswith(target_date)]
    
    if not date_logs:
        print(f"No logs found for {target_date} in review_log.")
        all_dates = sorted(list(set(log['reviewed_at'][:10] for log in logs)))
        if all_dates:
            print(f"Available log dates: {', '.join(all_dates)}")
        return

    # Map word_key to word from CSV
    csv_path = Path("data/target1900_master_enriched.csv")
    word_map = {}
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                word_map[str(row["id"])] = row["word"].strip()
    
    # Aggregate progress
    # rating: 4 = correct (green), 1 = incorrect (red)
    results = defaultdict(lambda: {"correct": 0, "incorrect": 0})
    for log in date_logs:
        wk = log["word_key"]
        if log["rating"] >= 4:
            results[wk]["correct"] += 1
        else:
            results[wk]["incorrect"] += 1
            
    print(f"\n--- {target_date} Word Learning Progress ---")
    print(f"{'Word':<15} {'ID':<6} {'Correct':<10} {'Incorrect':<10}")
    print("-" * 45)
    
    for wk, stats in sorted(results.items(), key=lambda x: int(x[0])):
        word = word_map.get(wk, f"Unknown")
        print(f"{word:<15} {wk:<6} {stats['correct']:<10} {stats['incorrect']:<10}")

if __name__ == "__main__":
    main()
