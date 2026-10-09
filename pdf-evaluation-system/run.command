#!/bin/bash
# 【Mac】inbox のスキャンPDFを読取 → 本人別フォルダ・結果通知書・集計Excelを作成（ダブルクリックで実行）
cd "$(dirname "$0")" || exit 1
finish() { echo; read -r -p "Enterキーを押すと閉じます" _; exit "$1"; }
[ -x .venv/bin/python ] || { echo "先に setup.command を実行してください。"; finish 1; }
.venv/bin/python -m pdfeval run "$@"
status=$?
[ $status -ne 0 ] && echo "【注意】読み取れなかったファイルがあります。logs/pdfeval.log を確認してください。"
command -v open >/dev/null && open "output"
finish $status
