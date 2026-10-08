"""動作確認用: 調査票に手書き風の○を付け、傾き・汚れのある「スキャン画像PDF」を作る。

    python sample/simulate_scan.py            → inbox/スキャン_サンプル.pdf と sample/正解.json
"""
from __future__ import annotations

import json
import random
import sys
import tempfile
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pdfeval import layout as L  # noqa: E402
from pdfeval.forms import make_forms, read_roster  # noqa: E402

DPI = 200
PX = DPI / 25.4

# 人ごとの回答傾向（1〜4 の出やすさ）。高ストレス者・そうでない人を混ぜる
PROFILES = {
    "E0001": {"A": [0.4, 0.4, 0.15, 0.05], "B": [0.05, 0.15, 0.4, 0.4], "C": [0.05, 0.15, 0.4, 0.4], "D": [0, 0.1, 0.5, 0.4]},
    "E0002": {"A": [0.2, 0.3, 0.3, 0.2], "B": [0.5, 0.35, 0.1, 0.05], "C": [0.5, 0.3, 0.15, 0.05], "D": [0.5, 0.4, 0.1, 0]},
    "E0003": {"A": [0.3, 0.3, 0.2, 0.2], "B": [0.2, 0.3, 0.3, 0.2], "C": [0.2, 0.3, 0.3, 0.2], "D": [0.2, 0.4, 0.3, 0.1]},
    "E0004": {"A": [0.2, 0.3, 0.3, 0.2], "B": [0.6, 0.3, 0.1, 0.0], "C": [0.6, 0.3, 0.1, 0.0], "D": [0.7, 0.3, 0, 0]},
}


def hand_circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, rng: random.Random) -> None:
    rx, ry = rng.uniform(3.2, 4.8) * PX, rng.uniform(2.2, 3.0) * PX
    cx += rng.uniform(-1.2, 1.2) * PX
    cy += rng.uniform(-0.6, 0.6) * PX
    start = rng.uniform(0, 2 * np.pi)
    pts = []
    for t in np.linspace(0, 2 * np.pi * rng.uniform(1.0, 1.15), 60):
        wob = 1 + 0.06 * np.sin(3 * t + start)
        pts.append((cx + rx * wob * np.cos(t + start), cy + ry * wob * np.sin(t + start)))
    draw.line(pts, fill=rng.randint(10, 60), width=rng.randint(3, 5))


def main(seed: int = 7) -> None:
    rng = random.Random(seed)
    people = read_roster(ROOT / "sample" / "名簿.csv")
    with tempfile.TemporaryDirectory() as tmp:
        blank = make_forms(people, Path(tmp))[0]
        doc = pdfium.PdfDocument(str(blank))
        pages = [doc[i].render(scale=DPI / 72, grayscale=True).to_pil().convert("L") for i in range(len(doc))]
        doc.close()

    truth: dict[str, dict[str, int]] = {}
    scans = []
    n_pages = len(L.LAYOUT)
    for idx, img in enumerate(pages):
        person = people[idx // n_pages]
        layout_page = L.LAYOUT[idx % n_pages]
        prof = PROFILES.get(person.id, PROFILES["E0003"])
        draw = ImageDraw.Draw(img)
        answers = truth.setdefault(person.id, {})
        for row in layout_page.rows:
            k = rng.choices([1, 2, 3, 4], weights=prof[row.section])[0]
            if (person.id, row.item) == ("E0003", "B2"):      # 記入もれ → 「未記入」になるはず
                answers[row.item] = None
                continue
            answers[row.item] = k
            hand_circle(draw, L.option_center_x(k) * PX, (row.y + 3.0) * PX, rng)
            if (person.id, row.item) == ("E0003", "A5"):      # ○が2つ → 「複数」になるはず
                answers[row.item] = None
                hand_circle(draw, L.option_center_x(k % 4 + 1) * PX, (row.y + 3.0) * PX, rng)
        # スキャンの傾き・ずれ・ノイズ
        img = img.rotate(rng.uniform(-1.5, 1.5), resample=Image.BICUBIC, fillcolor=255,
                         translate=(rng.uniform(-25, 25), rng.uniform(-25, 25)))
        arr = np.array(img, dtype=np.int16)
        arr += np.random.default_rng(seed + idx).normal(0, 8, arr.shape).astype(np.int16)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
        if idx == 2:
            img = img.rotate(180)          # 上下逆さに置いてスキャンされた想定
        scans.append(img)

    out = ROOT / "inbox"
    out.mkdir(exist_ok=True)
    # 2人目のページ順を入れ替え、まとめスキャン（順不同）も確認できるようにする
    scans[2], scans[3] = scans[3], scans[2]
    scans[0].save(out / "スキャン_サンプル.pdf", save_all=True, append_images=scans[1:], resolution=DPI)
    (ROOT / "sample" / "正解.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
    print("作成:", out / "スキャン_サンプル.pdf", f"({len(scans)}ページ)")


if __name__ == "__main__":
    main()
