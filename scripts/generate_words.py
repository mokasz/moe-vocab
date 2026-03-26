#!/usr/bin/env python3
"""
generate_words.py — SM-2 単語選定 + 医学系パッセージ生成
SPEC.md (2026-03-25) 準拠: 完全即時計算モデル対応版
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

# ── 設定 ────────────────────────────────────────────────
BOOK_KEY = "moe-target1900"
MOE_USER_EMAIL = "moeloveslemon1921@gmail.com"
MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
DAILY_LIMIT = 50
MIN_NEW = 10

CSV_PATH = Path(__file__).parent.parent / "data" / "target1900_master_enriched.csv"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "words.json"
INDEX_PATH = Path(__file__).parent.parent / "index.html"

MEDICAL_THEMES = [
    "antibiotic resistance",
    "brain neuroscience and cognitive function",
    "medical ethics and patient autonomy",
    "cancer biology and treatment",
    "infectious disease and immunity",
    "mental health and psychology",
    "cardiovascular disease",
    "medical technology and AI in healthcare",
    "organ transplantation and ethics",
    "environmental health and pollution",
]


# ── CSV 読み込み ───────────────────────────────────────────
def load_master_csv() -> list[dict]:
    """Load target1900_master_enriched.csv and return list of word dicts with SM-2 defaults."""
    words = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            words.append({
                "id": int(row["id"]),
                "word": row["word"].strip(),
                "pos": row["pos"].strip(),
                "part": int(row["part"]),
                "section": int(row["section"]),
                "japanese": row["japanese"].strip(),
                "sentence": row["sentence"].strip(),
                "sentence_ja": row["sentence_ja"].strip(),
                # SM-2 デフォルト
                "status": "new",
                "ease": 2.5,
                "interval": 1,
                "repetitions": 0,
                "lastSeen": None,
                "last_session_version": None,
                "nextReview": None,
            })
    return words


# ── Supabase 進捗マージ ────────────────────────────────────
def load_progress(sb, words: list[dict]) -> list[dict]:
    """Load progress_sync records and merge onto words."""
    rows = (
        sb.table("progress_sync")
        .select("word_key,status,ease_factor,interval_days,repetitions,last_studied,next_review,last_session_version")
        .eq("book_key", BOOK_KEY)
        .eq("user_id", MOE_USER_ID)
        .execute()
        .data
    )
    progress_map = {r["word_key"]: r for r in rows}

    for w in words:
        wk = str(w["id"])
        if wk in progress_map:
            p = progress_map[wk]
            w["status"] = p.get("status") or "new"
            v = p.get("ease_factor")
            w["ease"] = v if v is not None else 2.5
            v = p.get("interval_days")
            w["interval"] = v if v is not None else 1
            v = p.get("repetitions")
            w["repetitions"] = v if v is not None else 0
            w["lastSeen"]   = p.get("last_studied")
            w["nextReview"] = p.get("next_review")
            w["last_session_version"] = p.get("last_session_version")

    return words


# ── SM-2 単語選定 ─────────────────────────────────────────
def select_words(words: list[dict], daily_limit: int = DAILY_LIMIT) -> list[dict]:
    """
    単語選択ロジック (SPEC.md 2026-03-25 準拠)
    1. 復習枠 (最大40語): next_review <= now (red優先 -> due)
    2. 新規枠 (最低10語 + α): next_review is None
    合計50語
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    red = []
    due = []
    new = []

    for w in words:
        status = w.get("status", "new")
        next_review = w.get("nextReview")

        if next_review is None:
            new.append(w)
        elif next_review <= now_iso:
            if status == "red":
                red.append(w)
            else:
                due.append(w)
    
    # new の優先順位: Part降順 -> Section昇順 -> ID昇順
    new.sort(key=lambda w: (-w.get("part", 0), w.get("section", 0), w.get("id", 0)))

    # 1. 復習枠 (最大 40語)
    review_limit = daily_limit - MIN_NEW
    review_selected = []
    
    # red を優先
    review_selected.extend(red[:review_limit])
    # 残り枠を due で埋める
    remaining_review = review_limit - len(review_selected)
    if remaining_review > 0:
        review_selected.extend(due[:remaining_review])
    
    # 2. 新規枠 (最低 10語 + α)
    # 復習枠が 40語に満たない場合、その分も新規枠を増やす
    total_new_needed = daily_limit - len(review_selected)
    new_selected = new[:total_new_needed]

    selected = review_selected + new_selected
    return selected


