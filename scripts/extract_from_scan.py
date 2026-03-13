#!/usr/bin/env python3
"""
extract_from_scan.py — スキャンPDFからTarget 1900データを抽出・検証する

Claude Code CLI を使用（Gemini/Anthropic API キー不要）

使い方:
  # 単一PDFを処理
  venv/bin/python moe-vocab/scripts/extract_from_scan.py --pdf moe-vocab/data/target1900_scan_sample.pdf

  # ディレクトリ内の全PDFを処理
  venv/bin/python moe-vocab/scripts/extract_from_scan.py --dir moe-vocab/data/scans/

  # 抽出のみ（検証スキップ）
  venv/bin/python moe-vocab/scripts/extract_from_scan.py --pdf scan.pdf --no-verify

  # CSVに上書きマージ
  venv/bin/python moe-vocab/scripts/extract_from_scan.py --pdf scan.pdf --update-csv

出力:
  moe-vocab/data/scan_extracted.json     — 抽出データ（全エントリ）
  moe-vocab/data/scan_verify_report.json — 検証レポート
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).parent.parent
CSV_PATH = BASE / "data" / "target1900_master_enriched.csv"
OUTPUT_JSON = BASE / "data" / "scan_extracted.json"
VERIFY_REPORT = BASE / "data" / "scan_verify_report.json"

VERIFY_BATCH_SIZE = 20

EXTRACT_PROMPT_TEMPLATE = """Read the image at {image_path}

This is a scanned page from 英単語ターゲット1900 (Target 1900), a Japanese English vocabulary book.

Extract all main headword entries from this image. Each entry has:
- A 4-digit ID number shown below the word (e.g. □□ 1501)
- An English headword (bold, left column)
- A Japanese meaning (red/colored text, after the headword in the left column)
- An English example sentence (center column, headword appears bold/colored in the sentence)
- A Japanese translation of the example sentence (rightmost column)

Return ONLY a valid JSON array with no other text:
[
  {{
    "id": 1501,
    "word": "bless",
    "japanese": "に恩恵を与える；に感謝する",
    "sentence": "This area is blessed with natural beauty.",
    "sentence_ja": "この地域は自然美に恵まれている。"
  }}
]

Rules:
- Only include entries with a visible 4-digit ID (□□ NNNN format)
- Do NOT include derived words (e.g. blessing, blessed) — only the main headword
- If a page has no entries with IDs, return []
- Use the exact text from the scan"""

VERIFY_PROMPT_TEMPLATE = """You are verifying vocabulary data from ターゲット1900, a Japanese English vocabulary book.

For each entry below, verify that:
1. The Japanese meaning correctly translates the English word
2. The English sentence contains a form of the English word

Return ONLY a valid JSON array in the same order as the input:
[
  {{
    "id": <id>,
    "ok": true,
    "reason": ""
  }}
]

Set ok=false and provide a reason only if the meaning is clearly wrong or unrelated.
Allow partial matches, nuanced translations, and inflected forms in sentences.

