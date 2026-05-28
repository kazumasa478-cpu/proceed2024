#!/bin/bash

export PATH="/opt/homebrew/bin:/usr/local/bin:/opt/node22/bin:/usr/bin:/bin:$PATH"

cd "$(dirname "$0")"

INDEX_FILE="./index.txt"
KEYWORDS_FILE="./keywords.txt"

# キーワード一覧を配列に読み込む（macOS bash互換）
keywords=()
while IFS= read -r line || [ -n "$line" ]; do
  [ -n "$line" ] && keywords+=("$line")
done < "$KEYWORDS_FILE"

total=${#keywords[@]}

# 今日のインデックスを読み込む（なければ0）
if [ -f "$INDEX_FILE" ]; then
  index=$(cat "$INDEX_FILE")
else
  index=0
fi

# キーワードを全て使い切ったらリセット
if [ "$index" -ge "$total" ]; then
  index=0
fi

keyword="${keywords[$index]}"

echo "$(date '+%Y-%m-%d %H:%M:%S') - 投稿開始: $keyword"

node post.js "$keyword"

# 次のインデックスを保存
echo $((index + 1)) > "$INDEX_FILE"

echo "$(date '+%Y-%m-%d %H:%M:%S') - 完了"