# ── パッセージ生成 ────────────────────────────────────────
def generate_passage(client, words: list[dict]) -> dict:
    """Generate a ~200-word medical reading passage containing today's words."""
    if not words:
        return {}
    
    theme = random.choice(MEDICAL_THEMES)
    selected_words = [w["word"] for w in words[:15]]
    
    prompt = f"""
Create a medical-themed reading passage (approx. 200 words) in English.
Theme: {theme}
Target words to include: {", ".join(selected_words)}

Requirements:
1. The passage must be professional yet accessible.
2. Ensure ALL target words are used naturally.
3. Provide a high-quality Japanese translation.
4. Return ONLY a JSON object with this structure:
{{
  "text": "...",
  "text_ja": "...",
  "theme": "{theme}",
  "highlighted_words": ["word1", "word2", ...]
}}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
            }
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"  WARNING: passage generation failed: {e}")
        return {}


# ── Supabase & Gemini 連携 ─────────────────────────────────
def get_supabase():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not set.")
        sys.exit(1)
    return create_client(url, key)

def get_gemini():
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set.")
        sys.exit(1)
    return genai.Client(api_key=api_key)


# ── メイン ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="moe-vocab SM-2 単語生成スクリプト")
    parser.add_argument("--dry-run", action="store_true", help="Supabase / Gemini をスキップ。")
    parser.add_argument(
        "--section",
        type=int,
        help="このセクション番号の単語のみを対象にする（例: --section 16）",
    )
    args = parser.parse_args()

    print("=== generate_words.py ===")

    # 1. CSV 読み込み
    words = load_master_csv()
    print(f"  loaded {len(words)} words from CSV")

    # セクションフィルタ
    if args.section is not None:
        words = [w for w in words if w["section"] == args.section]
        print(f"  filtered to section {args.section}: {len(words)} words")

    current_time_ms = int(time.time())

    if args.dry_run:
        # Supabase / Gemini スキップ
        selected = select_words(words, daily_limit=DAILY_LIMIT)
        output = {
            "meta": {
                "total": len(selected),
                "source": "target1900",
                "created": date.today().isoformat(),
                "version": current_time_ms,
            },
            "words": selected,
            "passage": {},
        }
        text = json.dumps(output, ensure_ascii=False, indent=2)
        print(f"  [dry-run] selected {len(selected)} words")
        OUTPUT_PATH.write_text(text)
        return

    # 2. Supabase 進捗マージ
    sb = get_supabase()
    words = load_progress(sb, words)
    print("  merged Supabase progress")

    # 3. 単語選定 (SM-2計算はブラウザで行うため、ここでは選定のみ)
    selected = select_words(words, daily_limit=DAILY_LIMIT)
    print(f"  selected {len(selected)} words for today")

    # 4. 医学系パッセージ生成
    client = get_gemini()
    passage = generate_passage(client, selected)
    if passage:
        passage["audio"] = f"passage_{date.today().isoformat()}.mp3"
        print(f"  generated passage (theme: {passage.get('theme', '?')})")
    else:
        print("  WARNING: passage generation failed, using empty passage")

    # 5. words.json 出力
    # アプリ側では常に 'new'（未回答）から開始させるため、ステータスをリセットする
    for w in selected:
        w["status"] = "new"

    output = {
        "meta": {
            "total": len(selected),
            "source": "target1900",
            "created": date.today().isoformat(),
            "version": current_time_ms,
        },
        "words": selected,
        "passage": passage,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))

    # 6. index.html のキャッシュバスターを更新
    if INDEX_PATH.exists():
        content = INDEX_PATH.read_text(encoding="utf-8")
        # const wordsVersion = "1773380274"; 形式を置換
        new_content = re.sub(
            r'const wordsVersion = "\d+";',
            f'const wordsVersion = "{current_time_ms}";',
            content
        )
        INDEX_PATH.write_text(new_content, encoding="utf-8")
        print(f"  updated index.html words-version → {current_time_ms}")

    print("=== Done ===")


if __name__ == "__main__":
    main()