Entries to verify:
{entries}"""


def run_claude(prompt: str, allow_tools: bool = False) -> str:
    """Claude Code CLI を非インタラクティブモードで実行し、レスポンステキストを返す"""
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if allow_tools:
        cmd += ["--allowedTools", "Read"]
    else:
        cmd += ["--tools", ""]  # ツール不要（テキスト分析のみ）

    # CLAUDECODE 環境変数を除去してネスト実行制限を回避
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr[:300]}")

    # --output-format json は {"result": "...", "cost_usd": ...} 形式で返す
    try:
        outer = json.loads(result.stdout)
        return outer.get("result", result.stdout)
    except json.JSONDecodeError:
        return result.stdout


def extract_json(text: str) -> list | dict:
    """レスポンステキストからJSONを抽出する（余分なテキスト付きでも対応）"""
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    # 最初の [ か { の位置を探す
    start = next((i for i, c in enumerate(text) if c in "[{"), 0)
    # 対応する閉じ括弧の位置を探す（JSONデコーダが正確な範囲を検出）
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text, start)
    return obj


def pdf_to_images(pdf_path: Path, dpi: int = 150) -> list[Path]:
    """PDF を JPEG 画像のリストに変換する（pdftoppm使用）"""
    tmp_dir = Path(tempfile.mkdtemp(prefix="scan_extract_"))
    out_prefix = str(tmp_dir / "page")

    result = subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-jpeg", str(pdf_path), out_prefix],
        capture_output=True, text=True,
    )
    if result.returncode != 0 and "Syntax Error" not in result.stderr:
        print(f"  pdftoppm warning: {result.stderr[:200]}")

    images = sorted(tmp_dir.glob("page-*.jpg"))
    return images


def extract_entries_from_image(img_path: Path) -> list[dict]:
    """Claude Code CLI で1枚の画像からエントリを抽出する"""
    prompt = EXTRACT_PROMPT_TEMPLATE.format(image_path=str(img_path))
    try:
        response = run_claude(prompt, allow_tools=True)
        entries = extract_json(response)
        if not isinstance(entries, list):
            return []
        valid = []
        for e in entries:
            if all(k in e for k in ("id", "word", "japanese", "sentence", "sentence_ja")):
                e["id"] = int(e["id"])
                valid.append(e)
        return valid
    except Exception as ex:
        print(f"    WARNING: extraction failed for {img_path.name}: {ex}")
        return []


def extract_from_pdf(pdf_path: Path, dpi: int = 150) -> list[dict]:
    """PDF全ページを処理してエントリリストを返す"""
    print(f"\n{'='*60}")
    print(f"PDF: {pdf_path.name}")
    print(f"{'='*60}")

    print("  Converting pages to images...")
    images = pdf_to_images(pdf_path, dpi=dpi)
    print(f"  {len(images)} pages found")

    all_entries = []
    for img in images:
        entries = extract_entries_from_image(img)
        ids = [e["id"] for e in entries]
        status = "✅" if entries else "⬜"
        print(f"    {status} {img.name}: {len(entries)} entries  {ids}")
        all_entries.extend(entries)

    # 重複除去（同じIDが複数ページに出る場合は最初を優先）
    seen: set[int] = set()
    unique = []
    for e in all_entries:
        if e["id"] not in seen:
            seen.add(e["id"])
            unique.append(e)

    unique.sort(key=lambda x: x["id"])
    print(f"\n  Unique entries: {len(unique)}")
    if unique:
        print(f"  ID range: {unique[0]['id']} – {unique[-1]['id']}")

    return unique


def verify_entries(entries: list[dict]) -> dict:
    """
    抽出エントリの整合性を検証する。

    Step 1: ルールベース — sentenceにwordが含まれているか
    Step 2: Claude Code CLI — 英日意味の整合性チェック（バッチ）
    """
    print(f"\n{'='*60}")
    print(f"Verification ({len(entries)} entries)")
    print(f"{'='*60}")

    issues = []

    # --- Step 1: ルールベース ---
    print("\n[Step 1] Rule-based: word appears in sentence...")
    rule_ok = 0
    for e in entries:
        stem = e["word"].lower()[:max(3, len(e["word"]) - 3)]
        if stem not in e["sentence"].lower():
            issues.append({
                "id": e["id"],
                "word": e["word"],
                "issue_type": "word_not_in_sentence",
                "detail": f"'{e['word']}' (stem '{stem}') not in: {e['sentence'][:80]}",
            })
            print(f"    ❌ [{e['id']}] {e['word']}: not found in sentence")
        else:
            rule_ok += 1
    print(f"    Passed: {rule_ok}/{len(entries)}")

    # --- Step 2: Claude Code CLI バッチ検証 ---
    print(f"\n[Step 2] Semantic: EN/JP meaning alignment (batches of {VERIFY_BATCH_SIZE})...")
    meaning_ok = 0
    meaning_fail = 0

    for i in range(0, len(entries), VERIFY_BATCH_SIZE):
        batch = entries[i : i + VERIFY_BATCH_SIZE]
        batch_text = "\n".join(
            f'{j+1}. id={e["id"]}, word="{e["word"]}", japanese="{e["japanese"]}"'
            for j, e in enumerate(batch)
        )
        prompt = VERIFY_PROMPT_TEMPLATE.format(entries=batch_text)

        try:
            response = run_claude(prompt, allow_tools=False)
            results = extract_json(response)
            if not isinstance(results, list):
                raise ValueError("expected list")

            for r in results:
                if not r.get("ok", True):
                    meaning_fail += 1
                    entry = next((e for e in batch if e["id"] == r.get("id")), None)
                    word = entry["word"] if entry else "?"
                    issues.append({
                        "id": r.get("id"),
                        "word": word,
                        "issue_type": "meaning_mismatch",
                        "detail": r.get("reason", ""),
                    })
                    print(f"    ❌ [{r.get('id')}] {word}: {r.get('reason', '')}")
                else:
                    meaning_ok += 1

            print(f"    Batch {i // VERIFY_BATCH_SIZE + 1}: {meaning_ok} ok, {meaning_fail} fail so far")

        except Exception as ex:
            print(f"    WARNING: batch {i // VERIFY_BATCH_SIZE + 1} failed: {ex}")

    # --- サマリー ---
    total = len(entries)
    issue_ids = set(x["id"] for x in issues)
    clean = total - len(issue_ids)
    accuracy = 100 * clean / total if total > 0 else 0

    print(f"\n{'='*60}")
    print("Verification Summary")
    print(f"{'='*60}")
    print(f"  Total:             {total}")
    print(f"  ✅ Clean:          {clean}")
    print(f"  ❌ Meaning issues: {len([x for x in issues if x['issue_type'] == 'meaning_mismatch'])}")
    print(f"  ⚠️  Word not found: {len([x for x in issues if x['issue_type'] == 'word_not_in_sentence'])}")
    print(f"  Accuracy:          {accuracy:.1f}%")

    return {
        "total": total,
        "clean": clean,
        "accuracy_pct": round(accuracy, 1),
        "issues": issues,
    }


def update_csv(entries: list[dict]):
    """CSVのsentence/sentence_ja/japaneseを抽出データで更新する"""
    if not CSV_PATH.exists():
        print(f"  WARNING: CSV not found at {CSV_PATH}")
        return

    entry_map = {e["id"]: e for e in entries}
    rows = []
    updated = 0

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            wid = int(row["id"])
            if wid in entry_map:
                sc = entry_map[wid]
                row["japanese"] = sc["japanese"]
                row["sentence"] = sc["sentence"]
                row["sentence_ja"] = sc["sentence_ja"]
                updated += 1
            rows.append(row)

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Updated {updated} entries in {CSV_PATH.name}")


def load_existing() -> dict[int, dict]:
    if OUTPUT_JSON.exists():
        data = json.loads(OUTPUT_JSON.read_text(encoding="utf-8"))
        return {e["id"]: e for e in data}
    return {}


def main():
    parser = argparse.ArgumentParser(
        description="スキャンPDFからTarget 1900データを抽出・検証 (Claude Code CLI使用)"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=str, help="処理するPDFファイルパス")
    source.add_argument("--dir", type=str, help="PDFが入ったディレクトリ")
    parser.add_argument("--no-verify", action="store_true", help="検証をスキップ")
    parser.add_argument("--update-csv", action="store_true", help="CSVをスキャンデータで更新")
    parser.add_argument("--dpi", type=int, default=150, help="PDF→画像DPI (default: 150)")
    args = parser.parse_args()

    # pdftoppm の存在確認
    if subprocess.run(["which", "pdftoppm"], capture_output=True).returncode != 0:
        print("ERROR: pdftoppm が見つかりません。brew install poppler でインストールしてください。")
        sys.exit(1)

    # 処理対象PDF
    if args.pdf:
        pdfs = [Path(args.pdf)]
    else:
        pdfs = sorted(Path(args.dir).glob("*.pdf"))
        if not pdfs:
            print(f"ERROR: PDFが見つかりません: {args.dir}")
            sys.exit(1)

    existing = load_existing()
    print(f"Existing entries: {len(existing)}")

    # 抽出
    new_entries: list[dict] = []
    for pdf in pdfs:
        new_entries.extend(extract_from_pdf(pdf, dpi=args.dpi))

    # マージ・保存
    merged = {**existing, **{e["id"]: e for e in new_entries}}
    all_entries = sorted(merged.values(), key=lambda x: x["id"])
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(all_entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(all_entries)} entries → {OUTPUT_JSON}")

    # 検証
    if not args.no_verify and new_entries:
        report = verify_entries(new_entries)
        VERIFY_REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Saved verification report → {VERIFY_REPORT}")
        print(f"\n=== Result: {report['accuracy_pct']}% accuracy ({report['clean']}/{report['total']} clean) ===")
        if report["issues"]:
            print(f"Issues: see {VERIFY_REPORT}")
    else:
        print("\n=== Done ===")

    # CSV更新
    if args.update_csv:
        print("\nUpdating CSV...")
        update_csv(all_entries)


if __name__ == "__main__":
    main()
