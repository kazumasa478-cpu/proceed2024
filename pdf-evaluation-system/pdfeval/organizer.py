"""本人ごとのフォルダに、スキャン原本と回答確認シート(Excel)を保存・読込する。

回答確認シートは担当者が直接修正できる。読取に自信がない項目は「状態」が
要確認/未記入/複数 になるので、原本PDFを見て「回答」を直し、「状態」を「確認済」にする。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from pypdf import PdfReader, PdfWriter

from .forms import Person
from .omr import ItemRead
from .questionnaire import ALL_ITEMS, item_label

ANSWER_BOOK = "回答確認.xlsx"
RESOLVED = {"OK", "確認済"}
STATUSES = ["OK", "確認済", "要確認", "未記入", "複数"]


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "", name).strip(".") or "_"


def person_folder(output: Path, person: Person) -> Path:
    return output / f"{safe_name(person.id)}_{safe_name(person.name)}"


@dataclass
class AnswerSheet:
    person: Person
    folder: Path
    answers: dict[str, int | None]
    statuses: dict[str, str]

    @property
    def unresolved(self) -> list[str]:
        return [i for i in ALL_ITEMS if self.statuses.get(i) not in RESOLVED]


def save_page_pdf(source: Path, page_no: int, dest: Path) -> None:
    writer = PdfWriter()
    writer.add_page(PdfReader(source).pages[page_no - 1])
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        writer.write(f)


def update_answers(folder: Path, person: Person, reads: list[ItemRead]) -> None:
    """読み取った項目で回答確認シートを更新（他ページ分・手修正済みの行は残す）。"""
    path = folder / ANSWER_BOOK
    current = load_answer_sheet(folder, person)
    answers = dict(current.answers) if current else {}
    statuses = dict(current.statuses) if current else {}
    scores: dict[str, str] = {}
    for r in reads:
        answers[r.item] = r.answer
        statuses[r.item] = r.status
        scores[r.item] = " / ".join(f"{s:.1f}" for s in r.scores)

    old_scores = {}
    if path.exists():
        ws = load_workbook(path)["回答"]
        old_scores = {row[0]: row[4] for row in ws.iter_rows(min_row=4, values_only=True) if row[0]}

    wb = Workbook()
    ws = wb.active
    ws.title = "回答"
    ws["A1"] = f"ID: {person.id}　氏名: {person.name}　所属: {person.dept}"
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = ("読取結果を確認し、必要なら「回答」(1〜4)を修正して「状態」を「確認済」にしてください。"
                "未回答のままにする場合も「確認済」にします。")
    ws.append(["項目", "質問", "回答", "状態", "読取インク量(1/2/3/4)"])
    for c in ws[3]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDEBF7")
    for item in ALL_ITEMS:
        ws.append([item, item_label(item), answers.get(item), statuses.get(item, "未記入"),
                   scores.get(item, old_scores.get(item, ""))])
    last = 3 + len(ALL_ITEMS)
    for row in ws.iter_rows(min_row=4, max_row=last, min_col=3, max_col=4):
        for c in row:
            c.alignment = Alignment(horizontal="center")
    dv_ans = DataValidation(type="whole", operator="between", formula1="1", formula2="4", allow_blank=True)
    dv_st = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"')
    ws.add_data_validation(dv_ans)
    ws.add_data_validation(dv_st)
    dv_ans.add(f"C4:C{last}")
    dv_st.add(f"D4:D{last}")
    ws.conditional_formatting.add(
        f"A4:E{last}",
        FormulaRule(formula=['AND($D4<>"OK",$D4<>"確認済")'], fill=PatternFill("solid", fgColor="FFE699")))
    ws.freeze_panes = "A4"
    for col, w in {"A": 6, "B": 44, "C": 7, "D": 9, "E": 24}.items():
        ws.column_dimensions[col].width = w
    folder.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def load_answer_sheet(folder: Path, person: Person) -> AnswerSheet | None:
    path = folder / ANSWER_BOOK
    if not path.exists():
        return None
    ws = load_workbook(path, data_only=True)["回答"]
    answers, statuses = {}, {}
    for item, _, ans, status, *_ in ws.iter_rows(min_row=4, values_only=True):
        if item not in ALL_ITEMS:
            continue
        try:
            ans = int(ans) if ans not in (None, "") else None
        except (TypeError, ValueError):
            ans, status = None, "要確認"
        if ans is not None and not 1 <= ans <= 4:
            ans, status = None, "要確認"
        answers[item] = ans
        statuses[item] = str(status or "未記入").strip()
    return AnswerSheet(person, folder, answers, statuses)
