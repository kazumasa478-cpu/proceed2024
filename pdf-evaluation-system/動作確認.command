#!/bin/bash
# 【Mac】サンプルデータで一連の流れを試す（ダブルクリックで実行）
#   架空の4名分で：調査票作成 → 手書き風○付きの模擬スキャン作成 → 読取・採点 → 結果通知書・集計Excel
#   結果は「動作確認_結果」フォルダにでき、本番用の inbox / output には触れません。
cd "$(dirname "$0")" || exit 1
finish() { echo; read -r -p "Enterキーを押すと閉じます" _; exit "$1"; }
[ -x .venv/bin/python ] || { echo "先に setup.command を実行してください。"; finish 1; }

DEMO="動作確認_結果"
rm -rf "$DEMO"
mkdir -p "$DEMO/sample"
cp sample/名簿.csv "$DEMO/名簿.csv"
cp sample/名簿.csv "$DEMO/sample/名簿.csv"

echo "① 調査票を作成"
.venv/bin/python -m pdfeval forms --base "$DEMO" || finish 1
echo; echo "② 手書き風の○を付けた模擬スキャンPDFを作成"
.venv/bin/python - "$DEMO" <<'PY' || finish 1
import sys
from pathlib import Path
sys.path.insert(0, "sample")
import simulate_scan
simulate_scan.ROOT = Path(sys.argv[1]).resolve()
simulate_scan.main()
PY
echo; echo "③ 読取・採点・結果通知書と集計Excelを作成"
.venv/bin/python -m pdfeval run --base "$DEMO"
echo
echo "完了しました。「$DEMO/output」を開きます。"
echo "・結果通知書_印刷用_全員分.pdf … 本人に渡すA4の結果（3名分）"
echo "・ストレスチェック集計.xlsx    … 集計と円グラフ"
echo "・E0003_鈴木一郎 は、わざと「○2つ」「記入もれ」を入れてあるため「要確認」となり、通知書は作られません（正常な動作です）"
command -v open >/dev/null && open "$DEMO/output"
finish 0
