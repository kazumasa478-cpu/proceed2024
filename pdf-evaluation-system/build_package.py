"""移設用パッケージ(zip)を dist/ に作成する。

    python build_package.py                 # 通常版（移設先でネットからライブラリを入れる）
    python build_package.py --offline win   # Windows向けオフライン版（ライブラリ同梱）
    python build_package.py --offline mac   # macOS(Apple Silicon)向けオフライン版

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
INCLUDE = [
    "pdfeval", "sample", "tests", "config.json", "requirements.txt", "README.md",
    "setup.bat", "make_forms.bat", "run.bat", "setup.sh", "run.sh",
]
PLATFORMS = {
    "win": ["win_amd64"],
    "mac": ["macosx_11_0_arm64", "macosx_14_0_arm64"],
    "linux": ["manylinux2014_x86_64", "manylinux_2_17_x86_64", "manylinux_2_28_x86_64"],
}


def download_wheels(dest: Path, platform: str, python_version: str) -> None:
    cmd = [sys.executable, "-m", "pip", "download", "-r", str(ROOT / "requirements.txt"),
           "-d", str(dest), "--only-binary=:all:", "--python-version", python_version]
    for tag in PLATFORMS[platform]:
        cmd += ["--platform", tag]
    subprocess.run(cmd, check=True)


def build(offline: str | None, python_version: str) -> Path:
    suffix = f"-offline-{offline}-py{python_version.replace('.', '')}" if offline else ""
    name = f"pdf-evaluation-system-{__version__}"
    out = ROOT / "dist" / f"{name}{suffix}.zip"
    out.parent.mkdir(exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in INCLUDE:
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
                info.external_attr = (0o755 if f.suffix == ".sh" else 0o644) << 16
                zf.writestr(info, data)
        for empty in ("inbox", "output"):
            zf.writestr(f"{name}/{empty}/", "")
        if offline:
            with tempfile.TemporaryDirectory() as tmp:
                download_wheels(Path(tmp), offline, python_version)
                for whl in sorted(Path(tmp).iterdir()):
                    zf.write(whl, f"{name}/wheels/{whl.name}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--offline", choices=PLATFORMS, help="ライブラリを同梱する移設先OS")
    parser.add_argument("--python-version", default="3.12", help="移設先のPythonバージョン (既定: 3.12)")
    args = parser.parse_args()
    out = build(args.offline, args.python_version)
    print(f"作成しました: {out}  ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
