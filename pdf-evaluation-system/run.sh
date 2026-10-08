#!/bin/bash
# 実行: inbox/*.pdf → output/<氏名>/ と output/評価集計.xlsx
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "先に ./setup.sh を実行してください"; exit 1; }
.venv/bin/python -m pdfeval "$@"
