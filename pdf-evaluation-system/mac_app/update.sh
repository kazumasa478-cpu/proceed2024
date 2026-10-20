#!/bin/bash
# stresscheck_v*.zip の中に入っている更新・インストール用スクリプト。
#   bash update.sh <ダウンロードしたzipのパス>
# 「YADOLI訪問看護ステーション」フォルダの中に「ストレスチェック集計システム」フォルダを作り（あればアプリだけ更新）、
# 以前お送りした分割ファイルなどの不要なファイルをゴミ箱に入れる。
ZIP="$1"
SRC="$(cd "$(dirname "$0")" && pwd)"
FOLDER="ストレスチェック集計システム"
APP="ストレスチェック.app"
TITLE="ストレスチェック集計システム"

say() { osascript - "$1" <<'OSA' >/dev/null 2>&1
on run argv
  display dialog (item 1 of argv) with title "ストレスチェック集計システム" buttons {"OK"} default button 1
end run
OSA
}
ask2() { osascript - "$1" "$2" "$3" <<'OSA' 2>/dev/null
on run argv
  set r to display dialog (item 1 of argv) with title "ストレスチェック集計システム" buttons {item 3 of argv, item 2 of argv} default button 2
  return button returned of r
end run
OSA
}
trash() { local f; for f in "$@"; do [ -e "$f" ] && osascript -e "tell application \"Finder\" to delete POSIX file \"$f\"" >/dev/null 2>&1; done; }

# --- YADOLI訪問看護ステーション フォルダを決める ---
Y=""
zipdir="$(cd "$(dirname "$ZIP")" 2>/dev/null && pwd)"
case "$zipdir" in
  *YADOLI*) head="${zipdir%%YADOLI*}"; rest="${zipdir#"$head"}"; Y="$head${rest%%/*}" ;;
esac
if [ -z "$Y" ]; then
  Y="$(find ~/Desktop ~/Documents ~/Downloads ~/Library/CloudStorage ~/Library/Mobile\ Documents \
        -maxdepth 6 -type d -name '*YADOLI*' 2>/dev/null | head -1)"
fi
if [ -z "$Y" ]; then
  Y="$(osascript -e 'POSIX path of (choose folder with prompt "「YADOLI訪問看護ステーション」のフォルダを選んでください")' 2>/dev/null)"
  Y="${Y%/}"
fi
if [ -z "$Y" ] || [ ! -d "$Y" ]; then
  say "保存先のフォルダが決まらなかったため、中止しました。"
  exit 1
fi
echo "保存先: $Y/$FOLDER"

# --- フォルダを作ってアプリを入れる（既にあれば名簿・設定・結果は残してアプリだけ新しくする） ---
TARGET="$Y/$FOLDER"
mkdir -p "$TARGET" || { say "フォルダを作れませんでした：$TARGET"; exit 1; }
if [ -d "$TARGET/$APP" ]; then
  rm -rf "$TARGET/$APP"
  note="アプリを新しくしました（名簿・設定・結果はそのままです）。"
else
  note="フォルダを作成しました。"
fi
ditto "$SRC/$FOLDER/$APP" "$TARGET/$APP" || { say "アプリをコピーできませんでした。"; exit 1; }
cp "$SRC/$FOLDER/"*.txt "$TARGET/" 2>/dev/null
xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null
chmod +x "$TARGET/$APP/Contents/MacOS/"* 2>/dev/null

# --- 以前お送りした分割ファイル・インストーラなど、もう使わないファイルをゴミ箱へ ---
cleanup=()
for d in "$Y" "$zipdir" "$HOME/Downloads"; do
  [ -d "$d" ] || continue
  for f in "$d"/ストレスチェックMac_*.part "$d"/ストレスチェックMac_*.dat "$d"/インストーラ_Mac*.zip \
           "$d"/インストール.command "$d"/結合ツール_Mac.zip "$d"/結合_Mac.command \
           "$d"/Mac用オフライン版_*.part "$d"/pdf-evaluation-system-*.zip "$d"/ストレスチェック集計システム_Mac*.zip \
           "$d"/stresscheck_v*.zip; do
    [ -e "$f" ] && cleanup+=("$f")
  done
done
trash "${cleanup[@]}"

open -R "$TARGET/$APP"
b=$(ask2 "$note

場所：
$TARGET

この中の「ストレスチェック.app」をダブルクリックすると使えます。
（以前お送りした分割ファイル・インストーラなど ${#cleanup[@]} 個はゴミ箱に入れました）" "今すぐ開く" "閉じる")
[ "$b" = "今すぐ開く" ] && open "$TARGET/$APP"
exit 0
