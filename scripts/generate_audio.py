#!/usr/bin/env python3
"""
generate_audio.py — moe-vocab 用 Gemini TTS 音声生成

words.json の例文を Gemini TTS で MP3 化し、
data/audio/p4_split/{id}.mp3 に保存する。

使い方:
  venv/bin/python moe-vocab/scripts/generate_audio.py           # words.json の30語
  venv/bin/python moe-vocab/scripts/generate_audio.py --all-s16 # Section 16 全100語
  venv/bin/python moe-vocab/scripts/generate_audio.py --force   # 既存ファイルも上書き
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

# --- 設定 ---
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
WORDS_FILE = DATA_DIR / "words.json"
CSV_PATH = DATA_DIR / "target1900_master_enriched.csv"
SPLIT_DIR = DATA_DIR / "audio" / "p4_split"
WORDS_DIR = DATA_DIR / "audio" / "words"
JA_DIR    = DATA_DIR / "audio" / "ja"

VOICE_NAME = "Aoede"
PCM_RATE = 24000
RATE_LIMIT_SLEEP = 6.5
MAX_RETRIES = 3
PASSAGE_FILE = DATA_DIR / "audio" / "passage.mp3"

# フォールバック順: key1+Flash → key1+Pro → key2+Flash → key2+Pro
TTS_MODELS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]


def init_slots():
    """(client, model) ペアのフォールバックリストを生成。
    QUOTA超過時にこのリストを順番に試す。
    key1+Flash → key1+Pro → key2+Flash → key2+Pro の順。"""
    keys = []
    for var in ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
        key = os.environ.get(var)
        if key:
            keys.append(key)
    if not keys:
        print("ERROR: GEMINI_API_KEY が設定されていません")
        sys.exit(1)
    slots = [
        (genai.Client(api_key=k), model)
        for k in keys
        for model in TTS_MODELS
    ]
    print(f"  フォールバックスロット: {len(slots)}個 ({len(keys)}キー × {len(TTS_MODELS)}モデル)")
    return slots


def pcm_to_mp3(pcm_bytes: bytes, output_path: Path) -> bool:
    cmd = [
        "ffmpeg", "-y",
        "-f", "s16le", "-ar", str(PCM_RATE), "-ac", "1",
        "-i", "pipe:0",
        "-codec:a", "libmp3lame", "-q:a", "4",
        str(output_path),
    ]
    result = subprocess.run(cmd, input=pcm_bytes, capture_output=True)
    return result.returncode == 0


def generate_audio(slots: list, text: str, output_path: Path, force: bool = False) -> bool:
    if output_path.exists() and not force:
        print(f"  SKIP: {output_path.name}")
        return True

    slot_idx = 0  # 現在使用中の (client, model) スロット

    while slot_idx < len(slots):
        client, model = slots[slot_idx]
        slot_label = f"key{slot_idx // len(TTS_MODELS) + 1}/{model.split('-')[2]}"
        try:
            response = client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=VOICE_NAME
                            )
                        )
                    ),
                ),
            )
            content = response.candidates[0].content
            if content is None:
                print(f"  RETRY: content=None ({slot_label})")
                time.sleep(RATE_LIMIT_SLEEP)
                continue

            pcm = b""
            for part in content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    pcm += part.inline_data.data

            if not pcm:
                print(f"  RETRY: no PCM data ({slot_label})")
                time.sleep(RATE_LIMIT_SLEEP)
                continue

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if pcm_to_mp3(pcm, output_path):
                size_kb = output_path.stat().st_size // 1024
                print(f"  OK: {output_path.name} ({size_kb}KB) [{slot_label}]")
                time.sleep(RATE_LIMIT_SLEEP)
                return True
            else:
                print(f"  FAILED: ffmpeg エラー ({output_path.name})")
                return False

        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                next_idx = slot_idx + 1
                if next_idx < len(slots):
                    next_client, next_model = slots[next_idx]
                    next_label = f"key{next_idx // len(TTS_MODELS) + 1}/{next_model.split('-')[2]}"
                    print(f"  QUOTA超過 [{slot_label}] → [{next_label}] に切り替え")
                    slot_idx = next_idx
                else:
                    print(f"  QUOTA超過 [{slot_label}] → 全スロット消耗")
                    break
            else:
                print(f"  ERROR ({slot_label}): {e}")
                time.sleep(RATE_LIMIT_SLEEP * 2)

    print(f"  FAILED: {output_path.name} (全スロット消耗)")
    return False


def load_words_from_json():
    d = json.loads(WORDS_FILE.read_text())
    return [{"id": w["id"], "word": w["word"], "japanese": w["japanese"], "sentence": w["sentence"]} for w in d["words"]]


def load_section_from_csv(section: int):
    words = []
    with open(CSV_PATH) as f:
        for row in csv.DictReader(f):
            if int(row["section"]) == section:
                words.append({
                    "id": int(row["id"]),
                    "word": row["word"],
                    "japanese": row["japanese"],
                    "sentence": row["sentence"],
                })
    return words


def run_type(slots, words, audio_type, force):
    ok = skip = fail = 0
    for w in words:
        if audio_type == "words":
            out = WORDS_DIR / f"{w['id']}.mp3"
            text = f"Say the word: {w['word']}"
        elif audio_type == "ja":
            out = JA_DIR / f"{w['id']}.mp3"
            text = w["japanese"]
        else:  # sentences
            out = SPLIT_DIR / f"{w['id']}.mp3"
            text = w["sentence"]

        if not text.strip():
            print(f"  SKIP (テキストなし): {out.name}")
            skip += 1
            continue

        if generate_audio(slots, text, out, force=force):
            ok += 1
        else:
            fail += 1
    return ok, skip, fail


def generate_passage_audio(slots, force: bool = False):
    data = json.loads(WORDS_FILE.read_text())
    text = data.get("passage", {}).get("text", "").strip()
    if not text:
        print("  SKIP: passage.text が空です")
        return
    print(f"  文書 ({len(text)}文字)")
    generate_audio(slots, text, PASSAGE_FILE, force=force)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", type=int, default=None, help="対象セクション番号（例: --section 16）")
    parser.add_argument("--type", choices=["words", "ja", "sentences", "passage", "all"], default="all",
                        help="生成する音声の種類 (default: all)")
    parser.add_argument("--id", type=int, default=None, help="単語IDを指定して1語だけ再生成（例: --id 1515 --type words）")
    parser.add_argument("--force", action="store_true", help="既存ファイルも上書き")
    args = parser.parse_args()

    print("=== generate_audio.py ===")
    slots = init_slots()

    if args.type == "passage":
        print("\n--- passage ---")
        generate_passage_audio(slots, force=args.force)
        print("\n=== Done ===")
        return

    if args.section:
        words = load_section_from_csv(args.section)
        print(f"  対象: Section {args.section} ({len(words)}語)")
    else:
        words = load_words_from_json()
        print(f"  対象: words.json ({len(words)}語)")

    if args.id:
        words = [w for w in words if w["id"] == args.id]
        if not words:
            print(f"  ERROR: id={args.id} が見つかりません")
            return
        print(f"  単語指定: id={args.id} ({words[0]['word']})")
        args.force = True  # 単語指定時は常に上書き

    types = ["words", "ja", "sentences"] if args.type == "all" else [args.type]
    total_ok = total_skip = total_fail = 0

    for t in types:
        print(f"\n--- {t} ---")
        ok, skip, fail = run_type(slots, words, t, args.force)
        total_ok += ok
        total_skip += skip
        total_fail += fail

    if args.type == "all":
        print("\n--- passage ---")
        generate_passage_audio(slots, force=args.force)

    print(f"\n=== Done: OK={total_ok}, SKIP={total_skip}, FAIL={total_fail} ===")


if __name__ == "__main__":
    main()
