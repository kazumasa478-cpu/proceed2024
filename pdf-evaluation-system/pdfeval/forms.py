"""名簿から、本人特定用QRコード入りの印刷用調査票PDFを作成する。"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from . import layout as L
from .questionnaire import SECTION_BY_KEY

FONT = "HeiseiKakuGo-W5"
QR_PREFIX = "SC57"
ZEN = "１２３４"


@dataclass
class Person:
    id: str
    name: str
    dept: str = ""


def read_roster(path: Path) -> list[Person]:
    """名簿CSV（列: ID, 氏名, 所属）。Excelで保存したShift_JISにも対応。"""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp932"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"{path} の文字コードを判別できません")
    people = []
    for row in csv.DictReader(text.splitlines()):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if row.get("ID") and row.get("氏名"):
            people.append(Person(row["ID"], row["氏名"], row.get("所属", "")))
    ids = [p.id for p in people]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"名簿のIDが重複しています: {', '.join(sorted(dup))}")
    return people


def qr_payload(person_id: str, page: int) -> str:
    return f"{QR_PREFIX};{person_id};{page}"


def parse_qr(payload: str) -> tuple[str, int] | None:
    parts = payload.split(";")
    if len(parts) == 3 and parts[0] == QR_PREFIX and parts[2].isdigit():
        return parts[1], int(parts[2])
    return None


class _Canvas:
    """mm・左上原点で描くための薄いラッパー。"""

    def __init__(self, c: canvas.Canvas):
        self.c = c

    def y(self, y_mm: float) -> float:
        return (L.PAGE_H - y_mm) * mm

    def text(self, x, y, s, size=9, center=False, gray=0.0):
        self.c.setFillGray(gray)
        self.c.setFont(FONT, size)
        if center:
            self.c.drawCentredString(x * mm, self.y(y), s)
        else:
            self.c.drawString(x * mm, self.y(y), s)

    def fit_text(self, x, y, s, width, size=9, center=False):
        while size > 5.5 and pdfmetrics.stringWidth(s, FONT, size) > width * mm:
            size -= 0.25
        self.text(x, y, s, size, center=center)

    def rect(self, x, y, w, h, fill=False, stroke_gray=0.0, fill_gray=None, line=0.5):
        self.c.setLineWidth(line)
        self.c.setStrokeGray(stroke_gray)
        if fill_gray is not None:
            self.c.setFillGray(fill_gray)
        self.c.rect(x * mm, self.y(y + h), w * mm, h * mm,
                    stroke=1, fill=1 if (fill or fill_gray is not None) else 0)

    def line(self, x1, y1, x2, y2, gray=0.0, width=0.5):
        self.c.setStrokeGray(gray)
        self.c.setLineWidth(width)
        self.c.line(x1 * mm, self.y(y1), x2 * mm, self.y(y2))


def _draw_markers_and_qr(cv: _Canvas, person: Person, page: int, n_pages: int) -> None:
    for cx, cy in L.marker_centers():
        h = L.MARKER / 2
        cv.c.setFillGray(0)
        cv.rect(cx - h, cy - h, L.MARKER, L.MARKER, fill=True, fill_gray=0)
    x, y, size = L.QR_BOX
    widget = QrCodeWidget(qr_payload(person.id, page), barLevel="M")
    b = widget.getBounds()
    d = Drawing(size * mm, size * mm,
                transform=[size * mm / (b[2] - b[0]), 0, 0, size * mm / (b[3] - b[1]), 0, 0])
    d.add(widget)
    renderPDF.draw(d, cv.c, x * mm, cv.y(y + size))
    cv.text(x + size / 2, y + size + 3.5, f"{page}/{n_pages}", size=7, center=True)


def _draw_header(cv: _Canvas, person: Person) -> None:
    cv.text(L.LEFT, 26, "職業性ストレス簡易調査票（57項目）", size=15)
    top, h, label_w, w = 31.0, 6.5, 30.0, 140.0
    rows = [("ID", person.id), ("氏名", person.name), ("所属", person.dept),
            ("記入日", "　　　　年　　　月　　　日")]
    for i, (label, value) in enumerate(rows):
        y = top + i * h
        cv.rect(L.LEFT, y, label_w, h, fill_gray=0.92)
        cv.rect(L.LEFT + label_w, y, w - label_w, h)
        cv.text(L.LEFT + 2, y + 4.6, label, size=9)
        cv.text(L.LEFT + label_w + 3, y + 4.6, value, size=10)
    cv.text(L.LEFT, top + 4 * h + 5,
            "・Ａ～Ｄの各項目について、最もあてはまる数字（１～４）を○で囲んでください。"
            "黒のボールペンで記入してください。", size=8)
    cv.text(L.LEFT, top + 4 * h + 9.5,
            "・訂正するときは、誤った○に×を付けず、修正テープで消してから記入し直してください。"
            "用紙は折らないでください。", size=8)


def _draw_page_header_small(cv: _Canvas, person: Person) -> None:
    cv.text(L.LEFT, 26, "職業性ストレス簡易調査票（57項目）（つづき）", size=12)
    cv.text(L.LEFT, 34, f"ID：{person.id}　　氏名：{person.name}", size=10)


def _draw_blocks(cv: _Canvas, page: L.Page) -> None:
    right = L.OPT_X0 + 4 * L.OPT_W
    for b in page.blocks:
        sec = SECTION_BY_KEY[b.section]
        if b.kind == "section":
            cv.text(L.LEFT, b.y + 5, b.text + "　最もあてはまる数字に○を付けてください。", size=10)
        elif b.kind == "colhead":
            cv.rect(L.LEFT, b.y, right - L.LEFT, b.h, fill_gray=0.88)
            cv.text(L.LEFT + L.NO_W / 2, b.y + 5.2, "No.", size=8, center=True)
            cv.text(L.LEFT + L.NO_W + 2, b.y + 5.2,
                    "対象" if b.section == "C" else "質問項目", size=8)
            for k, opt in enumerate(sec.options, start=1):
                cv.fit_text(L.option_center_x(k), b.y + 5.2, opt, L.OPT_W - 1.5, 8, center=True)
                cv.line(L.option_center_x(k) - L.OPT_W / 2, b.y, L.option_center_x(k) - L.OPT_W / 2,
                        b.y + b.h, gray=0.5, width=0.3)
        elif b.kind == "group":
            cv.text(L.LEFT + 1, b.y + 4, b.text, size=8.5)
        else:
            cv.line(L.LEFT, b.y + b.h, right, b.y + b.h, gray=0.6, width=0.3)
            cv.text(L.LEFT + L.NO_W / 2, b.y + 4.3, str(b.no), size=9, center=True)
            cv.fit_text(L.LEFT + L.NO_W + 1, b.y + 4.3, b.text, L.OPT_X0 - L.LEFT - L.NO_W - 2)
            for k in range(1, 5):
                # 数字は薄めの灰色（読取時に記入の○と区別しやすくするため）
                cv.text(L.option_center_x(k), b.y + 4.3, ZEN[k - 1], size=10, center=True, gray=0.5)


def draw_form(c: canvas.Canvas, person: Person) -> None:
    n_pages = len(L.LAYOUT)
    for page in L.LAYOUT:
        cv = _Canvas(c)
        _draw_markers_and_qr(cv, person, page.number, n_pages)
        if page.number == 1:
            _draw_header(cv, person)
        else:
            _draw_page_header_small(cv, person)
        _draw_blocks(cv, page)
        if page.number == n_pages:
            last = page.blocks[-1]
            cv.text(L.LEFT, last.y + last.h + 7,
                    "以上です。記入もれがないか、ご確認ください。ご協力ありがとうございました。", size=9)
        c.showPage()


def make_forms(people: list[Person], out_dir: Path, combined: bool = True) -> list[Path]:
    """combined=True なら全員分を1つのPDF（まとめて両面印刷用）にする。"""
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    if combined:
        path = out_dir / "調査票_全員分.pdf"
        c = canvas.Canvas(str(path), pagesize=(L.PAGE_W * mm, L.PAGE_H * mm))
        c.setTitle("職業性ストレス簡易調査票")
        for p in people:
            draw_form(c, p)
        c.save()
        paths.append(path)
    else:
        for p in people:
            path = out_dir / f"調査票_{p.id}_{p.name}.pdf"
            c = canvas.Canvas(str(path), pagesize=(L.PAGE_W * mm, L.PAGE_H * mm))
            draw_form(c, p)
            c.save()
            paths.append(path)
    return paths
