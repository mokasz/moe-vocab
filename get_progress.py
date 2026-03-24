import os
import csv
from collections import defaultdict
from pathlib import Path
from supabase import create_client

def main():
    url = "https://uzpmpjkkwapaohleejtt.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5NzkzMjksImV4cCI6MjA4ODU1NTMyOX0.vnmV6eC05k4BRMR3SgrJBrn5x0gb0_4wI9_L39pGfl0"
    sb = create_client(url, key)
    
    # Using the user_id found in scripts/check_progress.py
    user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
    book_key = "moe-target1900"
    target_date = "2026-03-23"
    
    print(f"Fetching logs for user {user_id} on {target_date}...")
    response = sb.table("review_log") \
                 .select("word_key, rating, reviewed_at") \
                 .eq("user_id", user_id) \
                 .eq("book_key", book_key) \
                 .execute()
    
    logs = response.data
    # Filter logs for the specific date
    date_logs = [log for log in logs if log['reviewed_at'].startswith(target_date)]
    
    if not date_logs:
        print(f"No logs found for {target_date}.")
        # Let's list available dates to be helpful
        dates = sorted(list(set(log['reviewed_at'][:10] for log in logs)))
        print(f"Available dates: {', '.join(dates)}")
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
    results = defaultdict(lambda: {"correct": 0, "incorrect": 0})
    for log in date_logs:
        wk = log["word_key"]
        # rating: 4 = correct, 1 = incorrect (based on index.html: quality >= 4 ? 'green' : 'red')
        if log["rating"] >= 4:
            results[wk]["correct"] += 1
        else:
            results[wk]["incorrect"] += 1
            
    print(f"--- {target_date} Word Learning Progress ---")
    for wk, stats in sorted(results.items(), key=lambda x: int(x[0])):
        word = word_map.get(wk, f"Unknown (ID: {wk})")
        print(f"Word: {word} (ID: {wk}) - Correct: {stats['correct']}, Incorrect: {stats['incorrect']}")

if __name__ == "__main__":
    main()
