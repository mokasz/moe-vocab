import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from supabase import create_client
from dotenv import load_dotenv

# プロジェクトルートの1つ上の .env を読み込む
DOTENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=DOTENV_PATH)

def sm2_update(ease: float, interval: int, repetitions: int, quality: int):
    if quality < 2:
        return ease, 1, 0
    ease = max(1.3, ease + 0.1 - (4 - quality) * 0.08)
    repetitions += 1
    if repetitions == 1:
        interval = 3
    elif repetitions == 2:
        interval = 6
    else:
        interval = round(interval * ease)
    return ease, interval, repetitions

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        print("Error: Missing SUPABASE_URL or SUPABASE_SECRET_KEY")
        return
        
    sb = create_client(url, key)
    
    user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
    book_key = "moe-target1900"
    
    # 1. Fetch 3/25 logs
    print("Fetching 3/25 logs...")
    response = sb.table("review_log") \
                 .select("word_key, rating, reviewed_at") \
                 .eq("user_id", user_id) \
                 .eq("book_key", book_key) \
                 .gte("reviewed_at", "2026-03-24T15:00:00Z") \
                 .lte("reviewed_at", "2026-03-25T23:59:59Z") \
                 .execute()
                 
    logs = response.data
    if not logs:
        print("No logs to process.")
        return
        
    word_ratings = defaultdict(list)
    for log in logs:
        word_ratings[str(log["word_key"])].append(log["rating"])
        
    # 2. Determine quality (1 in ratings -> 0, else -> 4)
    # これは旧Pythonスクリプトと同じ「最悪評価優先」のロジックです
    word_quality = {}
    for wk, ratings in word_ratings.items():
        word_quality[wk] = 0 if 1 in ratings else 4
        
    word_keys = list(word_quality.keys())
    print(f"Found {len(word_keys)} unique words studied on 3/25.")
    
    # 3. Fetch current progress
    prog_resp = sb.table("progress_sync") \
                  .select("word_key, ease_factor, interval_days, repetitions, last_studied") \
                  .eq("user_id", user_id) \
                  .eq("book_key", book_key) \
                  .in_("word_key", word_keys) \
                  .execute()
                  
    current_prog = {str(p["word_key"]): p for p in prog_resp.data}
    
    updates = []
    # 3/25を基準日とする
    base_date = datetime(2026, 3, 25, tzinfo=timezone.utc)
    current_time_s = int(datetime.now().timestamp())
    
    for wk, quality in word_quality.items():
        prog = current_prog.get(wk, {})
        ease = prog.get("ease_factor")
        interval = prog.get("interval_days")
        reps = prog.get("repetitions")
        
        ease = ease if ease is not None else 2.5
        interval = interval if interval is not None else 1
        reps = reps if reps is not None else 0
        
        # SM-2計算
        new_ease, new_interval, new_reps = sm2_update(ease, interval, reps, quality)
        
        # 新仕様の next_review 計算（絶対時刻）
        next_review_dt = base_date + timedelta(days=new_interval)
        next_review_iso = next_review_dt.isoformat()
        
        status = "green" if quality >= 2 else "red"
        
        update_data = {
            "user_id": user_id,
            "book_key": book_key,
            "word_key": wk,
            "ease_factor": new_ease,
            "interval_days": new_interval,
            "repetitions": new_reps,
            "status": status,
            "next_review": next_review_iso,
            # 擬似的なセッションID（UNIXタイムスタンプ）を付与し、次回フロントで「解き直し」と誤認されないようにする
            "last_session_version": current_time_s 
        }
        
        # 最後に学習した日付が空なら埋める
        if "last_studied" not in prog or not prog["last_studied"]:
             update_data["last_studied"] = "2026-03-25"
             
        updates.append(update_data)
        
    print(f"Preparing to upsert updates for {len(updates)} words...")
    
    # 4. Upsert progress
    res = sb.table("progress_sync").upsert(updates, on_conflict="user_id,book_key,word_key").execute()
    print("Done! Successfully recovered and updated SM-2 for 3/25 words.")

if __name__ == "__main__":
    main()
