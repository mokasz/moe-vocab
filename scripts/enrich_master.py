#!/usr/bin/env python3
"""
enrich_master.py — ターゲット1900 master CSV エンリッチスクリプト

Gemini Batch API を使用して 50% コスト削減。
inlined_requests で 1900 語を一括送信 → ポーリングで完了待ち → inlined_responses で結果取得。

使い方:
  venv/bin/python moe-vocab/scripts/enrich_master.py             # 全1900語を処理（Batch API）
  venv/bin/python moe-vocab/scripts/enrich_master.py --limit 5   # 5語のみ（テスト用）
  venv/bin/python moe-vocab/scripts/enrich_master.py --sequential # 逐次モード
  venv/bin/python moe-vocab/scripts/enrich_master.py --resume    # キャッシュから再開（逐次モード）
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

# ── 設定 ────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "moe-vocab" / "data"
INPUT_CSV = DATA_DIR / "target1900_raw.csv"
OUTPUT_CSV = DATA_DIR / "target1900_master_enriched.csv"
CACHE_FILE = DATA_DIR / ".enrich_cache.json"

MODEL = "gemini-2.5-flash"
RATE_LIMIT_SLEEP = 0.3
MAX_RETRIES = 3
POLL_INTERVAL = 30  # batch job ポーリング間隔（秒）


def derive_section_part(word_id: int) -> tuple[int, int]:
    """word_id (1-1900) → (section 1-19, part 1-3)"""
    section = (word_id - 1) // 100 + 1
    part = 1 if word_id <= 800 else 2 if word_id <= 1500 else 3
    return section, part


def parse_gemini_enrichment(raw: str) -> dict | None:
    """Strip markdown fences, parse JSON, validate keys pos/sentence/sentence_ja. Returns None if invalid."""
    text = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    try:
        data = json.loads(text)
        if all(k in data for k in ("pos", "sentence", "sentence_ja")):
            return data
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def build_prompt(word: str, japanese: str) -> str:
    return (
        f'For word "{word}" (Japanese: {japanese}): '
        f'respond ONLY with JSON: {{"pos": "<noun|verb|adjective|adverb|preposition|conjunction|pronoun|phrase>", '
        f'"sentence": "<one natural English example sentence using \'{word}\', at Japanese university entrance exam level>", '
        f'"sentence_ja": "<Japanese translation>"}}'
    )


def run_batch_api(client: genai.Client, rows: list[dict]) -> list[dict | None]:
    """Submit rows as a batch job, poll for completion, return list of enriched dicts (or None on error)."""
    print(f"Preparing {len(rows)} inlined requests for batch API...")

    inlined_requests = [
        types.InlinedRequest(
            contents=build_prompt(r["word"], r["japanese"])
        )
        for r in rows
    ]

    src = types.BatchJobSource(inlined_requests=inlined_requests)

    print(f"Submitting batch job to Gemini ({MODEL})...")
    batch_job = client.batches.create(
        model=MODEL,
        src=src,
    )
    print(f"Batch job created: {batch_job.name}")
    print(f"Initial state: {batch_job.state}")

    # Poll until done
    elapsed = 0
    while not batch_job.done:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        batch_job = client.batches.get(name=batch_job.name)
        print(f"  [{elapsed}s] State: {batch_job.state}")

    print(f"Batch job completed with state: {batch_job.state}")

    if batch_job.state.name not in ("JOB_STATE_SUCCEEDED", "SUCCEEDED"):
        print(f"[ERROR] Batch job failed: {batch_job.error}", file=sys.stderr)
        return [None] * len(rows)

    # Extract responses
    if batch_job.dest is None or batch_job.dest.inlined_responses is None:
        print("[ERROR] No inlined_responses in batch job result", file=sys.stderr)
        return [None] * len(rows)

    responses = batch_job.dest.inlined_responses
    results = []
    for i, inlined_resp in enumerate(responses):
        if inlined_resp.error is not None:
            print(f"  [WARN] Response {i} error: {inlined_resp.error}", file=sys.stderr)
            results.append(None)
            continue
        if inlined_resp.response is None:
            print(f"  [WARN] Response {i} is None", file=sys.stderr)
            results.append(None)
            continue
        raw_text = inlined_resp.response.text
        parsed = parse_gemini_enrichment(raw_text)
        if parsed is None:
            print(f"  [WARN] Failed to parse response {i} for '{rows[i]['word']}': {raw_text[:100]}", file=sys.stderr)
        results.append(parsed)

    return results


def enrich_word_sequential(client: genai.Client, word: str, japanese: str) -> dict | None:
    """Fallback: Call Gemini to enrich a single word. Retry up to MAX_RETRIES times."""
    prompt = build_prompt(word, japanese)
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt)
            result = parse_gemini_enrichment(resp.text)
            if result is not None:
                return result
            print(f"  [WARN] Invalid JSON response for '{word}' (attempt {attempt+1}): {resp.text[:100]}", file=sys.stderr)
        except Exception as e:
            print(f"  [ERROR] Gemini call failed for '{word}' (attempt {attempt+1}): {e}", file=sys.stderr)
        if attempt < MAX_RETRIES - 1:
            sleep_time = 2 ** attempt
            print(f"  Retrying in {sleep_time}s...", file=sys.stderr)
            time.sleep(sleep_time)
    return None


def load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Enrich target1900_raw.csv with Gemini Batch API")
    parser.add_argument("--limit", type=int, default=None, help="Process only N words (for testing)")
    parser.add_argument("--resume", action="store_true", help="Load cache and skip already-done words (sequential mode)")
    parser.add_argument("--sequential", action="store_true", help="Force sequential mode (no batch API)")
    args = parser.parse_args()

    # Load API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Load raw CSV
    if not INPUT_CSV.exists():
        print(f"[ERROR] Input CSV not found: {INPUT_CSV}", file=sys.stderr)
        sys.exit(1)

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} words from {INPUT_CSV}")

    # Determine words to process
    if args.limit is not None:
        rows = rows[: args.limit]
        print(f"Limiting to {args.limit} words")

    # Load cache if resuming (sequential mode)
    cache: dict = {}
    if args.resume or args.sequential:
        cache = load_cache()
        print(f"Loaded cache with {len(cache)} entries")

    results = []
    errors = 0

    use_batch = not args.resume and not args.sequential
    if use_batch:
        # ── Batch API mode ──────────────────────────────
        print(f"\nUsing Gemini Batch API (50% cost reduction)...")
        enriched_list = run_batch_api(client, rows)

        for row, enriched in zip(rows, enriched_list):
            word_id = int(row["id"])
            section, part = derive_section_part(word_id)

            if enriched is None:
                print(f"  [WARN] No result for '{row['word']}' (id={word_id})")
                errors += 1
                enriched = {"pos": "", "sentence": "", "sentence_ja": ""}

            results.append({
                "id": word_id,
                "word": row["word"],
                "pos": enriched.get("pos", ""),
                "part": part,
                "section": section,
                "japanese": row["japanese"],
                "sentence": enriched.get("sentence", ""),
                "sentence_ja": enriched.get("sentence_ja", ""),
            })
    else:
        # ── Sequential mode (with resume/cache support) ──
        total = len(rows)
        for i, row in enumerate(rows):
            word_id = int(row["id"])
            word = row["word"]
            japanese = row["japanese"]
            section, part = derive_section_part(word_id)
            cache_key = str(word_id)

            if cache_key in cache:
                enriched = cache[cache_key]
                print(f"[{i+1}/{total}] {word} (cached)")
            else:
                print(f"[{i+1}/{total}] Enriching '{word}'...", end=" ", flush=True)
                enriched = enrich_word_sequential(client, word, japanese)
                if enriched is None:
                    print(f"FAILED", file=sys.stderr)
                    errors += 1
                    enriched = {"pos": "", "sentence": "", "sentence_ja": ""}
                else:
                    print(f"OK ({enriched['pos']})")
                    cache[cache_key] = enriched
                    save_cache(cache)
                time.sleep(RATE_LIMIT_SLEEP)

            results.append({
                "id": word_id,
                "word": word,
                "pos": enriched.get("pos", ""),
                "part": part,
                "section": section,
                "japanese": japanese,
                "sentence": enriched.get("sentence", ""),
                "sentence_ja": enriched.get("sentence_ja", ""),
            })

    # Write output CSV
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["id", "word", "pos", "part", "section", "japanese", "sentence", "sentence_ja"]
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {len(results)} rows to {OUTPUT_CSV}")
    if errors:
        print(f"[WARN] {errors} words failed enrichment (empty pos/sentence fields)")

    # Delete cache on full successful sequential run
    if (args.sequential or args.resume) and args.limit is None and errors == 0:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
            print("Cache file deleted (full run completed successfully)")
    elif (args.sequential or args.resume) and args.limit is None and errors > 0:
        print(f"Cache retained due to {errors} errors. Re-run with --resume to retry.")


if __name__ == "__main__":
    main()
