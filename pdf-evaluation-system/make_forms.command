#!/bin/bash
# 【Mac】名簿.csv から QRコード入り調査票PDFを作成（ダブルクリックで実行）
cd "$(dirname "$0")" || exit 1
finish() { echo; read -r -p "Enterキーを押すと閉じます" _; exit "$1"; }
[ -x .venv/bin/python ] || { echo "先に setup.command を実行してください。"; finish 1; }
.venv/bin/python -m pdfeval forms "$@" || finish 1
command -v open >/dev/null && open "調査票"
finish 0
