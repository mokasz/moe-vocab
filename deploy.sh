#!/bin/bash
# moe-vocab を GitHub Pages にデプロイする

set -e

DEPLOY_DIR="/tmp/moe-vocab-deploy"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== moe-vocab デプロイ ==="
echo "ソース: $SOURCE_DIR"

# words.json のバージョンを index.html の meta タグに書き込む（キャッシュバスター）
VERSION=$(python3 -c "import json; d=json.load(open('$SOURCE_DIR/data/words.json')); print(d['meta'].get('version', 0))")
sed -i '' "s|<meta name=\"words-version\" content=\"[^\"]*\">|<meta name=\"words-version\" content=\"$VERSION\">|" "$SOURCE_DIR/index.html"
echo "  words-version: $VERSION"

# 音声ファイルの欠けチェック（デプロイ前に必須）
echo "  音声ファイルチェック中..."
MISSING=$(venv/bin/python -c "
import json
from pathlib import Path
base = Path('$SOURCE_DIR')
words = json.loads((base / 'data/words.json').read_text())['words']
missing = [
    f'{t}/{w[\"id\"]}.mp3'
    for w in words
    for t in ['words', 'ja', 'p4_split']
    if not (base / 'data/audio' / t / f'{w[\"id\"]}.mp3').exists()
]
print('\n'.join(missing))
" 2>/dev/null)

if [ -n "$MISSING" ]; then
  echo "❌ 音声ファイルが不足しています。デプロイを中止します。"
  echo "$MISSING" | sed 's/^/     /'
  echo "  venv/bin/python moe-vocab/scripts/generate_audio.py を実行してください。"
  exit 1
fi
echo "  音声ファイル: OK ✅"

# 変更ファイルをデプロイ用リポジトリにコピー
cp -r "$SOURCE_DIR/." "$DEPLOY_DIR/"

cd "$DEPLOY_DIR"

# 変更があるか確認
if git diff --quiet && git diff --cached --quiet; then
  echo "変更なし。デプロイ不要。"
  exit 0
fi

# コミットメッセージを引数から取得（なければ日付）
MSG="${1:-Update $(date '+%Y-%m-%d %H:%M')}"

git add .
git commit -m "$MSG"
git push

echo ""
echo "✅ デプロイ完了！"
echo "   https://mokasz.github.io/moe-vocab/"
