import os
import json
from collections import defaultdict
from supabase import create_client
import time

def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    # 接続試行
    for attempt in range(3):
        try:
            sb = create_client(url, key)
            user_id = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
            book_key = "moe-target1900"
            target_date = "2026-03-25"

            # 3/25のログを取得
            response = sb.table("review_log") \
                         .select("word_key, rating, reviewed_at") \
                         .eq("user_id", user_id) \
                         .eq("book_key", book_key) \
                         .gte("reviewed_at", "2026-03-24T15:00:00Z") \
                         .lte("reviewed_at", "2026-03-25T23:59:59Z") \
                         .execute()
            
            logs = response.data
            break
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    else:
        print("All attempts failed.")
        return

    if not logs:
        print("No logs found for the period around 2026-03-25.")
        return

    # 単語マスタ読み込み
    words_map = {}
    if os.path.exists("data/words.json"):
        with open("data/words.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            words_map = {str(w["id"]): w["word"] for w in data.get("words", [])}

    # 集計 (JSTでの3/25分を抽出)
    # UTC + 9h が JST 3/25 00:00-23:59 になる範囲
    stats = defaultdict(lambda: {"correct": 0, "incorrect": 0})
    count = 0
    for log in logs:
        # 簡易的に UTC 3/24 15:00 以降を JST 3/25 とみなす
        stats[str(log["word_key"])]["correct" if log["rating"] == 4 else "incorrect"] += 1
        count += 1

    print(f"\n--- 3/25 学習進捗レポート ({count}件のログ) ---")
    print(f"{'ID':<6} | {'単語':<15} | {'正解(✅)':<8} | {'不正解(❌)':<8}")
    print("-" * 50)
    for wk, s in sorted(stats.items(), key=lambda x: int(x[0])):
        word = words_map.get(wk, "不明")
        print(f"{wk:<6} | {word:<15} | {s['correct']:<8} | {s['incorrect']:<8}")

if __name__ == "__main__":
    main()
