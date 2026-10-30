#!/bin/bash
# ストレスチェック.app の本体。ダブルクリックでメニューを表示する。
#   ・プログラムとライブラリ … アプリの中 (Contents/Resources)
#   ・Python 仮想環境       … ~/Library/Application Support/ストレスチェック集計システム
#   ・名簿・設定・入出力    … アプリと同じフォルダ（BtoB フォルダなどに置いた場所）
APP_NAME="ストレスチェック集計システム"
CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
APP="$(dirname "$CONTENTS")"
RES="$CONTENTS/Resources"
BASE="$(dirname "$APP")"
VERSION="$(cat "$RES/VERSION" 2>/dev/null || echo 1)"
SUPPORT="$HOME/Library/Application Support/$APP_NAME"
VENV="$SUPPORT/venv-$VERSION"
LOG="$BASE/logs/app.log"
export PYTHONPATH="$RES"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

dialog() {  # dialog "本文" [ボタン...]  → 押したボタン名を返す
  local text="$1"; shift
  local buttons="\"OK\""
  [ $# -gt 0 ] && buttons=$(printf '"%s",' "$@") && buttons="${buttons%,}"
  osascript - "$text" <<OSA 2>/dev/null
on run argv
  set r to display dialog (item 1 of argv) with title "$APP_NAME" buttons {$buttons} default button 1
  return button returned of r
end run
OSA
}

notify() { osascript -e "display notification \"$1\" with title \"$APP_NAME\"" >/dev/null 2>&1; }

ask_text() {  # ask_text "質問" "初期値" → 入力された文字（キャンセル時は終了コード1）
  osascript - "$1" "$2" <<'OSA' 2>/dev/null
on run argv
  set r to display dialog (item 1 of argv) with title "ストレスチェック集計システム" default answer (item 2 of argv) buttons {"キャンセル", "保存"} default button 2 cancel button 1
  return text returned of r
end run
OSA
}

choose() {  # choose "説明" 項目... → 選んだ項目（「戻る」なら空）
  local prompt="$1"; shift
  osascript - "$prompt" "$@" <<'OSA' 2>/dev/null
on run argv
  set r to choose from list (items 2 thru -1 of argv) with title "ストレスチェック集計システム" with prompt (item 1 of argv) OK button name "選ぶ" cancel button name "戻る"
  if r is false then return ""
  return item 1 of r
end run
OSA
}

# --- 置き場所のチェック（ダウンロードしたまま開くと、macOSが一時的な場所で起動することがある） ---
case "$APP" in
  */AppTranslocation/*)
    dialog "このアプリは一時的な場所で起動されました。

「$APP_NAME」フォルダを Finder でドラッグして BtoB フォルダなどへ移動してから、もう一度ダブルクリックしてください。"
    exit 0 ;;
esac
if [ ! -w "$BASE" ]; then
  dialog "このフォルダには書き込みできません：
$BASE

書き込みできる場所（BtoB フォルダなど）へ移動してから開いてください。"
  exit 1
fi
# ネットから来たファイルの実行ブロックをフォルダごと解除（2回目以降の確認を出さないため）
xattr -dr com.apple.quarantine "$BASE" 2>/dev/null
mkdir -p "$BASE/logs"

# --- 初回準備：Python を探して仮想環境を作り、同梱ライブラリを入れる ---
find_python() {
  for cand in python3.13 python3.12 python3; do
    for dir in /Library/Frameworks/Python.framework/Versions/Current/bin /opt/homebrew/bin /usr/local/bin /usr/bin; do
      exe="$dir/$cand"
      [ -x "$exe" ] || continue
      # /usr/bin/python3 はコマンドラインツール未導入だと案内画面が出るだけなので確認してから使う
      if "$exe" -c 'import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 13) else 1)' >/dev/null 2>&1; then
        echo "$exe"; return 0
      fi
    done
  done
  return 1
}

setup() {
  local py
  if ! py="$(find_python)"; then
    local b
    b=$(dialog "Python（3.12 または 3.13）が見つかりません。

python.org から「macOS 64-bit universal2 installer」をダウンロードしてインストールし、もう一度このアプリを開いてください。" "ダウンロードページを開く" "閉じる")
    [ "$b" = "ダウンロードページを開く" ] && open "https://www.python.org/downloads/macos/"
    exit 1
  fi
  if [ -d "$RES/wheels" ]; then
    notify "初回の準備をしています（1〜2分かかります）"
    src=(--no-index --find-links "$RES/wheels")
  else
    dialog "初回の準備として、必要な部品をインターネットから取り込みます（数分かかります）。
インターネットにつながった状態で「OK」を押してください。" >/dev/null
    notify "必要な部品を取り込んでいます…"
    src=()
  fi
  {
    echo "=== setup $(date) with $py"
    rm -rf "$VENV"
    mkdir -p "$SUPPORT"
    "$py" -m venv "$VENV" &&
    "$VENV/bin/python" -m pip install --disable-pip-version-check "${src[@]}" -r "$RES/requirements.txt"
  } >>"$LOG" 2>&1
  if ! "$VENV/bin/python" -c "import cv2, reportlab, openpyxl, pypdfium2" >>"$LOG" 2>&1; then
    rm -rf "$VENV"
    dialog "初回の準備に失敗しました。
logs/app.log の内容を担当者に送ってください。"
    exit 1
  fi
}
reuse_existing_venv() {  # 以前の版で入れた部品がそのまま使えるなら使う（更新時に部品を送らなくて済む）
  local v
  for v in "$SUPPORT"/venv-*; do
    [ -x "$v/bin/python" ] || continue
    if "$v/bin/python" -c "import cv2, numpy, PIL, pypdfium2, pypdf, reportlab, openpyxl" >/dev/null 2>&1; then
      VENV="$v"; return 0
    fi
  done
  return 1
}
if ! "$VENV/bin/python" -c "import cv2, reportlab, openpyxl, pypdfium2" >/dev/null 2>&1; then
  reuse_existing_venv || setup
fi
PY="$VENV/bin/python"

# 名簿・設定がなければ見本をコピー
[ -f "$BASE/config.json" ] || cp "$RES/config.json" "$BASE/config.json"
[ -f "$BASE/名簿.csv" ] || cp "$RES/sample/名簿.csv" "$BASE/名簿.csv"
mkdir -p "$BASE/inbox"

run_pdfeval() {  # run_pdfeval 説明 引数...
  local title="$1"; shift
  notify "$title を実行しています…"
  local out status
  out=$("$PY" -m pdfeval "$@" --config "$BASE/config.json" --base "$BASE" 2>&1)
  status=$?
  echo "$out" >>"$LOG"
  SUMMARY=$(echo "$out" | sed -E 's/^[0-9-]+ [0-9:,]+ \[(INFO|WARNING|ERROR)\] //' | grep -E '集計:|印刷用:|未作成|未提出|読み取れません|見つかりません|ありません|名簿|調査票を作成|名分|重複' | tail -8)
  return $status
}

demo() {
  local d="$BASE/動作確認_結果"
  rm -rf "$d"; mkdir -p "$d/sample"
  cp "$RES/sample/名簿.csv" "$d/名簿.csv"; cp "$RES/sample/名簿.csv" "$d/sample/名簿.csv"
  cp "$BASE/config.json" "$d/config.json"
  notify "サンプルで動作確認をしています…"
  {
    "$PY" -m pdfeval forms --config "$d/config.json" --base "$d" &&
    "$PY" - "$d" "$RES/sample" <<'PY' &&
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
import simulate_scan
simulate_scan.ROOT = Path(sys.argv[1]).resolve()
simulate_scan.main()
PY
    "$PY" -m pdfeval run --config "$d/config.json" --base "$d"
  } >>"$LOG" 2>&1
  open "$d/output"
  dialog "動作確認が完了しました（架空の4名分）。

・結果通知書_印刷用_全員分.pdf … 本人に渡すA4の結果
・ストレスチェック集計.xlsx … 集計と円グラフ
・集団分析結果_A4.pdf … 集団分析（A4・1枚。この見本は4名のため注意書きが出ます）
・鈴木一郎さんは、わざと「2つ塗った」「記入もれ」を入れてあるため「要確認」となり、通知書は作られません（正常な動作です）。

結果は「動作確認_結果」フォルダにあり、本番のデータには影響しません。" >/dev/null
}

# --- 設定（相談先など）をアプリの画面で変更する ---
settings_menu() {
  local P_PREVIEW="▶ 結果通知書の見本を見る（今の設定で作成）"
  local P_FILE="▶ 設定ファイルを直接開く（上級者向け）"
  while true; do
    local keys=() labels=() currents=() hints=() items=() k l c h
    while IFS=$'\x1f' read -r k l c h; do
      [ -n "$k" ] || continue
      keys+=("$k"); labels+=("$l"); currents+=("$c"); hints+=("$h")
      items+=("$l：${c:-（未設定）}")
    done < <("$PY" -m pdfeval settings-list --config "$BASE/config.json" --base "$BASE" 2>>"$LOG")
    local pick
    pick=$(choose "変更したい項目を選んでください。結果通知書に載る内容です。" "${items[@]}" "$P_PREVIEW" "$P_FILE")
    case "$pick" in
      "") return ;;
      "$P_PREVIEW")
        local out
        out=$("$PY" -m pdfeval preview-report --config "$BASE/config.json" --base "$BASE" 2>>"$LOG" | tail -1)
        [ -f "$out" ] && open "$out" || dialog "見本を作れませんでした。logs/app.log を確認してください。" >/dev/null ;;
      "$P_FILE") open -e "$BASE/config.json" ;;
      *)
        local i
        for i in "${!items[@]}"; do
          [ "${items[$i]}" = "$pick" ] || continue
          local new msg
          new=$(ask_text "「${labels[$i]}」を入力してください。
${hints[$i]}" "${currents[$i]}") || break
          msg=$("$PY" -m pdfeval settings-set --key "${keys[$i]}" --value "$new" --config "$BASE/config.json" --base "$BASE" 2>>"$LOG")
          dialog "$msg

これから作る結果通知書に反映されます。
すでに作った結果通知書を作り直すには、メニューの「スキャンしたPDFを読み取って集計する」をもう一度実行してください。" >/dev/null
          break
        done ;;
    esac
  done
}

# --- メニュー ---
M_RUN="スキャンしたPDFを読み取って集計する"
M_GROUP="集団分析（A4・1枚）を作る"
M_FORMS="名簿から調査票（印刷用PDF）を作る"
M_DEMO="動作確認（サンプルで試す）"
M_ROSTER="名簿を開く（名簿.csv）"
M_CONFIG="設定を変更する（相談先・連絡先など）"
M_INBOX="スキャンPDFの置き場所（inbox）を開く"
M_OUTPUT="結果フォルダ（output）を開く"
while true; do
  choice=$(osascript - "$M_RUN" "$M_GROUP" "$M_FORMS" "$M_DEMO" "$M_ROSTER" "$M_CONFIG" "$M_INBOX" "$M_OUTPUT" <<'OSA' 2>/dev/null
on run argv
  set r to choose from list argv with title "ストレスチェック集計システム" with prompt "行う作業を選んで「OK」を押してください。" OK button name "OK" cancel button name "終了" default items {item 1 of argv}
  if r is false then return ""
  return item 1 of r
end run
OSA
)
  case "$choice" in
    "$M_RUN")
      if ! ls "$BASE/inbox/"*.[pP][dD][fF] >/dev/null 2>&1 && [ ! -d "$BASE/output" ]; then
        b=$(dialog "inbox フォルダにスキャンしたPDFがありません。
PDFを inbox に入れてから実行してください。" "inboxを開く" "戻る")
        [ "$b" = "inboxを開く" ] && open "$BASE/inbox"
        continue
      fi
      run_pdfeval "読み取り・集計" run
      st=$?
      open "$BASE/output"
      [ $st -eq 0 ] && head="完了しました。" || head="一部のファイルを読み取れませんでした（output/_読取不可 を確認してください）。"
      dialog "$head

$SUMMARY

黄色の「要確認」がある人は、本人フォルダの 回答確認.xlsx を直して「状態」を「確認済」にし、もう一度この作業を行ってください。" >/dev/null ;;
    "$M_FORMS")
      if run_pdfeval "調査票の作成" forms; then
        open "$BASE/調査票"
        dialog "調査票を作成しました。

$SUMMARY

等倍・片面で印刷してください（「用紙に合わせる」はオフ）。" >/dev/null
      else
        dialog "調査票を作成できませんでした。名簿.csv（列：ID,氏名,所属）を確認してください。

$SUMMARY" >/dev/null
      fi ;;
    "$M_GROUP")
      if [ ! -d "$BASE/output" ]; then
        dialog "まだ集計した結果がありません。
先に「スキャンしたPDFを読み取って集計する」を行ってください。" >/dev/null
        continue
      fi
      run_pdfeval "集団分析" run   # 最新の回答で集計し直してから作る
      if [ -f "$BASE/output/集団分析結果_A4.pdf" ]; then
        open "$BASE/output/集団分析結果_A4.pdf"
        dialog "集団分析（A4・1枚）を作成しました。
output フォルダの「集団分析結果_A4.pdf」です。

・結果が確定した人（要確認が残っていない人）だけで集計しています
・10名未満の所属は、個人が特定されないよう数値を表示していません" >/dev/null
      else
        dialog "集団分析を作成できませんでした。logs/app.log を確認してください。" >/dev/null
      fi ;;
    "$M_DEMO") demo ;;
    "$M_ROSTER") open "$BASE/名簿.csv" ;;
    "$M_CONFIG") settings_menu ;;
    "$M_INBOX") open "$BASE/inbox" ;;
    "$M_OUTPUT") mkdir -p "$BASE/output"; open "$BASE/output" ;;
    *) exit 0 ;;
  esac
done
