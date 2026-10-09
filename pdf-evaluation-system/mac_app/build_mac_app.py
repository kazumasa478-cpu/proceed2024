"""Mac用アプリ（ストレスチェック.app）入りの配布パッケージを作る。

    python mac_app/build_mac_app.py

dist/mac/ に次ができる:
  ストレスチェック集計システム_Mac.zip   … 本体（フォルダごと）
  ストレスチェックMac_v<版>_00.part …    … 上のzipを25MBずつに分割したもの（送付用）
  インストーラ_Mac_v<版>.zip             … 分割ファイルを結合・展開する「インストール.command」
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from build_package import download_wheels  # noqa: E402
from pdfeval import __version__  # noqa: E402

FOLDER = "ストレスチェック集計システム"
APP = "ストレスチェック.app"
EXE = "ストレスチェック"
PART_PREFIX = f"ストレスチェックMac_v{__version__}_"
PART_SIZE = 25 * 1024 * 1024

INFO_PLIST = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>{EXE}</string>
  <key>CFBundleDisplayName</key><string>{EXE}</string>
  <key>CFBundleExecutable</key><string>{EXE}</string>
  <key>CFBundleIdentifier</key><string>jp.yadoli.stresscheck</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>{__version__}</string>
  <key>CFBundleVersion</key><string>{__version__}</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
"""

README = """ストレスチェック集計システム（Mac版）

■ 使い方
  「ストレスチェック.app」をダブルクリックすると、作業メニューが表示されます。
    ・名簿から調査票（印刷用PDF）を作る
    ・スキャンしたPDFを読み取って集計する
    ・動作確認（サンプルで試す）  … まずはこれで一通り試せます
    ・名簿を開く / 設定を開く / inbox・結果フォルダを開く

■ 最初に1回だけ必要なこと
  1. Python 3.12 または 3.13 のインストール
     https://www.python.org/downloads/macos/ の「macOS 64-bit universal2 installer」
     （入っていない場合は、アプリを開くと案内が出ます）
  2. 初めて開くときに準備（1〜2分）が自動で行われます。ネット接続は不要です。

■ フォルダについて
  このフォルダごと BtoB フォルダなど、好きな場所に置いて使えます。
  名簿.csv・config.json・inbox・output などは、このフォルダの中に作られます。
  output には職員の回答と結果が入るため、実施者だけが開ける場所で管理してください。

■ 対応機種
  Apple Silicon（M1〜M4）、Intel（macOS 14 以降）
"""

INSTALLER = r"""#!/bin/bash
# 分割ファイルを1つに戻して「ストレスチェック集計システム」フォルダを作ります。
# 送られてきたファイルをすべて同じフォルダ（例：ダウンロード）に置いてから、ダブルクリックしてください。
cd "$(dirname "$0")" || exit 1
FOLDER="__FOLDER__"
APP="__APP__"
ZIP="__FOLDER___Mac_install.zip"
SHA="__SHA__"
PARTS=(__PARTS__)

say() { osascript - "$1" <<'OSA' >/dev/null 2>&1
on run argv
  display dialog (item 1 of argv) with title "ストレスチェック集計システム" buttons {"OK"} default button 1
end run
OSA
}
ask() { osascript - "$1" <<'OSA' 2>/dev/null
on run argv
  set r to display dialog (item 1 of argv) with title "ストレスチェック集計システム" buttons {"いいえ", "はい"} default button 2
  return button returned of r
end run
OSA
}
trash() { for f in "$@"; do [ -e "$f" ] && osascript -e "tell application \"Finder\" to delete POSIX file \"$PWD/$f\"" >/dev/null 2>&1; done; }

missing=()
for p in "${PARTS[@]}"; do [ -f "$p" ] || missing+=("$p"); done
if [ ${#missing[@]} -gt 0 ]; then
  say "次のファイルが見つかりません。すべて同じフォルダに保存してから、もう一度開いてください。

${missing[*]}"
  exit 1
fi

cat "${PARTS[@]}" > "$ZIP"
if [ "$(shasum -a 256 "$ZIP" | cut -d' ' -f1)" != "$SHA" ]; then
  rm -f "$ZIP"
  say "ファイルが壊れています。もう一度ダウンロードしてください。"
  exit 1
fi

TMP="$(mktemp -d)"
ditto -x -k "$ZIP" "$TMP" || { say "展開に失敗しました。"; exit 1; }

# すでに使っているフォルダ（BtoB 内など）があれば、その中のアプリだけを入れ替える
TARGET=""
if [ -d "$FOLDER/$APP" ]; then
  TARGET="$PWD/$FOLDER"
elif [ "$(ask "以前から使っている「$FOLDER」フォルダ（BtoB フォルダ内など）はありますか？

「はい」を選ぶと、そのフォルダの中のアプリだけを新しくします（名簿・設定・結果はそのまま残ります）。
初めて使う場合は「いいえ」を選んでください。")" = "はい" ]; then
  picked=$(osascript -e 'POSIX path of (choose folder with prompt "使っている「ストレスチェック集計システム」フォルダを選んでください")' 2>/dev/null)
  picked="${picked%/}"
  if [ -n "$picked" ] && [ -d "$picked/$APP" ]; then
    TARGET="$picked"
  elif [ -n "$picked" ]; then
    say "選んだフォルダに「$APP」がありません。新しいフォルダとして作成します。"
  fi
fi
if [ -n "$TARGET" ]; then
  rm -rf "$TARGET/$APP"
  ditto "$TMP/$FOLDER/$APP" "$TARGET/$APP"
  cp "$TMP/$FOLDER/"*.txt "$TARGET/" 2>/dev/null
  xattr -dr com.apple.quarantine "$TARGET/$APP" 2>/dev/null
  updated="
「$TARGET」の中のアプリを新しくしました。名簿・設定・結果はそのままです。"
  DONE_APP="$TARGET/$APP"
  NEXT="そのまま「ストレスチェック.app」をダブルクリックして使えます。"
else
  ditto "$TMP/$FOLDER" "$FOLDER"
  xattr -dr com.apple.quarantine "$FOLDER" 2>/dev/null
  DONE_APP="$PWD/$FOLDER/$APP"
  NEXT="「$FOLDER」フォルダを、Finder で BtoB フォルダへドラッグして移動してください。
その後「ストレスチェック.app」をダブルクリックすると使えます。"
fi
rm -rf "$TMP"

# 送付用の分割ファイルと、以前お送りした旧版のファイルをゴミ箱へ
old=()
for f in "$ZIP" "${PARTS[@]}" ストレスチェックMac_*.part Mac用オフライン版_*.part pdf-evaluation-system-1.0.0-mac-offline.zip \
         pdf-evaluation-system-1.0.0-mac.zip 結合ツール_Mac.zip 結合_Mac.command; do
  [ -e "$f" ] && old+=("$f")
done
trash "${old[@]}"
for d in pdf-evaluation-system-1.0.0; do
  if [ -d "$d" ] && [ "$(ask "以前の版のフォルダ「$d」があります。ゴミ箱に入れますか？
（中の output に本番の結果がある場合は「いいえ」を選んでください）")" = "はい" ]; then
    trash "$d"
  fi
done

open -R "$DONE_APP"
say "インストールが完了しました。$updated

$NEXT

この「インストール.command」はゴミ箱に入れてかまいません。"
"""


