import os
from collections import defaultdict
from supabase import create_client

def main():
    url = "https://uzpmpjkkwapaohleejtt.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6cG1wamtrd2FwYW9obGVlanR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5NzkzMjksImV4cCI6MjA4ODU1NTMyOX0.vnmV6eC05k4BRMR3SgrJBrn5x0gb0_4wI9_L39pGfl0"
    sb = create_client(url, key)

    user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
    book_key = "moe-target1900"
    target_date = "2026-03-25"

    print(f"Fetching logs for user {user_id} on {target_date}...")
    response = sb.table("review_log") \
                 .select("word_key, rating, reviewed_at") \
                 .eq("user_id", user_id) \
                 .eq("book_key", book_key) \
                 .execute()

    logs = response.data
    # Filter logs for the specific date (JST is assumed)
    date_logs = [log for log in logs if log['reviewed_at'].startswith(target_date)]

    if not date_logs:
        print(f"No logs found for {target_date} in review_log.")
        all_dates = sorted(list(set(log['reviewed_at'][:10] for log in logs)))
        if all_dates:
            print(f"Available log dates: {', '.join(all_dates)}")
        return

    # Count correct (4) and incorrect (1) for each word
    word_stats = defaultdict(lambda: {"correct": 0, "incorrect": 0})
    for log in date_logs:
        word_key = str(log["word_key"])
        if log["rating"] == 4:
            word_stats[word_key]["correct"] += 1
        elif log["rating"] == 1:
            word_stats[word_key]["incorrect"] += 1

    # Fetch word details to display the actual word, not just the ID
    words_response = sb.table("progress_sync") \
                       .select("word_key, status") \
                       .eq("user_id", user_id) \
                       .eq("book_key", book_key) \
                       .execute()
    # (Note: progress_sync doesn't have the word string, we need to read from words.json or CSV)
    
    import json
    with open("data/words.json", "r", encoding="utf-8") as f:
        words_data = json.load(f)
        word_dict = {str(w["id"]): w["word"] for w in words_data.get("words", [])}
        
    print(f"\nProgress for {target_date}:")
    print(f"{'Word ID':<8} | {'Word':<15} | {'Correct (✅)':<12} | {'Incorrect (❌)':<14}")
    print("-" * 55)
    
    total_correct = 0
    total_incorrect = 0
    for word_key, stats in sorted(word_stats.items(), key=lambda x: int(x[0])):
        word = word_dict.get(word_key, "Unknown")
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
