#!/bin/bash
# 初回セットアップ (macOS / Linux): .venv を作成しライブラリをインストール
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
"$PY" -m venv .venv
if [ -d wheels ]; then
  .venv/bin/python -m pip install --no-index --find-links wheels -r requirements.txt
else
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi
mkdir -p inbox
[ -f 名簿.csv ] || cp sample/名簿.csv 名簿.csv
echo "セットアップ完了。名簿.csv を編集し、./run.sh forms で調査票を作成してください。"
