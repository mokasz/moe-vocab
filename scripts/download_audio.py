#!/usr/bin/env python3
"""
download_audio.py — 旺文社公式音声ダウンロード

認証はクライアントサイドJSのみ（サーバー認証不要）。ZIPは直接GETで取得可能。

各ZIPには100語分の音声が6ファイル（セクション単位）に分割されて格納されている。
例: 1900_1_1-100/TG1900_1_Sec01_0001_0014.mp3

使い方:
  venv/bin/python moe-vocab/scripts/download_audio.py --patterns 1 4
  venv/bin/python moe-vocab/scripts/download_audio.py --patterns 1 4 --dry-run
  venv/bin/python moe-vocab/scripts/download_audio.py --patterns 1 --range 1-100
  venv/bin/python moe-vocab/scripts/download_audio.py --index-only
"""

import argparse
import io
import json
import re
import time
import zipfile
from pathlib import Path

import requests

# ── 設定 ────────────────────────────────────────────────
BASE_URL = 'https://service.obunsha.co.jp/tokuten/target/target1900_6'
# 認証はクライアントサイドJSのみ。サーバーへのログインPOST不要。
# dload{n}.html にアクセスすれば直接ZIPをダウンロードできる。

RANGES = [f'{i}-{i+99}' for i in range(1, 1901, 100)]  # ['1-100', '101-200', ..., '1801-1900']
OUTPUT_BASE = Path('moe-vocab/data/audio')


def build_zip_url(pattern: int, range_str: str) -> str:
    """ZIPファイルのURLを構築する。"""
    return f'{BASE_URL}/dl/1900_{pattern}_{range_str}.zip'


def already_downloaded(pattern: int, range_str: str) -> bool:
    """指定レンジのMP3が既に出力ディレクトリに存在するか確認する。"""
    out_dir = OUTPUT_BASE / f'p{pattern}'
    if not out_dir.exists():
        return False
    # レンジ文字列からファイル名パターンを確認
    # 例: 1-100 → TG1900_1_Sec01_*.mp3 のような名前のファイルが存在するか
    # ZIPの中身はレンジごとにサブディレクトリ (1900_{p}_{range}/) に入っているが、
    # 展開後はフラットに p{pattern}/ へ置く。
    # チェック方法: レンジの開始番号からセクション番号を推定
    start = int(range_str.split('-')[0])
    sec_num = (start - 1) // 100 + 1
    sec_str = f'Sec{sec_num:02d}'
    existing = list(out_dir.glob(f'TG1900_{pattern}_{sec_str}_*.mp3'))
    return len(existing) > 0


def download_zip(session: requests.Session, pattern: int, range_str: str, dry_run: bool) -> bytes | None:
    """ZIPファイルをダウンロードしてバイト列で返す。失敗時はNoneを返す。"""
    url = build_zip_url(pattern, range_str)
    if dry_run:
        print(f'  [DRY-RUN] GET {url}')
        return None

    try:
        r = session.get(url, timeout=60)
        if r.status_code == 200:
            return r.content
        else:
            print(f'  [ERROR] HTTP {r.status_code}: {url}')
            return None
    except requests.RequestException as e:
        print(f'  [ERROR] {e}: {url}')
        return None


def extract_mp3s(zip_bytes: bytes, pattern: int, dry_run: bool) -> int:
    """ZIPからMP3ファイルを抽出して出力ディレクトリに保存する。保存したファイル数を返す。"""
    out_dir = OUTPUT_BASE / f'p{pattern}'
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for name in z.namelist():
            if not name.lower().endswith('.mp3'):
                continue
            # サブディレクトリを除いてフラットに保存
            filename = Path(name).name
            dest = out_dir / filename
            if dry_run:
                print(f'  [DRY-RUN] Extract → {dest}')
            else:
                dest.write_bytes(z.read(name))
            count += 1
    return count


def generate_index(output_base: Path) -> None:
    """抽出済みMP3ファイルからaudio_index.jsonを生成する。"""
    index: dict[str, dict[str, str]] = {'p1': {}, 'p4': {}}
    for pattern_key in ['p1', 'p4']:
        pattern_dir = output_base / pattern_key
        if not pattern_dir.exists():
            continue
        for mp3_file in sorted(pattern_dir.glob('*.mp3')):
            m = re.match(r'TG1900_(\d+)_Sec\d+_(\d+)_(\d+)\.mp3', mp3_file.name)
            if not m:
                continue
            start_id = int(m.group(2))
            end_id = int(m.group(3))
            rel_path = f'{pattern_key}/{mp3_file.name}'
            for word_id in range(start_id, end_id + 1):
                index[pattern_key][str(word_id)] = rel_path
    index_path = output_base / 'audio_index.json'
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))
    total_entries = sum(len(v) for v in index.values())
    print(f'  wrote {index_path} ({total_entries} entries)')


def main() -> None:
    parser = argparse.ArgumentParser(description='旺文社ターゲット1900 音声ダウンロード')
    parser.add_argument(
        '--patterns', nargs='+', type=int, choices=[1, 2, 3, 4], default=[1, 4],
        help='ダウンロードするパターン番号 (1=見出し語のみ, 4=見出し語+意味+例文)',
    )
    parser.add_argument(
        '--range', dest='only_range', default=None,
        help='特定レンジのみダウンロード (例: 1-100)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='URLを表示するのみ、実際のダウンロードは行わない',
    )
    parser.add_argument(
        '--index-only', action='store_true',
        help='ダウンロードをスキップして、既存ファイルからインデックスのみ生成する',
    )
    args = parser.parse_args()

    if args.index_only:
        print('インデックス生成中...')
        generate_index(OUTPUT_BASE)
        print('\n完了。')
        return

    ranges = [args.only_range] if args.only_range else RANGES

    # 総ダウンロード数を計算
    total = len(args.patterns) * len(ranges)
    idx = 0

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': f'{BASE_URL}/dload1.html',
    })

    for pattern in args.patterns:
        for range_str in ranges:
            idx += 1
            label = f'[{idx}/{total}] Pattern {pattern}, {range_str}'

            if not args.dry_run and already_downloaded(pattern, range_str):
                print(f'{label} — スキップ (既存)')
                continue

            print(f'{label} — ダウンロード中...')
            zip_bytes = download_zip(session, pattern, range_str, dry_run=args.dry_run)

            if zip_bytes is not None:
                n = extract_mp3s(zip_bytes, pattern, dry_run=args.dry_run)
                print(f'  → {n} MP3ファイルを保存')

            if not args.dry_run and idx < total:
                time.sleep(0.5)

    if not args.dry_run:
        print('\nインデックス生成中...')
        generate_index(OUTPUT_BASE)

    print('\n完了。')


if __name__ == '__main__':
    main()
