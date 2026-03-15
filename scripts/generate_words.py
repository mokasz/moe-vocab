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
from datetime import date, timedelta
from pathlib import Path

# ── 設定 ────────────────────────────────────────────────
BOOK_KEY = "moe-target1900"
MOE_USER_EMAIL = "moe.zhu@icloud.com"
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
    quality: 4=正解ヒントなし, 2=正解ヒントあり, 0=不正解
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
        .select("word_key,status,ease_factor,interval_days,repetitions,last_studied")
        .eq("book_key", BOOK_KEY)
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
            w["lastSeen"] = p.get("last_studied")

    return words


# ── SM-2 単語選定 ─────────────────────────────────────────
def select_words(words: list[dict], daily_limit: int = DAILY_LIMIT) -> list[dict]:
    """
    単語選択ロジック（SPEC: docs/moe-vocab/SPEC.md「単語選択ロジック」参照）

    red ≥ 1 のとき: red → due → new（合計 daily_limit 上限）
    red = 0 のとき: due 最大 DUE_MAX 語 → new 残り枠
    """
    today = date.today().isoformat()

    red = []
    due = []
    new = []

    for w in words:
        status = w.get("status", "new")
        if status == "red":
            red.append(w)
        elif status == "green":
            last_seen = w.get("lastSeen")
            interval = w.get("interval", 1)
            if last_seen:
                next_due = (
                    date.fromisoformat(last_seen[:10]) + timedelta(days=interval)
                ).isoformat()
                if next_due <= today:
                    due.append(w)
            else:
                # lastSeen なし → 即時due扱い
                due.append(w)
        elif status == "new":
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
    args = parser.parse_args()

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
        selected = select_words(words, daily_limit=DAILY_LIMIT)
        output = {
            "meta": {
                "total": len(selected),
                "source": "target1900",
                "created": date.today().isoformat(),
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

    # 3. SM-2 単語選定
    selected = select_words(words, daily_limit=DAILY_LIMIT)
    print(f"  selected {len(selected)} words for today")

    # 4. 医学系パッセージ生成
    client = get_gemini()
    passage = generate_passage(client, selected)
    if passage:
        print(f"  generated passage (theme: {passage.get('theme', '?')})")
    else:
        print("  WARNING: passage generation failed, using empty passage")

    # 5. words.json 出力
    output = {
        "meta": {
            "total": len(selected),
            "source": "target1900",
            "created": date.today().isoformat(),
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
