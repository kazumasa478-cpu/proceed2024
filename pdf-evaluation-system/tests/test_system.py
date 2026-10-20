"""python -m unittest discover tests"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sample"))

from pdfeval.main import build_outputs, load_config, read_inbox, _roster  # noqa: E402
from pdfeval.questionnaire import ALL_ITEMS, score  # noqa: E402

CONFIG = load_config(ROOT / "config.json")


class ScoringTest(unittest.TestCase):
    def test_item_count(self):
        self.assertEqual(len(ALL_ITEMS), 57)

    def test_lowest_and_highest_stress(self):
        # 逆転項目を考慮して「最もストレスが低い」「最も高い」回答を作る
        from pdfeval.questionnaire import REVERSED
        low = {i: (4 if i in REVERSED else 1) for i in ALL_ITEMS}
        high = {i: (1 if i in REVERSED else 4) for i in ALL_ITEMS}
        r = score(low, CONFIG["criteria"])
        self.assertEqual((r.a, r.b, r.c, r.high_stress), (17, 29, 9, False))
        r = score(high, CONFIG["criteria"])
        self.assertEqual((r.a, r.b, r.c, r.high_stress), (68, 116, 36, True))

    def test_criteria_boundaries(self):
        crit = CONFIG["criteria"]
        def answers_with(b_total, ac_high):
            from pdfeval.questionnaire import REVERSED
            ans = {i: (1 if i in REVERSED else 4) if ac_high else (4 if i in REVERSED else 1)
                   for i in ALL_ITEMS if i[0] in "ACD"}
            pts = [1] * 29
            for k in range(b_total - 29):
                pts[k % 29] += 1
            for n, p in enumerate(pts, start=1):
                ans[f"B{n}"] = 5 - p if n <= 3 else p
            return ans
        self.assertFalse(score(answers_with(76, False), crit).high_stress)
        self.assertTrue(score(answers_with(77, False), crit).high_stress)   # 条件①
        self.assertFalse(score(answers_with(62, True), crit).high_stress)
        self.assertTrue(score(answers_with(63, True), crit).high_stress)    # 条件②


class EndToEndTest(unittest.TestCase):
    def test_scan_to_reports(self):
        import simulate_scan

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            shutil.copy(ROOT / "sample" / "名簿.csv", base / "名簿.csv")
            orig_root = simulate_scan.ROOT
            simulate_scan.ROOT = base
            (base / "sample").mkdir()
            shutil.copy(ROOT / "sample" / "名簿.csv", base / "sample" / "名簿.csv")
            try:
                simulate_scan.main()
            finally:
                simulate_scan.ROOT = orig_root
            truth = json.loads((base / "sample" / "正解.json").read_text(encoding="utf-8"))

            roster = _roster(base, CONFIG)
            self.assertEqual(read_inbox(base, CONFIG, roster), 0)
            build_outputs(base, CONFIG, roster)

            out = base / "output"
            for pid, answers in truth.items():
                folder = next(out.glob(f"{pid}_*"))
                ws = load_workbook(folder / "回答確認.xlsx")["回答"]
                read = {r[0]: (r[2], r[3]) for r in ws.iter_rows(min_row=4, values_only=True)}
                for item, expected in answers.items():
                    if expected is None:
                        self.assertIn(read[item][1], ("未記入", "複数"), f"{pid} {item}")
                    else:
                        self.assertEqual(read[item], (expected, "OK"), f"{pid} {item}")
            # 要確認が残る E0003 だけ結果通知書がない
            self.assertEqual(len(list(out.glob("*/結果通知書_*.pdf"))), 3)
            self.assertFalse(list(out.glob("E0003_*/結果通知書_*.pdf")))
            wb = load_workbook(out / "ストレスチェック集計.xlsx")
            self.assertEqual(wb.sheetnames, ["集計", "一覧", "回答データ", "要確認"])
            self.assertEqual(wb["要確認"].max_row, 3)
            self.assertEqual(len(wb["集計"]._charts), 2)


if __name__ == "__main__":
    unittest.main()


class InboxTest(unittest.TestCase):
    def test_subfolder_jpeg_and_unsupported(self):
        import io
        from contextlib import redirect_stdout

        import pypdfium2 as pdfium

        from pdfeval.forms import Person, make_forms
        from pdfeval.main import cmd_inbox, read_inbox

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            shutil.copy(ROOT / "sample" / "名簿.csv", base / "名簿.csv")
            pdf = make_forms([Person("E0001", "山田 太郎", "営業部")], base / "forms")[0]
            sub = base / "inbox" / "スキャン10月"            # フォルダごと入れた場合
            sub.mkdir(parents=True)
            shutil.copy(pdf, sub / "scan.pdf")
            doc = pdfium.PdfDocument(str(pdf))                # 2枚目は JPEG で保存された場合
            doc[1].render(scale=200 / 72).to_pil().save(base / "inbox" / "IMG_0002.JPG", quality=85)
            doc.close()
            (base / "inbox" / "IMG_0003.HEIC").write_bytes(b"x")
            (base / "inbox" / ".DS_Store").write_bytes(b"x")

            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cmd_inbox(base, CONFIG), 0)
            text = out.getvalue()
            self.assertIn("読み取れるファイル（PDF・JPEG・PNG・TIFF）：2件", text)
            self.assertIn("HEIC", text)

            read_inbox(base, CONFIG, _roster(base, CONFIG))
            folder = base / "output" / "E0001_山田太郎"
            self.assertTrue((folder / "調査票スキャン_1枚目.pdf").exists())
            self.assertTrue((folder / "調査票スキャン_2枚目.pdf").exists())   # JPEG からPDFにして保存
            self.assertTrue((base / "processed" / "IMG_0002.JPG").exists())

    def test_empty_inbox(self):
        from pdfeval.main import cmd_inbox
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cmd_inbox(Path(tmp), CONFIG), 2)

    def test_permission_denied(self):
        from unittest import mock

        from pdfeval import main as m
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(m, "scan_inbox", side_effect=PermissionError):
                self.assertEqual(m.cmd_inbox(Path(tmp), CONFIG), 3)


class RosterAndFixTest(unittest.TestCase):
    def test_roster_encodings_and_bom(self):
        from pdfeval.forms import Person, read_roster, write_roster
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "名簿.csv"
            for data in ("ID,氏名,所属\r\nE1,山田 太郎,営業\r\n".encode("cp932"),        # Excel（Shift_JIS）
                         "ID,氏名,所属\nE1,山田 太郎,営業\n".encode("utf-8-sig"),          # BOM付き
                         "ID\t氏名\t所属\nE1\t山田 太郎\t営業\n".encode("utf-16")):       # Excel「Unicodeテキスト」
                p.write_bytes(data)
                self.assertEqual(read_roster(p), [Person("E1", "山田 太郎", "営業")])
            write_roster(p, [Person("E1", "山田 太郎", "営業")])
            self.assertTrue(p.read_bytes().startswith(b"\xef\xbb\xbfID,"))   # Excelでも文字化けしない
            p.write_text("ID,氏名\nE;1,x\nE2,\n", encoding="utf-8")
            with self.assertRaises(ValueError) as cm:
                read_roster(p)
            self.assertIn("使えない文字", str(cm.exception))

    def test_roster_commands(self):
        import io
        from contextlib import redirect_stdout

        from pdfeval.main import cmd_roster
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            shutil.copy(ROOT / "sample" / "名簿.csv", base / "名簿.csv")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cmd_roster(base, CONFIG, "add", "E0009", "新人 花子", "訪問看護"), 0)
                self.assertEqual(cmd_roster(base, CONFIG, "add", "E0009", "重複", ""), 1)
                self.assertEqual(cmd_roster(base, CONFIG, "add", "x y", "空白入り", ""), 1)
                self.assertEqual(cmd_roster(base, CONFIG, "remove", "E0001", "", ""), 0)
            ids = [p.id for p in _roster(base, CONFIG).values()]
            self.assertIn("E0009", ids)
            self.assertNotIn("E0001", ids)

    def test_fix_answer_in_app(self):
        import io
        from contextlib import redirect_stdout

        import simulate_scan
        from pdfeval.main import cmd_fix, list_todo

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "sample").mkdir()
            shutil.copy(ROOT / "sample" / "名簿.csv", base / "名簿.csv")
            shutil.copy(ROOT / "sample" / "名簿.csv", base / "sample" / "名簿.csv")
            orig, simulate_scan.ROOT = simulate_scan.ROOT, base
            try:
                simulate_scan.main()
            finally:
                simulate_scan.ROOT = orig
            roster = _roster(base, CONFIG)
            read_inbox(base, CONFIG, roster)
            people, _ = list_todo(base, CONFIG, roster)
            self.assertEqual([p["person"].id for p in people], ["E0003"])
            with redirect_stdout(io.StringIO()):
                cmd_fix(base, CONFIG, "E0003", "A5", "2")
                cmd_fix(base, CONFIG, "E0003", "B2", "none")
            self.assertEqual(list_todo(base, CONFIG, roster)[0], [])
            build_outputs(base, CONFIG, roster)
            self.assertTrue(list((base / "output").glob("E0003_*/結果通知書_*.pdf")))
