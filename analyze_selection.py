import json
import os
from pathlib import Path
from collections import defaultdict
from supabase import create_client

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_SECRET_KEY not set.")
        return
        
    sb = create_client(url, key)
    user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
    book_key = "moe-target1900"
    target_date = "2026-03-24"
    
    # Load selected words
    data = json.loads(Path("data/words.json").read_text())
    words = data["words"]
    
    # We need to know which words were 'red' on the *previous* session
    # A word is red if its last review rating was 1 (quality=0)
    # Actually, generate_words.py calculates quality from review_log.
    
    # Let's fetch the latest review_log for all selected words
    selected_ids = [str(w["id"]) for w in words]
    response = sb.table("review_log") \
                 .select("word_key, rating, reviewed_at") \
                 .eq("user_id", user_id) \
                 .eq("book_key", book_key) \
                 .in_("word_key", selected_ids) \
                 .execute()
    
    logs = response.data
    log_map = defaultdict(list)
    for log in logs:
        log_map[log["word_key"]].append(log)
        
    for k in log_map:
        log_map[k].sort(key=lambda x: x["reviewed_at"], reverse=True)
    
    reasons = {"red": [], "due": [], "new": []}
    
    for w in words:
        wk = str(w["id"])
        last_seen = w.get("lastSeen")
        
        if not last_seen:
            reasons["new"].append(w)
        else:
            # Check if it was red (rating 1) on the last review
            last_logs = log_map.get(wk, [])
            if last_logs:
                # Get logs from the last_seen date
                last_date_logs = [log for log in last_logs if log["reviewed_at"].startswith(last_seen[:10])]
                if last_date_logs and any(log["rating"] == 1 for log in last_date_logs):
                    reasons["red"].append(w)
                else:
                    reasons["due"].append(w)
            else:
                reasons["due"].append(w)
                
    print(f"=== 3/24 選ばれた50語の選定理由 ===")
    print(f"1. 前回不正解 (red枠): {len(reasons['red'])}語")
    print(f"2. 復習時期到来 (due枠): {len(reasons['due'])}語")
    print(f"3. 新規単語 (new枠): {len(reasons['new'])}語")
    print("-" * 40)
    
    if reasons["red"]:
        print("\n【1. 前回不正解 (red)】: 優先して復習")
        for w in sorted(reasons["red"], key=lambda x: x["id"]):
            print(f"- {w['word']} (ID: {w['id']}) - 前回学習日: {w['lastSeen'][:10]}")
            
    if reasons["due"]:
        print("\n【2. 復習時期到来 (due)】: 忘却曲線上、今日が復習日の単語")
        for w in sorted(reasons["due"], key=lambda x: x["id"]):
            print(f"- {w['word']} (ID: {w['id']}) - 前回学習日: {w['lastSeen'][:10]} -> 次回予定日: {w.get('nextReview', '不明')[:10]}")
            
    if reasons["new"]:
        print("\n【3. 新規単語 (new)】: 今回初めて学習する単語 (最低10枠保証)")
        for w in sorted(reasons["new"], key=lambda x: x["id"]):
            print(f"- {w['word']} (ID: {w['id']})")

if __name__ == "__main__":
    main()
