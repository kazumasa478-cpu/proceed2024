"""スキャンの向き・明るさムラ・縮小印刷などで誤読や読取不可にならないことを確かめる。"""
import random
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sample"))

from pdfeval import layout as L  # noqa: E402
from pdfeval.forms import Person, make_forms  # noqa: E402
from pdfeval.omr import DPI, PX, read_page  # noqa: E402
from simulate_scan import hand_circle  # noqa: E402


class RobustnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = make_forms([Person("E0001", "山田 太郎", "営業部")], Path(tmp))[0]
            doc = pdfium.PdfDocument(str(pdf))
            cls.page = doc[0].render(scale=DPI / 72, grayscale=True).to_pil().convert("L")
            doc.close()
        rng = random.Random(1)
        cls.truth = {}
        draw = ImageDraw.Draw(cls.page)
        for row in L.LAYOUT[0].rows:
            k = rng.randint(1, 4)
            cls.truth[row.item] = k
            hand_circle(draw, L.option_center_x(k) * PX, (row.y + 3) * PX, rng)

    def assert_reads(self, img: Image.Image):
        r = read_page(np.array(img.convert("L")), 1, {})
        self.assertEqual(r.error, "")
        self.assertEqual(r.person_id, "E0001")
        self.assertEqual({i.item: i.answer for i in r.items}, self.truth)

    def test_upside_down(self):
        # 以前は向きを取り違えて回答を誤読していた
        self.assert_reads(self.page.rotate(180))

    def test_sideways(self):
        self.assert_reads(self.page.transpose(Image.ROTATE_90))
        self.assert_reads(self.page.transpose(Image.ROTATE_270))

    def test_uneven_lighting(self):
        a = np.array(self.page, dtype=np.float32)
        h, w = a.shape
        shade = np.linspace(1.0, 0.55, w)[None, :] * np.linspace(1.0, 0.8, h)[:, None]
        self.assert_reads(Image.fromarray(np.clip(a * shade, 0, 255).astype(np.uint8)).rotate(180))

    def test_shrunk_print_and_low_dpi(self):
        w, h = self.page.size
        small = self.page.resize((int(w * 0.9), int(h * 0.9)))
        canvas = Image.new("L", (w, h), 255)
        canvas.paste(small, ((w - small.width) // 2, (h - small.height) // 2))
        self.assert_reads(canvas.resize((w * 3 // 4, h * 3 // 4)))

    def test_form_without_marks_is_reported(self):
        # 元のWordの調査票など、QR・位置合わせマークのない用紙
        blank = Image.new("L", self.page.size, 255)
        ImageDraw.Draw(blank).text((200, 200), "survey", fill=0)
        r = read_page(np.array(blank), 1, {})
        self.assertIn("位置合わせマーク", r.error)


if __name__ == "__main__":
    unittest.main()
