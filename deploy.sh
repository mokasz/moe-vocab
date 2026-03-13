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
