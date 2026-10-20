#!/bin/bash
# ストレスチェック.app の本体。ダブルクリックでメニューを表示する。
#   ・プログラム         … アプリの中 (Contents/Resources)
#   ・Python とライブラリ … ~/Library/Application Support/ストレスチェック集計システム/venv-…
#   ・名簿・設定・入出力 … アプリと同じフォルダ
# 名簿の編集・要確認の修正はアプリの中でできるので、Excel や Numbers がなくても使える。
APP_NAME="ストレスチェック集計システム"
CONTENTS="$(cd "$(dirname "$0")/.." && pwd)"
APP="$(dirname "$CONTENTS")"
RES="$CONTENTS/Resources"
BASE="$(dirname "$APP")"
SUPPORT="$HOME/Library/Application Support/$APP_NAME"
LOG="$BASE/logs/app.log"
export PYTHONPATH="$RES"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
# ライブラリの組み合わせが同じなら、版が変わっても同じ仮想環境を使い回す
REQ_ID="$(shasum -a 256 "$RES/requirements.txt" 2>/dev/null | cut -c1-12)"
VENV="$SUPPORT/venv-$REQ_ID"
CHECK_IMPORT="import cv2, numpy, PIL, pypdfium2, pypdf, reportlab, openpyxl"

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

ask_text() {  # ask_text "質問" "初期値" → 入力された文字（キャンセル時は空で終了コード1）
  osascript - "$1" "$2" <<'OSA' 2>/dev/null
on run argv
  set r to display dialog (item 1 of argv) with title "ストレスチェック集計システム" default answer (item 2 of argv) buttons {"キャンセル", "OK"} default button 2 cancel button 1
  return text returned of r
end run
OSA
}

choose() {  # choose "説明" "OKボタン名" 項目... → 選んだ項目（やめたら空）
  local prompt="$1" ok="$2"; shift 2
  osascript - "$prompt" "$ok" "$@" <<'OSA' 2>/dev/null
on run argv
  set theItems to items 3 thru -1 of argv
  set r to choose from list theItems with title "ストレスチェック集計システム" with prompt (item 1 of argv) OK button name (item 2 of argv) cancel button name "戻る"
  if r is false then return ""
  return item 1 of r
end run
OSA
}

notify() { osascript -e "display notification \"$1\" with title \"$APP_NAME\"" >/dev/null 2>&1; }

finder_open() {  # Finder に開いてもらう（Finder は「書類」フォルダを開く許可を必ず持っている）
  osascript - "$1" <<'OSA' >/dev/null 2>&1
on run argv
  tell application "Finder"
    open (POSIX file (item 1 of argv) as alias)
    activate
  end tell
end run
OSA
}

open_path() {  # ファイルやフォルダを開く。3通り試し、だめなら理由と開き方を表示する
  local f="$1" err
  [ -e "$f" ] || case "$f" in */inbox|*/output|*/調査票) mkdir -p "$f" 2>/dev/null ;; esac
  err=$(/usr/bin/open "$f" 2>&1) && return 0
  /usr/bin/open -a Finder "$f" >/dev/null 2>&1 && return 0
  finder_open "$f" && return 0
  echo "open failed: $f : $err" >>"$LOG" 2>/dev/null
  printf %s "$f" | pbcopy 2>/dev/null
  dialog "開けませんでした：
$f

理由：${err:-不明}

【手で開く方法】この場所をコピーしてあります。
Finder のメニュー「移動」→「フォルダへ移動…」を選び、⌘V で貼り付けて Enter を押してください。" >/dev/null
  return 1
}

import_scans() {  # ファイル選択画面でスキャンを選び、inbox にコピーする。取り込んだ件数を返す（echo）
  local list n=0 f
  list=$(osascript <<'OSA' 2>/dev/null
set fs to choose file with prompt "取り込むスキャン（PDF・JPEG・PNG・TIFF）を選んでください。⌘キーを押しながらクリックすると複数選べます。" of type {"com.adobe.pdf", "public.jpeg", "public.png", "public.tiff"} with multiple selections allowed
set out to ""
repeat with f in fs
  set out to out & POSIX path of f & linefeed
end repeat
return out
OSA
)
  mkdir -p "$BASE/inbox"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if cp "$f" "$BASE/inbox/" 2>>"$LOG"; then n=$((n + 1)); else echo "copy failed: $f" >>"$LOG"; fi
  done <<< "$list"
  echo "$n"
}

