import os
import json
from collections import defaultdict
from supabase import create_client
from datetime import datetime, timedelta, timezone

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    sb = create_client(url, key)

    user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
    book_key = "moe-target1900"

    # 3/25のログを取得 (UTC 3/24 15:00 ~ 3/25 23:59)
    response = sb.table("review_log") \
                 .select("word_key, rating, reviewed_at") \
                 .eq("user_id", user_id) \
                 .eq("book_key", book_key) \
                 .gte("reviewed_at", "2026-03-24T15:00:00Z") \
                 .lte("reviewed_at", "2026-03-25T23:59:59Z") \
                 .order("reviewed_at", desc=False) \
                 .execute()
    
    logs = response.data

    # 単語マスタ読み込み
    words_map = {}
    if os.path.exists("data/words.json"):
        with open("data/words.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            words_map = {str(w["id"]): w["word"] for w in data.get("words", [])}

    print(f"\n--- 3/25 学習時刻ログ（JST） ---")
    print(f"{'時刻 (JST)':<20} | {'ID':<6} | {'単語':<15} | {'判定'}")
    print("-" * 55)

    for log in logs:
        # UTCをJSTに変換
        dt_utc = datetime.fromisoformat(log["reviewed_at"].replace('Z', '+00:00'))
        dt_jst = dt_utc.astimezone(timezone(timedelta(hours=9)))
        
        # 実際に3/25のJSTのものだけ表示
        if dt_jst.date().isoformat() == "2026-03-25":
            time_str = dt_jst.strftime("%Y-%m-%d %H:%M:%S")
            word = words_map.get(str(log["word_key"]), "不明")
            status = "✅知ってた" if log["rating"] == 4 else "❌知らなかった"
            print(f"{time_str:<20} | {log['word_key']:<6} | {word:<15} | {status}")

if __name__ == "__main__":
    main()
