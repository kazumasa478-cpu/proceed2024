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