# --- 置き場所のチェック ---
case "$APP" in
  */AppTranslocation/*)
    dialog "このアプリは一時的な場所で起動されました。

「$APP_NAME」フォルダを Finder でドラッグして別の場所（YADOLI訪問看護ステーション のフォルダなど）へ移動してから、もう一度ダブルクリックしてください。" >/dev/null
    exit 0 ;;
esac
# 「書類」「デスクトップ」「Googleドライブ」などは、アプリごとに macOS の許可が必要
if ! err=$(ls "$BASE" 2>&1 >/dev/null); then
  case "$err" in *"not permitted"*|*"許可"*|*"Permission denied"*)
    b=$(dialog "このアプリに、次のフォルダを使う許可がありません。
$BASE

【許可のしかた】
1. 下の「設定を開く」を押す（「フルディスクアクセス」の画面と、このアプリの場所が開きます）
2. 一覧の下の「＋」を押し、「ストレスチェック.app」を選んで「開く」
　（または、開いた Finder から「ストレスチェック.app」を一覧へドラッグ）
3. 「ストレスチェック」のスイッチをオンにする（Macのパスワードを聞かれたら入力）
4. このアプリをもう一度ダブルクリックする" "設定を開く" "終了")
    if [ "$b" = "設定を開く" ]; then
      open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
      osascript -e "tell application \"Finder\" to reveal (POSIX file \"$APP\" as alias)" -e 'tell application "Finder" to activate' >/dev/null 2>&1
    fi
    exit 0 ;;
  esac
fi
if [ ! -w "$BASE" ]; then
  dialog "このフォルダには書き込みできません：
$BASE

書き込みできる場所へ移動してから開いてください。" >/dev/null
  exit 1
fi
xattr -dr com.apple.quarantine "$BASE" 2>/dev/null
mkdir -p "$BASE/logs"

# --- Python とライブラリの準備 ---
find_python() {
  for cand in python3.13 python3.12 python3; do
    for dir in /Library/Frameworks/Python.framework/Versions/Current/bin /opt/homebrew/bin /usr/local/bin /usr/bin; do
      exe="$dir/$cand"
      [ -x "$exe" ] || continue
      if "$exe" -c 'import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 13) else 1)' >/dev/null 2>&1; then
        echo "$exe"; return 0
      fi
    done
  done
  return 1
}

reuse_existing_venv() {  # 以前の版で作ったライブラリがそのまま使えるなら使う
  local v
  for v in "$SUPPORT"/venv-*; do
    [ -x "$v/bin/python" ] || continue
    if "$v/bin/python" -c "$CHECK_IMPORT" >/dev/null 2>&1; then
      VENV="$v"; return 0
    fi
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
  VENV="$SUPPORT/venv-$REQ_ID"
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
  if ! "$VENV/bin/python" -c "$CHECK_IMPORT" >>"$LOG" 2>&1; then
    rm -rf "$VENV"
    dialog "準備に失敗しました。インターネット接続を確認して、もう一度開いてください。
直らない場合は logs/app.log を担当者に送ってください。" >/dev/null
    exit 1
  fi
}
if ! "$VENV/bin/python" -c "$CHECK_IMPORT" >/dev/null 2>&1; then
  reuse_existing_venv || setup
fi
PY="$VENV/bin/python"

pdfeval() { "$PY" -m pdfeval "$@" --config "$BASE/config.json" --base "$BASE"; }

# 名簿・設定がなければ見本をコピー。名簿は文字化けしない形式で保存し直しておく
[ -f "$BASE/config.json" ] || cp "$RES/config.json" "$BASE/config.json"
[ -f "$BASE/名簿.csv" ] || cp "$RES/sample/名簿.csv" "$BASE/名簿.csv"
pdfeval roster-fixfile >>"$LOG" 2>&1
mkdir -p "$BASE/inbox"

run_pdfeval() {  # run_pdfeval 説明 引数...（結果の要点を SUMMARY に入れる）
  local title="$1"; shift
  notify "$title を実行しています…"
  local out status
  out=$(pdfeval "$@" 2>&1)
  status=$?
  echo "$out" >>"$LOG"
  SUMMARY=$(echo "$out" | sed -E 's/^[0-9-]+ [0-9:,]+ \[(INFO|WARNING|ERROR)\] //' |
            grep -E '集計:|印刷用:|未作成|未提出|読み取れません|見つかりません|ありません|名簿|調査票を作成|名分|重複|問題' | tail -8)
  return $status
}

# --- 名簿 ---
roster_menu() {
  while true; do
    local c
    c=$(choose "名簿（$(pdfeval roster-list 2>/dev/null | grep -c .)名）" "OK" \
        "名簿を見る" "名簿に追加する" "名簿から外す" "名簿ファイルを開く（Excel・Numbers など）")
    case "$c" in
      "名簿を見る")
        local list
        list=$(pdfeval roster-list 2>&1 | awk -F'\t' '{printf "%s　%s　%s\n", $1, $2, $3}')
        dialog "${list:-（まだ誰も登録されていません）}" >/dev/null ;;
      "名簿に追加する")
        local id name dept msg
        id=$(ask_text "ID（社員番号など。英数字）を入力してください" "") || continue
        name=$(ask_text "氏名を入力してください" "") || continue
        dept=$(ask_text "所属を入力してください（空欄でも可）" "") || continue
        msg=$(pdfeval roster-add --id "$id" --name "$name" --dept "$dept" 2>>"$LOG")
        dialog "$msg" >/dev/null ;;
      "名簿から外す")
        local items=() line pick
        while IFS= read -r line; do [ -n "$line" ] && items+=("$(echo "$line" | tr '\t' ' ')"); done \
          < <(pdfeval roster-list 2>/dev/null)
        [ ${#items[@]} -gt 0 ] || { dialog "名簿に誰もいません。" >/dev/null; continue; }
        pick=$(choose "名簿から外す人を選んでください" "外す" "${items[@]}")
        [ -n "$pick" ] || continue
        [ "$(dialog "「$pick」を名簿から外しますか？" "外す" "やめる")" = "外す" ] || continue
        dialog "$(pdfeval roster-remove --id "${pick%% *}" 2>>"$LOG")" >/dev/null ;;
      "名簿ファイルを開く（Excel・Numbers など）")
        dialog "名簿.csv を開きます。
・1行目は「ID,氏名,所属」のままにしてください
・Numbers で直した場合は「ファイル」→「書き出す」→「CSV」で、同じ名前（名簿.csv）に上書きしてください" >/dev/null
        open_path "$BASE/名簿.csv" ;;
      *) return ;;
    esac
  done
}

# --- 要確認の人：アプリの中で回答を確定する ---
fix_person() {  # fix_person ID 表示名 スキャンファイル(|区切り)
  local pid="$1" label="$2" files="$3" f
  IFS='|' read -r -a scans <<< "$files"
  for f in "${scans[@]}"; do [[ "$f" == *.pdf ]] && open_path "$f"; done
  local lines
  lines=$(pdfeval items --id "$pid" 2>>"$LOG")
  [ -n "$lines" ] || return 0
  local item q st sc opts
  while IFS=$'\t' read -r item q st sc opts; do
    [ -n "$item" ] || continue
    IFS='|' read -r -a o <<< "$opts"
    local reason="$st"
    [ "$st" = "複数" ] && reason="2つ以上塗られているように見えます"
    [ "$st" = "未記入" ] && reason="どれも塗られていないように見えます"
    [ "$st" = "要確認" ] && reason="塗りが薄く、自信がありません"
    local pick
    pick=$(choose "$label　$item
「$q」

読み取り結果：$reason
開いたスキャン（調査票スキャン_○枚目.pdf）を見て、本人が塗った番号を選んでください。" "確定" \
      "1：${o[0]}" "2：${o[1]}" "3：${o[2]}" "4：${o[3]}" "未回答（本人が答えていない）" < /dev/null)
    [ -n "$pick" ] || return 1          # 「戻る」＝続きはあとで
    local ans="${pick%%：*}"
    [[ "$ans" =~ ^[1-4]$ ]] || ans="none"
    pdfeval fix --id "$pid" --item "$item" --answer "$ans" >>"$LOG" 2>&1
  done <<< "$lines"
  return 0
}

todo() {
  while true; do
    local lines labels=() files=() kinds=() ids=()
    lines=$(pdfeval todo --tsv 2>>"$LOG")
    while IFS=$'\t' read -r kind paths label; do
      [ -n "$kind" ] || continue
      kinds+=("$kind"); files+=("$paths"); labels+=("$label"); ids+=("${label%% *}")
    done <<< "$lines"
    if [ ${#labels[@]} -eq 0 ]; then
      dialog "要確認の人はいません。全員の結果通知書を作成できる状態です。" >/dev/null
      return
    fi
    local picked i
    picked=$(choose "読み取りに自信がない回答が残っている人です。選ぶと、スキャンを見ながら1問ずつ確定できます。" "確認する" "${labels[@]}")
    [ -n "$picked" ] || return
    for i in "${!labels[@]}"; do
      [ "${labels[$i]}" = "$picked" ] || continue
      if [ "${kinds[$i]}" = "UNREADABLE" ]; then
        open_path "${files[$i]}"
        dialog "このページは読み取れませんでした。
・このアプリで作った調査票か（四隅の黒い四角とQRコードがあるか）
・用紙の端やQRコードが欠けたり汚れたりしていないか
を確認し、スキャンし直して inbox に入れてください。" >/dev/null
        continue 2
      fi
      if fix_person "${ids[$i]}" "${labels[$i]%%（*}" "${files[$i]}"; then
        run_pdfeval "集計" run
        dialog "${labels[$i]%%（*} さんの確認が終わり、集計し直しました。

$SUMMARY" >/dev/null
      fi
    done
  done
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
  open_path "$d/output"
  dialog "動作確認が完了しました（架空の4名分）。

・結果通知書_印刷用_全員分.pdf … 本人に渡すA4の結果
・ストレスチェック集計.xlsx … 集計と円グラフ
・鈴木一郎さんは、わざと「2つ塗った」「記入もれ」を入れてあるため「要確認」となり、通知書は作られません（正常な動作です）。

結果は「動作確認_結果」フォルダにあり、本番のデータには影響しません。" >/dev/null
}

# --- メニュー ---
M_RUN="スキャンしたPDFを読み取って集計する"
M_IMPORT="スキャンを選んで取り込み、読み取る"
M_TODO="要確認の人を確認・修正する"
M_FORMS="名簿から調査票（印刷用PDF）を作る"
M_ROSTER="名簿を見る・追加する"
M_DEMO="動作確認（サンプルで試す）"
M_CONFIG="設定を開く（実施者名・連絡先など）"
M_INBOX="inbox フォルダを開く"
M_OUTPUT="結果フォルダ（output）を開く"
while true; do
  choice=$(osascript - "$M_IMPORT" "$M_RUN" "$M_TODO" "$M_FORMS" "$M_ROSTER" "$M_DEMO" "$M_CONFIG" "$M_INBOX" "$M_OUTPUT" <<'OSA' 2>/dev/null
on run argv
  set r to choose from list argv with title "ストレスチェック集計システム" with prompt "行う作業を選んで「OK」を押してください。" OK button name "OK" cancel button name "終了" default items {item 1 of argv}
  if r is false then return ""
  return item 1 of r
end run
OSA
)
  [ "$choice" = "$M_IMPORT" ] && {
    n=$(import_scans)
    [ "${n:-0}" -gt 0 ] || { dialog "ファイルが取り込まれませんでした。" >/dev/null; continue; }
    choice="$M_RUN"
  }
  case "$choice" in
    "$M_RUN")
      status_text=$(pdfeval inbox 2>>"$LOG")
      st=$?
      if [ $st -eq 3 ]; then
        b=$(dialog "このアプリに、フォルダの中を見る許可がありません。

$status_text

「システム設定」→「プライバシーとセキュリティ」→「ファイルとフォルダ」で「ストレスチェック」の項目をオンにしてください。
見つからない場合は「フルディスクアクセス」に「ストレスチェック.app」を追加してオンにしてください。" "設定を開く" "戻る")
        [ "$b" = "設定を開く" ] && open "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders"
        continue
      fi
      if [ $st -ne 0 ]; then
        if [ -d "$BASE/output" ]; then
          b=$(dialog "inbox に新しいスキャンはありません。
新しいスキャンを取り込むか、これまでの回答で集計だけやり直せます。" "ファイルを選ぶ" "集計だけやり直す" "戻る")
        else
          b=$(dialog "inbox にスキャンがありません。
取り込むスキャン（PDF・JPEG・PNG・TIFF）を選んでください。" "ファイルを選ぶ" "戻る")
        fi
        [ "$b" = "戻る" ] || [ -z "$b" ] && continue
      fi
      if [ $st -ne 0 ] && [ "$b" = "ファイルを選ぶ" ]; then
        n=$(import_scans)
        if [ "${n:-0}" -eq 0 ]; then
          dialog "ファイルが取り込まれませんでした。" >/dev/null
          continue
        fi
      fi
      run_pdfeval "読み取り・集計" run
      st=$?
      open_path "$BASE/output"
      [ $st -eq 0 ] && head="完了しました。" || head="一部のファイルを読み取れませんでした（output/_読取不可 を確認してください）。"
      dialog "$head

$SUMMARY

要確認の人がいる場合は、メニューの「要確認の人を確認・修正する」で直せます。" >/dev/null ;;
    "$M_TODO") todo ;;
    "$M_FORMS")
      if run_pdfeval "調査票の作成" forms; then
        open_path "$BASE/調査票"
        dialog "調査票を作成しました。

$SUMMARY

等倍・片面で印刷してください（「用紙に合わせる」はオフ）。" >/dev/null
      else
        dialog "調査票を作成できませんでした。

$SUMMARY

メニューの「名簿を見る・追加する」で名簿を確認してください。" >/dev/null
      fi ;;
    "$M_ROSTER") roster_menu ;;
    "$M_DEMO") demo ;;
    "$M_CONFIG") open -e "$BASE/config.json" 2>>"$LOG" || open_path "$BASE/config.json" ;;
    "$M_INBOX") open_path "$BASE/inbox" ;;
    "$M_OUTPUT") mkdir -p "$BASE/output"; open_path "$BASE/output" ;;
    *) exit 0 ;;
  esac
done