def make_icon(path: Path) -> None:
    """円グラフ風のアイコン(.icns)を作る。"""
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((60, 60, size - 60, size - 60), radius=200, fill=(255, 255, 255, 255),
                        outline=(220, 220, 220, 255), width=8)
    box = (200, 200, size - 200, size - 200)
    d.pieslice(box, -90, 54, fill=(46, 139, 122, 255))
    d.pieslice(box, 54, 198, fill=(201, 162, 39, 255))
    d.pieslice(box, 198, 270, fill=(200, 85, 61, 255))
    c = size // 2
    d.ellipse((c - 150, c - 150, c + 150, c + 150), fill=(255, 255, 255, 255))
    img.save(path, sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])


def build_tree(dest: Path, wheels: Path) -> Path:
    top = dest / FOLDER
    res = top / APP / "Contents" / "Resources"
    macos = top / APP / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    res.mkdir(parents=True)
    (top / APP / "Contents" / "Info.plist").write_text(INFO_PLIST, encoding="utf-8")
    shutil.copy(HERE / "launcher.sh", macos / EXE)
    shutil.copytree(ROOT / "pdfeval", res / "pdfeval", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "sample", res / "sample", ignore=shutil.ignore_patterns("__pycache__", "正解.json"))
    for f in ("config.json", "requirements.txt"):
        shutil.copy(ROOT / f, res / f)
    (res / "VERSION").write_text(__version__, encoding="utf-8")
    shutil.copytree(wheels, res / "wheels")
    make_icon(res / "AppIcon.icns")
    (top / "はじめにお読みください.txt").write_text(README, encoding="utf-8")
    return top


def zip_tree(top: Path, out: Path) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(top.rglob("*")):
            arc = f.relative_to(top.parent).as_posix() + ("/" if f.is_dir() else "")
            info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            if f.is_dir():
                info.external_attr = (0o40755 << 16) | 0x10
                zf.writestr(info, b"")
                continue
            executable = f.parent.name == "MacOS"
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            info.compress_type = zipfile.ZIP_STORED if f.suffix == ".whl" else zipfile.ZIP_DEFLATED
            zf.writestr(info, f.read_bytes())


def split(path: Path, out_dir: Path) -> list[Path]:
    parts = []
    with path.open("rb") as f:
        i = 0
        while chunk := f.read(PART_SIZE):
            p = out_dir / f"{PART_PREFIX}{i:02d}.part"
            p.write_bytes(chunk)
            parts.append(p)
            i += 1
    return parts


def main() -> None:
    out_dir = ROOT / "dist" / "mac"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wheels = tmp / "wheels"
        download_wheels(wheels, "mac", ["3.12", "3.13"])
        top = build_tree(tmp / "tree", wheels)
        zip_path = out_dir / f"{FOLDER}_Mac.zip"
        zip_tree(top, zip_path)

    parts = split(zip_path, out_dir)
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    script = (INSTALLER.replace("__FOLDER__", FOLDER).replace("__APP__", APP).replace("__SHA__", sha)
              .replace("__PARTS__", " ".join(f'"{p.name}"' for p in parts)))
    with zipfile.ZipFile(out_dir / f"インストーラ_Mac_v{__version__}.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("インストール.command", date_time=(2026, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100755 << 16
        zf.writestr(info, script.encode("utf-8"))
    print(f"作成しました: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.0f} MB)")
    print(f"分割: {len(parts)}個 + インストーラ_Mac_v{__version__}.zip")


if __name__ == "__main__":
    main()
