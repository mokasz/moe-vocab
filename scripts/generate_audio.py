#!/usr/bin/env python3
"""
generate_audio.py — moe-vocab 音声生成

エンジン分担:
  words/    → Google Cloud TTS (en-US-Studio-O)
  ja/       → Google Cloud TTS (ja-JP-Chirp3-HD-Aoede)
  p4_split/ → Gemini TTS（永続ブロック時は Google Cloud TTS にフォールバック）
  passage   → Gemini TTS（永続ブロック時は Google Cloud TTS にフォールバック）

使い方:
  venv/bin/python moe-vocab/scripts/generate_audio.py           # words.json の30語
  venv/bin/python moe-vocab/scripts/generate_audio.py --section 16  # Section 16 全語
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
from google.cloud import texttospeech

# --- 設定 ---
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
WORDS_FILE = DATA_DIR / "words.json"
CSV_PATH = DATA_DIR / "target1900_master_enriched.csv"
SPLIT_DIR = DATA_DIR / "audio" / "p4_split"
WORDS_DIR = DATA_DIR / "audio" / "words"
JA_DIR    = DATA_DIR / "audio" / "ja"
AUDIO_DIR = DATA_DIR / "audio"

# Google Cloud TTS ボイス
EN_VOICE = "en-US-Studio-O"
JA_VOICE = "ja-JP-Chirp3-HD-Aoede"

# 日本語読みオーバーライド（TTSが漢字を誤読する場合にひらがなで指定）
# key: word_id (str), value: 読み（ひらがな）
JA_READING_OVERRIDES = {
    "1561": "はいぐうしゃ",  # 配偶者 → TTSが「ぺいようしゃ」と誤読
}

# Gemini TTS 設定
GEMINI_VOICE = "Aoede"
PCM_RATE = 24000
RATE_LIMIT_SLEEP = 6.5
TTS_MODELS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]


# ── Google Cloud TTS ──────────────────────────────────────

def init_gcloud_tts():
    client = texttospeech.TextToSpeechClient()
    print("  Google Cloud TTS: 初期化完了")
    return client


def gcloud_tts(client, text: str, language_code: str, voice_name: str,
               output_path: Path, force: bool = False) -> bool:
    if output_path.exists() and not force:
        print(f"  SKIP: {output_path.name}", flush=True)
        return True

    try:
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name,
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
            ),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.audio_content)
        size_kb = output_path.stat().st_size // 1024
        print(f"  OK: {output_path.name} ({size_kb}KB) [gcloud/{voice_name}]", flush=True)
        return True
    except Exception as e:
        print(f"  FAILED (gcloud): {output_path.name} — {e}", flush=True)
        return False


# ── Gemini TTS ────────────────────────────────────────────

def init_gemini_slots():
    """(client, model) ペアのフォールバックリストを生成。"""
    keys = []
    for var in ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4"]:
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
    print(f"  Gemini TTS スロット: {len(slots)}個 ({len(keys)}キー × {len(TTS_MODELS)}モデル)")
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


def gemini_tts(slots: list, text: str, output_path: Path, force: bool = False):
    """
    Gemini TTS で音声生成。
    戻り値:
      True  — 成功
      None  — 永続ブロック（SAFETY / PROHIBITED / RECITATION）→ フォールバック推奨
      False — 一時失敗（全スロット消耗）
    """
    if output_path.exists() and not force:
        print(f"  SKIP: {output_path.name}", flush=True)
        return True

    slot_idx = 0

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
                                voice_name=GEMINI_VOICE
                            )
                        )
                    ),
                ),
            )
            cand = response.candidates[0]
            content = cand.content
            if content is None:
                reason = str(getattr(cand, "finish_reason", None))
                if any(r in reason for r in ("SAFETY", "PROHIBITED", "RECITATION")):
                    print(f"  BLOCKED: {output_path.name} ({reason}) [{slot_label}]", flush=True)
                    return None  # 永続ブロック → フォールバック
                print(f"  SKIP_SLOT: content=None finish_reason={reason} [{slot_label}]")
                slot_idx += 1
                continue

            pcm = b""
            for part in content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    pcm += part.inline_data.data

            if not pcm:
                print(f"  SKIP_SLOT: no PCM data [{slot_label}]")
                slot_idx += 1
                continue

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if pcm_to_mp3(pcm, output_path):
                size_kb = output_path.stat().st_size // 1024
                print(f"  OK: {output_path.name} ({size_kb}KB) [{slot_label}]", flush=True)
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


# ── データ読み込み ────────────────────────────────────────

def load_words_from_json():
    d = json.loads(WORDS_FILE.read_text())
    return [{"id": w["id"], "word": w["word"], "japanese": w["japanese"],
             "sentence": w["sentence"]} for w in d["words"]]


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


# ── 生成ループ ────────────────────────────────────────────

def run_type(gcloud, slots, words, audio_type, force):
    ok = skip = fail = 0
    total = len(words)

    for i, w in enumerate(words, 1):
        print(f"[{i}/{total}] {w['word']} (id={w['id']})", flush=True)

        if audio_type == "words":
            out = WORDS_DIR / f"{w['id']}.mp3"
            if gcloud_tts(gcloud, f"Say the word: {w['word']}", "en-US", EN_VOICE, out, force):
                ok += 1
            else:
                fail += 1

        elif audio_type == "ja":
            out = JA_DIR / f"{w['id']}.mp3"
            text = JA_READING_OVERRIDES.get(str(w["id"]), w["japanese"])
            if not text.strip():
                print(f"  SKIP (テキストなし): {out.name}")
                skip += 1
                continue
            if gcloud_tts(gcloud, text, "ja-JP", JA_VOICE, out, force):
                ok += 1
            else:
                fail += 1

        else:  # sentences
            out = SPLIT_DIR / f"{w['id']}.mp3"
            text = w["sentence"]
            if not text.strip():
                print(f"  SKIP (テキストなし): {out.name}")
                skip += 1
                continue
            result = gemini_tts(slots, text, out, force)
            if result is True:
                ok += 1
            elif result is None:
                # 永続ブロック → Google Cloud TTS にフォールバック
                print(f"  FALLBACK → gcloud: {out.name}", flush=True)
                if gcloud_tts(gcloud, text, "en-US", EN_VOICE, out, force=True):
                    ok += 1
                else:
                    fail += 1
            else:
                fail += 1

    return ok, skip, fail


def run_passage(gcloud, slots, force: bool = False):
    data = json.loads(WORDS_FILE.read_text())
    passage = data.get("passage", {})
    text = passage.get("text", "").strip()
    if not text:
        print("  SKIP: passage.text が空です")
        return

    audio_filename = passage.get("audio", "passage.mp3")
    out = AUDIO_DIR / audio_filename
    print(f"  文書 ({len(text)}文字) → {audio_filename}")

    result = gemini_tts(slots, text, out, force)
    if result is None:
        print(f"  FALLBACK → gcloud: {audio_filename}", flush=True)
        gcloud_tts(gcloud, text, "en-US", EN_VOICE, out, force=True)


# ── メイン ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="moe-vocab 音声生成")
    parser.add_argument("--section", type=int, default=None,
                        help="対象セクション番号（例: --section 16）")
    parser.add_argument("--type", choices=["words", "ja", "sentences", "passage", "all"],
                        default="all", help="生成する音声の種類 (default: all)")
    parser.add_argument("--id", type=int, default=None,
                        help="単語IDを指定して1語だけ再生成（例: --id 1515 --type words）")
    parser.add_argument("--force", action="store_true", help="既存ファイルも上書き")
    args = parser.parse_args()

    print("=== generate_audio.py ===")
    gcloud = init_gcloud_tts()
    slots = init_gemini_slots()

    if args.type == "passage":
        print("\n--- passage ---")
        run_passage(gcloud, slots, force=args.force)
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
        args.force = True

    run_types = ["words", "ja", "sentences"] if args.type == "all" else [args.type]
    total_ok = total_skip = total_fail = 0

    for t in run_types:
        print(f"\n--- {t} ---")
        ok, skip, fail = run_type(gcloud, slots, words, t, args.force)
        total_ok += ok
        total_skip += skip
        total_fail += fail

    if args.type == "all":
        print("\n--- passage ---")
        run_passage(gcloud, slots, force=args.force)

    print(f"\n=== Done: OK={total_ok}, SKIP={total_skip}, FAIL={total_fail} ===")


if __name__ == "__main__":
    main()
