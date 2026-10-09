#!/bin/bash
# 【Mac】初回セットアップ（ダブルクリックで実行）
cd "$(dirname "$0")" || exit 1
finish() { echo; read -r -p "Enterキーを押すと閉じます" _; exit "$1"; }

# オフライン版（wheels 同梱）は Python 3.12 / 3.13 用のライブラリのみ入っている
if [ -d wheels ]; then
  CANDS="python3.13 python3.12 python3"; CHECK='(3, 12) <= sys.version_info[:2] <= (3, 13)'
else
  CANDS="python3.13 python3.12 python3.11 python3.10 python3"; CHECK='sys.version_info >= (3, 10)'
fi
PY=""
for cand in $CANDS; do
  for dir in /Library/Frameworks/Python.framework/Versions/Current/bin /opt/homebrew/bin /usr/local/bin ""; do
    exe="${dir:+$dir/}$cand"
    if command -v "$exe" >/dev/null 2>&1 && "$exe" -c "import sys; sys.exit(0 if $CHECK else 1)" 2>/dev/null; then
      PY="$exe"; break 2
    fi
  done
done
if [ -z "$PY" ]; then
  echo "【エラー】使える Python が見つかりません（Python 3.12 または 3.13 が必要です）。"
  echo "https://www.python.org/downloads/macos/ から macOS 64-bit universal2 installer を入れてから、もう一度実行してください。"
  finish 1
fi
echo "使用するPython: $PY ($("$PY" --version))"

[ -d .venv ] || "$PY" -m venv .venv || finish 1
if [ -d wheels ]; then
  .venv/bin/python -m pip install --no-index --find-links wheels -r requirements.txt || finish 1
else
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt || finish 1
fi
mkdir -p inbox
[ -f 名簿.csv ] || cp sample/名簿.csv 名簿.csv
echo
echo "セットアップ完了。"
echo "・すぐに試す場合 → 「動作確認.command」をダブルクリック"
echo "・本番 → 名簿.csv を編集し「make_forms.command」で調査票を作成"
finish 0
