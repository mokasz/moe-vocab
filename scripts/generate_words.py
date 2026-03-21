#!/usr/bin/env python3
"""
generate_words.py — SM-2 単語選定 + 医学系パッセージ生成

使い方:
  venv/bin/python moe-vocab/scripts/generate_words.py           # 通常実行
  venv/bin/python moe-vocab/scripts/generate_words.py --dry-run # Supabase/Gemini スキップ
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

# ── 設定 ────────────────────────────────────────────────
BOOK_KEY = "moe-target1900"
MOE_USER_EMAIL = "moeloveslemon1921@gmail.com"
MOE_USER_ID = "a29d41be-9ee3-4890-9c03-cff3f7339c21"
DAILY_LIMIT = 30
DUE_MAX = 15       # red=0 時の due（復習）上限枚数

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


# ── SM-2 ─────────────────────────────────────────────────
def sm2_update(ease: float, interval: int, repetitions: int, quality: int):
    """
    SM-2 アルゴリズム（インライン実装）。
    quality: 4=正解（知ってた）, 0=不正解（知らなかった）
    moe-vocab はヒント機能なし。quality は 0 / 4 の2値のみ使用する。
    returns: (ease, interval, repetitions)
    """
    if quality < 2:  # 不正解 → リセット
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


def quality_from_review_log(ratings: list[int]) -> int:
    """
    当日の review_log の rating リストから SM-2 quality を決定する。
    rating: green=4, red=1（moe-vocab は yellow なし）

    前提: ratings は空でないこと（呼び出し元で確認する）。
    review_log に記録がない単語は SM-2 計算対象外とし、この関数を呼ばない。
    """
    if 1 in ratings:
        return 0
    return 4


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
            })
    return words


# ── Supabase 進捗マージ ────────────────────────────────────
def load_progress(sb, words: list[dict]) -> list[dict]:
    """Load Supabase progress_sync records and merge onto words."""
    rows = (
        sb.table("progress_sync")
        .select("word_key,status,ease_factor,interval_days,repetitions,last_studied,next_review")
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

    return words


# ── SM-2 更新 + progress_sync 書き戻し ─────────────────────
def update_sm2_and_save(sb, words: list[dict], target_date: str) -> None:
    """
    回答済み単語の SM-2 を再計算し、progress_sync を更新する。
    next_review > last_studied の単語はスキップ（重複適用防止）。

    quality は review_log から導出し、w["quality"] に書き戻す。
    select_words() はこの値を使って red バケットを決定する
    （progress_sync.status はブラウザが保存するため信頼性が低い）。
    """
    today = target_date

    # 対象絞り込み（kaya-vocab と同じパターン）
    # status は参照しない: new（lastSeen=null）のみ除外すれば十分
    targets = [
        w for w in words
        if w.get("lastSeen")                        # 未回答はスキップ
        and w.get("lastSeen", "")[:10] < today      # 今日の回答は翌朝に処理
        and (                                        # SM-2 未反映のみ
            w.get("nextReview") is None
            or w.get("nextReview") <= w.get("lastSeen", "")[:10]
        )
    ]

    if not targets:
        print("  no SM-2 updates needed")
        return

    # review_log を一括取得（対象単語の last_studied 日付分）
    word_keys = [str(w["id"]) for w in targets]
    log_rows = (
        sb.table("review_log")
        .select("word_key, rating, reviewed_at")
        .eq("user_id", MOE_USER_ID)
        .eq("book_key", BOOK_KEY)
        .in_("word_key", word_keys)
        .execute()
        .data
    )
    log_map: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for log in log_rows:
        d = log["reviewed_at"][:10]
        log_map[log["word_key"]][d].append(log["rating"])

    for w in targets:
        ratings = log_map[str(w["id"])].get(w["lastSeen"][:10], [])
        if not ratings:
            # review_log 記録なし → SM-2 計算対象外（スキップ）
            # 学習した事実がない or データ欠損の場合は計算しない
            continue
        quality = quality_from_review_log(ratings)
        ease, interval, repetitions = sm2_update(
            w["ease"], w["interval"], w["repetitions"], quality
        )
        next_review = (date.fromisoformat(w["lastSeen"][:10]) + timedelta(days=interval)).isoformat()
        sb.table("progress_sync").update({
            "ease_factor":   ease,
            "interval_days": interval,
            "repetitions":   repetitions,
            "next_review":   next_review,
        }).eq("book_key", BOOK_KEY).eq("user_id", MOE_USER_ID).eq("word_key", str(w["id"])).execute()
        w["interval"]   = interval
        w["nextReview"] = next_review
        w["quality"]    = quality   # select_words() で red バケット判定に使用

    print(f"  updated SM-2 for {len(targets)} words")


# ── SM-2 単語選定 ─────────────────────────────────────────
def select_words(words: list[dict], target_date: str, daily_limit: int = DAILY_LIMIT) -> list[dict]:
    """
    単語選択ロジック（SPEC: docs/moe-vocab/SPEC.md「単語選択ロジック」参照）

    red ≥ 1 のとき: red → due → new（合計 daily_limit 上限）
    red = 0 のとき: due 最大 DUE_MAX 語 → new 残り枠

    red の判定: progress_sync.status ではなく w["quality"] == 0 を使う。
    quality は update_sm2_and_save() が review_log から導出して書き戻す。
    ブラウザが保存する status は UI 表示用であり、選定ロジックでは参照しない。
    """
    today = target_date

    red = []
    due = []
    new = []

    for w in words:
        # review_log 由来の quality=0 → red（前回不正解）
        if w.get("quality") == 0:
            red.append(w)
        elif w.get("lastSeen"):
            # 回答済み（green/red 問わず）: lastSeen + interval で due 判定
            interval = w.get("interval", 1)
            next_due = (
                date.fromisoformat(w["lastSeen"][:10]) + timedelta(days=interval)
            ).isoformat()
            if next_due <= today:
                due.append(w)
        else:
            # lastSeen なし → 未出題（new）
            new.append(w)

    # new は part 降順 → section 昇順 → id 昇順（Part3-sec16→17→18→19→Part2-sec9…）
    new.sort(key=lambda w: (-w.get("part", 0), w.get("section", 0), w.get("id", 0)))

    selected = []

    if red:
        # red ≥ 1: 現行仕様（red → due → new、合計 daily_limit 上限）
        remaining = daily_limit
        for bucket in (red, due, new):
            take = bucket[:remaining]
            selected.extend(take)
            remaining -= len(take)
            if remaining <= 0:
                break
    else:
        # red = 0: due は最大 DUE_MAX 語、残り枠を new で補充
        due_take = due[:DUE_MAX]
        selected.extend(due_take)
        remaining = daily_limit - len(due_take)
        selected.extend(new[:remaining])

    return selected


# ── パッセージ生成 ────────────────────────────────────────
def generate_passage(client, words: list[dict]) -> dict:
    """Generate a ~200-word medical reading passage containing today's words.
    Returns: {"text": "...", "theme": "...", "highlighted_words": [...]}
    """
    theme = random.choice(MEDICAL_THEMES)
    # 最大15語をパッセージに含める
    passage_words = [w["word"] for w in words[:15]]
    word_list = ", ".join(passage_words)

    prompt = (
        f"Write a ~200-word academic passage on {theme} at Japanese medical school"
        " entrance exam level.\n"
        f"Incorporate these words naturally: {word_list}.\n"
        "The passage should read like an excerpt from a science journal or textbook.\n\n"
        "Output ONLY a JSON object (no markdown, no explanation):\n"
        "{\n"
        '  "text": "<the full ~200-word passage in English>",\n'
        '  "text_ja": "<natural Japanese translation of the passage>",\n'
        f'  "theme": "{theme}",\n'
        '  "highlighted_words": ["word1", "word2"]\n'
        "}\n\n"
        "highlighted_words must be the exact words from the list that appear in the passage."
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = response.text.strip()
        text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        result = json.loads(text)
        # Gemini sometimes wraps highlighted words in **bold** — strip those
        if "text" in result:
            result["text"] = re.sub(r"\*\*(.+?)\*\*", r"\1", result["text"])
        return result
    except Exception as e:
        print(f"  WARNING: passage generation failed: {e}")
    return {}


# ── Supabase クライアント ──────────────────────────────────
def get_supabase():
    from supabase import create_client
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )


def get_gemini():
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY が環境変数に設定されていません")
        sys.exit(1)
    return genai.Client(api_key=api_key)


# ── メイン ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="moe-vocab SM-2 単語生成スクリプト")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Supabase / Gemini をスキップ。CSVから選定した最初の500文字を表示。",
    )
    parser.add_argument(
        "--section",
        type=int,
        default=None,
        help="このセクション番号の単語のみを対象にする（例: --section 16）",
    )
    parser.add_argument(
        "--date",
        dest="target_date",
        default=None,
        help="生成対象日 YYYY-MM-DD（省略時は今日）",
    )
    args = parser.parse_args()

    target_date = args.target_date if args.target_date else date.today().isoformat()

    print("=== generate_words.py ===")

    # 1. CSV 読み込み
    words = load_master_csv()
    print(f"  loaded {len(words)} words from CSV")

    # セクションフィルタ
    if args.section is not None:
        words = [w for w in words if w["section"] == args.section]
        print(f"  filtered to section {args.section}: {len(words)} words")

    if args.dry_run:
        # Supabase / Gemini スキップ
        selected = select_words(words, target_date, daily_limit=DAILY_LIMIT)
        output = {
            "meta": {
                "total": len(selected),
                "source": "target1900",
                "created": target_date,
                "version": int(time.time()),
            },
            "words": selected,
            "passage": {},
        }
        text = json.dumps(output, ensure_ascii=False, indent=2)
        print(f"  [dry-run] selected {len(selected)} words")
        print(f"  [dry-run] first word IDs: {[w['id'] for w in selected[:5]]}")
        print(text[:500])
        return

    # 2. Supabase 進捗マージ
    sb = get_supabase()
    words = load_progress(sb, words)
    print("  merged Supabase progress")

    # 3. SM-2 再計算 + progress_sync 書き戻し
    update_sm2_and_save(sb, words, target_date)

    # 4. 単語選定
    selected = select_words(words, target_date, daily_limit=DAILY_LIMIT)
    print(f"  selected {len(selected)} words for today")

    # 5. 医学系パッセージ生成
    client = get_gemini()
    passage = generate_passage(client, selected)
    if passage:
        passage["audio"] = f"passage_{target_date}.mp3"
        print(f"  generated passage (theme: {passage.get('theme', '?')})")
    else:
        print("  WARNING: passage generation failed, using empty passage")

    # 6. words.json 出力
    # status を 'new' にリセット（アプリは "全語 new で即座に表示" が前提。
    # Supabase から取得した進捗値をそのまま書くと起動時に全問完了扱いになるため）
    for w in selected:
        w["status"] = "new"

    output = {
        "meta": {
            "total": len(selected),
            "source": "target1900",
            "created": target_date,
            "version": int(time.time()),
        },
        "words": selected,
        "passage": passage,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"  wrote {OUTPUT_PATH} ({len(selected)} words)")

    # index.html の words-version meta タグを更新（キャッシュバスター）
    version = output["meta"]["version"]
    html = INDEX_PATH.read_text()
    html = re.sub(
        r'<meta name="words-version" content="[^"]*">',
        f'<meta name="words-version" content="{version}">',
        html,
    )
    INDEX_PATH.write_text(html)
    print(f"  updated index.html words-version → {version}")

    print("=== Done ===")


if __name__ == "__main__":
    main()
