import os
import json
from collections import defaultdict
from supabase import create_client
from datetime import datetime, timedelta, timezone

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("Missing env vars")
        return
        
    sb = create_client(url, key)

    user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
    book_key = "moe-target1900"

    print(f"Fetching all recent logs for user {user_id}...")
    response = sb.table("review_log") \
                 .select("word_key, rating, reviewed_at") \
                 .eq("user_id", user_id) \
                 .eq("book_key", book_key) \
                 .order("reviewed_at", desc=True) \
                 .limit(500) \
                 .execute()

    logs = response.data
    if not logs:
        print("No logs found.")
        return
        
    # Load all words to show actual word text
    words_map = {}
    if os.path.exists("data/words.json"):
        with open("data/words.json", "r", encoding="utf-8") as f:
            words_data = json.load(f)
            words_map = {str(w["id"]): w["word"] for w in words_data.get("words", [])}

    # Group by logical JST date (UTC + 5 hours for the 4AM cutoff)
    logs_by_date = defaultdict(list)
    for log in logs:
        # reviewed_at is ISO 8601 UTC
        dt = datetime.fromisoformat(log["reviewed_at"].replace('Z', '+00:00'))
        # JST Logical date (subtract 4 hours from JST = add 5 hours to UTC)
        logical_date = (dt + timedelta(hours=5)).strftime("%Y-%m-%d")
        logs_by_date[logical_date].append(log)

    print("\n--- Summary of Recent Progress ---")
    for date_key in sorted(logs_by_date.keys(), reverse=True)[:3]: # Show last 3 days
        date_logs = logs_by_date[date_key]
        
        word_stats = defaultdict(lambda: {"correct": 0, "incorrect": 0})
        for log in date_logs:
            word_key = str(log["word_key"])
            if log["rating"] == 4:
                word_stats[word_key]["correct"] += 1
            elif log["rating"] == 1:
                word_stats[word_key]["incorrect"] += 1
                
        print(f"\nProgress for Logical Date: {date_key}")
        print(f"{'Word ID':<8} | {'Word':<15} | {'Correct (✅)':<12} | {'Incorrect (❌)':<14}")
        print("-" * 55)
        
        total_correct = 0
        total_incorrect = 0
        for word_key, stats in sorted(word_stats.items(), key=lambda x: int(x[0])):
            word = words_map.get(word_key, "Unknown")
            c = stats["correct"]
            i = stats["incorrect"]
            total_correct += c
            total_incorrect += i
            print(f"{word_key:<8} | {word:<15} | {c:<12} | {i:<14}")
            
        print("-" * 55)
        print(f"Total actions: {len(date_logs)}")
        print(f"Total Correct: {total_correct}, Total Incorrect: {total_incorrect}")

if __name__ == "__main__":
    main()
