"""移設用パッケージ(zip)を dist/ に作成する。

    python build_package.py                 # 通常版（移設先でネットからライブラリを入れる）
    python build_package.py --os mac        # Mac用（.command のみ）
    python build_package.py --os win        # Windows用（.bat のみ）
    python build_package.py --os mac --offline mac   # Mac用オフライン版（Apple Silicon/Intel両対応）
    python build_package.py --os win --offline win   # Windows用オフライン版

名簿・調査票・回答・結果（名簿.csv / 調査票 / inbox / output / processed / logs）は
個人情報を含むため同梱しない。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from pdfeval import __version__

ROOT = Path(__file__).resolve().parent
INCLUDE = ["pdfeval", "sample", "tests", "config.json", "requirements.txt", "README.md"]
LAUNCHERS = {
    "win": ["setup.bat", "make_forms.bat", "run.bat"],
    "mac": ["setup.command", "make_forms.command", "run.command", "動作確認.command",
            "setup.sh", "run.sh"],
}
_MAC_VERSIONS = ["10_9", "10_13", "10_15", "11_0", "12_0", "13_0", "14_0", "15_0"]
# 1つのzipで複数の機種に対応するため、機種ごとに必要なライブラリをすべて同梱する
PLATFORMS = {
    "win": {"x64": ["win_amd64"]},
    "mac": {
        "AppleSilicon": [f"macosx_{v}_{a}" for v in _MAC_VERSIONS for a in ("arm64", "universal2")],
        "Intel": [f"macosx_{v}_{a}" for v in _MAC_VERSIONS for a in ("x86_64", "universal2", "intel")],
    },
    "linux": {"x64": ["manylinux2014_x86_64", "manylinux_2_17_x86_64", "manylinux_2_28_x86_64"]},
}


def download_wheels(dest: Path, platform: str, python_versions: list[str]) -> None:
    for py in python_versions:
        for arch, tags in PLATFORMS[platform].items():
            print(f"ライブラリを取得中: {platform}/{arch} Python {py}")
            cmd = [sys.executable, "-m", "pip", "download", "-q", "-r", str(ROOT / "requirements.txt"),
                   "-d", str(dest), "--only-binary=:all:", "--python-version", py]
            for tag in tags:
                cmd += ["--platform", tag]
            subprocess.run(cmd, check=True)


def build(offline: str | None, python_versions: list[str], target_os: str = "all") -> Path:
    suffix = f"-{target_os}" if target_os != "all" else ""
    if offline:
        suffix += "-offline"
    launchers = [f for os_name, files in LAUNCHERS.items()
                 if target_os in ("all", os_name) for f in files]
    name = f"pdf-evaluation-system-{__version__}"
    out = ROOT / "dist" / f"{name}{suffix}.zip"
    out.parent.mkdir(exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in INCLUDE + launchers:
            path = ROOT / entry
            files = [path] if path.is_file() else sorted(path.rglob("*"))
            for f in files:
                if f.is_dir() or "__pycache__" in f.parts or f.name == "正解.json":
                    continue
                arc = f"{name}/{f.relative_to(ROOT).as_posix()}"
                data = f.read_bytes()
                if f.suffix == ".bat":  # Windowsのバッチは CRLF・Shift_JIS でないと日本語パスが壊れる
                    text = data.decode("utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
                    data = text.encode("cp932")
                info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3   # Unix形式の権限を記録（Macで展開しても実行可能のまま）
                info.external_attr = (0o100755 if f.suffix in (".sh", ".command") else 0o100644) << 16
                zf.writestr(info, data)
        for empty in ("inbox", "output"):
            zf.writestr(f"{name}/{empty}/", "")
        if offline:
            with tempfile.TemporaryDirectory() as tmp:
                download_wheels(Path(tmp), offline, python_versions)
                for whl in sorted(Path(tmp).iterdir()):
                    zf.write(whl, f"{name}/wheels/{whl.name}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--offline", choices=PLATFORMS, help="ライブラリを同梱する移設先OS")
    parser.add_argument("--os", dest="target_os", choices=["all", "win", "mac"], default="all",
                        help="同梱する起動ファイル (既定: all)")
    parser.add_argument("--python-version", default="3.12,3.13",
                        help="移設先で使うPythonのバージョン（カンマ区切り, 既定: 3.12,3.13）")
    args = parser.parse_args()
    out = build(args.offline, args.python_version.split(","), args.target_os)
    print(f"作成しました: {out}  ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
