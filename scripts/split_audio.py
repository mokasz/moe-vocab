#!/usr/bin/env python3
"""
split_audio.py — Whisper STT を使ってグループMP3を単語ごとに分割する

使い方:
  # Section 19 のみ（テスト）
  venv/bin/python moe-vocab/scripts/split_audio.py --section 19

  # 全セクション処理
  venv/bin/python moe-vocab/scripts/split_audio.py --all

  # 特定ファイルのみ（デバッグ）
  venv/bin/python moe-vocab/scripts/split_audio.py --file moe-vocab/data/audio/p4/TG1900_4_Sec19_1801_1817.mp3

出力:
  moe-vocab/data/audio/p4_split/{word_id}.mp3  — 単語ごとの音声
  moe-vocab/data/audio/sentences.json          — 公式例文テキスト（whisper STT）
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).parent.parent
AUDIO_P4_DIR = BASE / "data" / "audio" / "p4"
OUT_DIR = BASE / "data" / "audio" / "p4_split"
CSV_PATH = BASE / "data" / "target1900_master_enriched.csv"
SENTENCES_JSON = BASE / "data" / "audio" / "sentences.json"
WHISPER_BIN = Path("/tmp/whisper-venv/bin/whisper")

# 英語文らしいと判断する最小単語数
SENTENCE_MIN_WORDS = 5

# 単語ユニット開始をさかのぼる最大セグメント数
LOOKBACK = 4

# 単語ユニット末尾から次単語開始の padding（秒）
END_PADDING = 0.3


def is_english_sentence(text: str) -> bool:
    """5語以上の英文かどうか判定"""
    words = text.strip().split()
    if len(words) < SENTENCE_MIN_WORDS:
        return False
    # 80%以上がASCII文字なら英語とみなす
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars / max(len(text), 1) > 0.8


def is_english_word(text: str) -> bool:
    """短い英単語（1-3語）かどうか判定"""
    words = text.strip().split()
    if not (1 <= len(words) <= 3):
        return False
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars / max(len(text), 1) > 0.85


def load_csv() -> dict[int, dict]:
    """CSV から {word_id: {word, section, ...}} を返す"""
    words = {}
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wid = int(row["id"])
            words[wid] = {
                "id": wid,
                "word": row["word"].strip(),
                "section": int(row["section"]),
            }
    return words


def run_whisper(mp3_path: Path, out_dir: Path) -> dict:
    """Whisper を実行して JSON 結果を返す"""
    json_path = out_dir / (mp3_path.stem + ".json")
    if json_path.exists():
        print(f"    (cached) {json_path.name}")
        return json.loads(json_path.read_text())

    print(f"    whisper {mp3_path.name} ...", end="", flush=True)
    result = subprocess.run(
        [
            str(WHISPER_BIN),
            str(mp3_path),
            "--model", "base",
            "--output_dir", str(out_dir),
            "--output_format", "json",
            "--language", "en",   # 英語優先（日本語セグメントはそのまま通す）
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f" FAILED\n{result.stderr}")
        return {}
    print(" done")
    return json.loads(json_path.read_text())


def find_word_boundaries(segments: list[dict], n_words: int) -> list[tuple[float, float]]:
    """
    セグメントリストから n_words 個の単語区間 [(start, end), ...] を推定する。
    戦略:
      1. 英語文セグメントを anchor として特定（これが各単語ユニットの末尾）
      2. 英語文の直前 LOOKBACK セグメント以内で最後の英語単語セグメントを探し、
         それをユニット開始とする
      3. ユニット開始が見つからない場合は英語文の start - 5s を仮開始とする
    """
    # 英語文セグメントを抽出
    sentence_segs = [
        seg for seg in segments if is_english_sentence(seg["text"])
    ]

    if len(sentence_segs) != n_words:
        print(
            f"    WARNING: expected {n_words} sentences, found {len(sentence_segs)}. "
            "Trying to continue."
        )
        # 不足分は先頭 n_words 個に切り詰め
        sentence_segs = sentence_segs[:n_words]

    boundaries = []
    for i, sent_seg in enumerate(sentence_segs):
        sent_start = sent_seg["start"]
        sent_end = sent_seg["end"]

        # sent_seg より前のセグメントを LOOKBACK 個さかのぼって英単語を探す
        seg_idx = segments.index(sent_seg)
        unit_start = sent_start - 5.0  # デフォルト（fallback）

        for j in range(seg_idx - 1, max(seg_idx - LOOKBACK - 1, -1), -1):
            if is_english_word(segments[j]["text"]):
                unit_start = segments[j]["start"]
                break

        # 前の単語の end を超えないようにクランプ
        if boundaries:
            prev_end = boundaries[-1][1]
            unit_start = max(unit_start, prev_end + 0.1)

        # 次の単語の start に END_PADDING を加えた値を end として使う
        # (最後の単語は sent_end を使う)
        if i + 1 < len(sentence_segs):
            next_start = sentence_segs[i + 1]["start"]
            # 次の単語ユニット開始の少し前で切る
            unit_end = next_start - END_PADDING
        else:
            unit_end = sent_end + 0.5  # 最後の単語は少し余裕を持たせる

        unit_end = max(unit_end, sent_end)  # sentence より前で切らない
        boundaries.append((unit_start, unit_end))

    return boundaries


def extract_sentence_texts(segments: list[dict], n_words: int) -> list[str]:
    """英語文セグメントから例文テキストをリストで返す"""
    sentences = [
        seg["text"].strip()
        for seg in segments
        if is_english_sentence(seg["text"])
    ]
    return sentences[:n_words]


def split_group(mp3_path: Path, word_ids: list[int], whisper_cache: Path) -> dict[int, str]:
    """
    グループMP3を分割して per-word MP3 を出力する。
    戻り値: {word_id: sentence_text}
    """
    n = len(word_ids)
    whisper_data = run_whisper(mp3_path, whisper_cache)
    if not whisper_data:
        return {}

    segments = whisper_data.get("segments", [])
    boundaries = find_word_boundaries(segments, n)
    sentences = extract_sentence_texts(segments, n)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    for idx, wid in enumerate(word_ids):
        if idx >= len(boundaries):
            print(f"    SKIP {wid}: no boundary found")
            continue

        start, end = boundaries[idx]
        out_mp3 = OUT_DIR / f"{wid}.mp3"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(mp3_path),
            "-ss", f"{start:.3f}",
            "-to", f"{end:.3f}",
            "-c", "copy",
            str(out_mp3),
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            print(f"    ERROR ffmpeg {wid}: {r.stderr.decode()[:200]}")
        else:
            duration = end - start
            sent = sentences[idx] if idx < len(sentences) else ""
            print(f"    [{wid}] {duration:.1f}s  {sent[:60]}")
            results[wid] = sent

    return results


def parse_group_filename(mp3_path: Path) -> tuple[int, int] | None:
    """TG1900_4_SecXX_YYYY_ZZZZ.mp3 → (start_id, end_id)"""
    m = re.match(r"TG1900_4_Sec\d+_(\d+)_(\d+)\.mp3", mp3_path.name)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def get_section_files(section: int) -> list[Path]:
    return sorted(AUDIO_P4_DIR.glob(f"TG1900_4_Sec{section:02d}_*.mp3"))


def process_files(mp3_files: list[Path], all_words: dict[int, dict]) -> dict[int, str]:
    """複数のグループファイルを処理し、word_id → sentence_text を返す"""
    all_sentences = {}

    whisper_cache = Path(tempfile.mkdtemp(prefix="whisper_cache_"))
    print(f"Whisper cache: {whisper_cache}")

    for mp3 in mp3_files:
        parsed = parse_group_filename(mp3)
        if not parsed:
            print(f"SKIP (cannot parse filename): {mp3.name}")
            continue
        start_id, end_id = parsed
        word_ids = [wid for wid in range(start_id, end_id + 1) if wid in all_words]

        print(f"\n{mp3.name}  ({len(word_ids)} words: {start_id}–{end_id})")
        sentences = split_group(mp3, word_ids, whisper_cache)
        all_sentences.update(sentences)

    return all_sentences


def save_sentences(sentences: dict[int, str], existing_path: Path):
    """sentences.json に word_id → sentence_text をマージ保存する"""
    existing = {}
    if existing_path.exists():
        existing = json.loads(existing_path.read_text(encoding="utf-8"))

    existing.update({str(k): v for k, v in sentences.items()})

    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSaved {len(sentences)} sentences → {existing_path}")


def main():
    parser = argparse.ArgumentParser(description="Whisper 音声分割スクリプト")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--section", type=int, metavar="N", help="処理するセクション番号 (1-19)")
    group.add_argument("--all", action="store_true", help="全19セクションを処理")
    group.add_argument("--file", type=str, metavar="PATH", help="特定のグループMP3を処理")
    args = parser.parse_args()

    if not WHISPER_BIN.exists():
        print(f"ERROR: Whisper が見つかりません: {WHISPER_BIN}")
        sys.exit(1)

    all_words = load_csv()
    print(f"Loaded {len(all_words)} words from CSV")

    if args.file:
        mp3_files = [Path(args.file)]
    elif args.section:
        mp3_files = get_section_files(args.section)
        if not mp3_files:
            print(f"ERROR: Section {args.section} のファイルが見つかりません")
            sys.exit(1)
    else:  # --all
        mp3_files = sorted(AUDIO_P4_DIR.glob("TG1900_4_Sec*.mp3"))

    print(f"Processing {len(mp3_files)} files → {OUT_DIR}")

    sentences = process_files(mp3_files, all_words)
    save_sentences(sentences, SENTENCES_JSON)

    print(f"\n=== Done: {len(sentences)} words split ===")
    print(f"Per-word MP3s: {OUT_DIR}/{{id}}.mp3")


if __name__ == "__main__":
    main()
