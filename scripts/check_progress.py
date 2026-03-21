import os
import csv
from collections import defaultdict
from pathlib import Path

def get_supabase():
    from supabase import create_client
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )

def main():
    sb = get_supabase()
    user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
    book_key = "moe-target1900"
    target_date = "2026-03-21"
    
    # 1. Fetch review_log for the target date
    # Fetching all logs for the user to be safe and filtering in python
    print("Fetching logs from Supabase...")
    response = sb.table("review_log") \
                 .select("word_key, rating, reviewed_at") \
                 .eq("user_id", user_id) \
                 .eq("book_key", book_key) \
                 .execute()
    
    logs = response.data
    date_logs = [log for log in logs if log['reviewed_at'].startswith(target_date)]
    
    print(f"Found {len(date_logs)} review logs for {target_date}")
    
    # 2. Map word_key to word from CSV
    csv_path = Path("moe-vocab/data/target1900_master_enriched.csv")
    word_map = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            word_map[str(row["id"])] = row["word"].strip()
            
    # 3. Aggregate progress (correct vs incorrect)
    # rating: 4 = correct, 1 = incorrect
    results = defaultdict(lambda: {"correct": 0, "incorrect": 0})
    for log in date_logs:
        wk = log["word_key"]
        if log["rating"] == 4:
            results[wk]["correct"] += 1
        elif log["rating"] == 1:
            results[wk]["incorrect"] += 1
            
    # 4. Print results
    print("--- 3/21 Word Learning Progress ---")
    for wk, stats in sorted(results.items(), key=lambda x: int(x[0])):
        word = word_map.get(wk, f"Unknown (ID: {wk})")
        print(f"Word: {word} (ID: {wk}) - Correct: {stats['correct']} times, Incorrect: {stats['incorrect']} times")

if __name__ == "__main__":
    main()
