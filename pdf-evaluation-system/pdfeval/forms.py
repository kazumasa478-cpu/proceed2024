"""名簿から、本人特定用QRコード入りの印刷用調査票PDFを作成する。"""
from __future__ import annotations

import csv
import re
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
MARK_SHEET = "M"     # QRの4番目の値。M=マークシート形式（ぬりつぶし）、なし=旧形式（○で囲む）
ZEN = "１２３４"


@dataclass
class Person:
    id: str
    name: str
    dept: str = ""


ROSTER_HEADER = ["ID", "氏名", "所属"]
_ID_OK = re.compile(r"^[0-9A-Za-z_-]{1,20}$")


def valid_id(person_id: str) -> bool:
    """ID は英数字・ハイフン・アンダーバーのみ（QRコードとフォルダ名に使うため）。"""
    return bool(_ID_OK.match(person_id))


def read_roster(path: Path) -> list[Person]:
    """名簿CSV（列: ID, 氏名, 所属）を読む。UTF-8（BOMあり/なし）・Shift_JIS・UTF-16 に対応。"""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        for enc in ("utf-8-sig", "cp932"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError(f"名簿の文字コードを判別できません: {path}")
    lines = text.splitlines()
    delimiter = "\t" if lines and "\t" in lines[0] and "," not in lines[0] else ","
    people, bad = [], []
    for row in csv.DictReader(lines, delimiter=delimiter):
        row = {(k or "").strip().lstrip("\ufeff"): (v or "").strip() for k, v in row.items() if k}
        pid, name = row.get("ID", ""), row.get("氏名") or row.get("名前", "")
        if not pid and not name:
            continue
        if not pid or not name:
            bad.append(f"IDまたは氏名が空の行があります（{pid or name}）")
        elif not valid_id(pid):
            bad.append(f"ID「{pid}」に使えない文字があります（英数字・-・_ のみ）")
        else:
            people.append(Person(pid, name, row.get("所属", "")))
    ids = [p.id for p in people]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        bad.append(f"IDが重複しています: {', '.join(dup)}")
    if bad:
        raise ValueError("名簿に問題があります：\n" + "\n".join(bad))
    return people


def write_roster(path: Path, people: list[Person]) -> None:
    """名簿CSVを書く。BOM付きUTF-8にして、Excel・Numbers・テキストエディットのどれで開いても文字化けしないようにする。"""
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(ROSTER_HEADER)
    for p in people:
        w.writerow([p.id, p.name, p.dept])
    path.write_text(buf.getvalue(), encoding="utf-8-sig")


def qr_payload(person_id: str, page: int, style: str = MARK_SHEET) -> str:
    return f"{QR_PREFIX};{person_id};{page}" + (f";{style}" if style == MARK_SHEET else "")


def parse_qr(payload: str) -> tuple[str, int, str] | None:
    """(ID, ページ, 形式) を返す。形式は "M"=マークシート、"C"=旧形式（○で囲む）。"""
    parts = payload.split(";")
    if len(parts) in (3, 4) and parts[0] == QR_PREFIX and parts[2].isdigit():
        style = MARK_SHEET if len(parts) == 4 and parts[3] == MARK_SHEET else "C"
        return parts[1], int(parts[2]), style
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


def _draw_markers_and_qr(cv: _Canvas, person: Person, page: int, n_pages: int, style: str) -> None:
    for cx, cy in L.marker_centers():
        h = L.MARKER / 2
        cv.c.setFillGray(0)
        cv.rect(cx - h, cy - h, L.MARKER, L.MARKER, fill=True, fill_gray=0)
    x, y, size = L.QR_BOX
    widget = QrCodeWidget(qr_payload(person.id, page, style), barLevel="M")
    b = widget.getBounds()
    d = Drawing(size * mm, size * mm,
                transform=[size * mm / (b[2] - b[0]), 0, 0, size * mm / (b[3] - b[1]), 0, 0])
    d.add(widget)
    renderPDF.draw(d, cv.c, x * mm, cv.y(y + size))
    cv.text(x + size / 2, y + size + 3.5, f"{page}/{n_pages}", size=7, center=True)


def _bubble(cv: _Canvas, cx: float, cy: float, label: str = "", filled: bool = False) -> None:
    """マークシートの楕円。線と数字は薄い灰色にして、記入したインクだけが濃く写るようにする。"""
    c = cv.c
    w, h = L.BUBBLE_W * mm, L.BUBBLE_H * mm
    c.setLineWidth(0.6)
    c.setStrokeGray(0.55)
    c.setFillGray(0.1 if filled else 1)
    c.ellipse(cx * mm - w / 2, cv.y(cy) - h / 2, cx * mm + w / 2, cv.y(cy) + h / 2,
              stroke=1, fill=1 if filled else 0)
    if label:
        c.setFillGray(0.6)
        c.setFont(FONT, 7)
        c.drawCentredString(cx * mm, cv.y(cy) - 0.85 * mm, label)


def _draw_header(cv: _Canvas, person: Person, style: str = MARK_SHEET) -> None:
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
    y1, y2 = top + 4 * h + 4.2, top + 4 * h + 8.8
    if style != MARK_SHEET:
        cv.text(L.LEFT, y1, "・Ａ～Ｄの各項目について、最もあてはまる数字（１～４）を○で囲んでください。"
                "黒のボールペンで記入してください。", size=8)
        cv.text(L.LEFT, y2, "・訂正するときは、誤った○に×を付けず、修正テープで消してから記入し直してください。"
                "用紙は折らないでください。", size=8)
        return
    cv.text(L.LEFT, y1, "・各項目について、最もあてはまる番号の楕円を、黒のボールペンまたは濃い鉛筆（HB以上）で"
            "ぬりつぶしてください。", size=8)
    x = L.LEFT
    cv.text(x, y2 + 0.2, "・よい例", size=8)
    _bubble(cv, x + 16, y2 - 1.0, filled=True)
    cv.text(x + 23, y2 + 0.2, "わるい例", size=8)
    _bubble(cv, x + 43, y2 - 1.0, "1")                     # ○で囲む
    cv.c.setLineWidth(0.7)
    cv.c.setStrokeGray(0)
    cv.c.ellipse((x + 37.5) * mm, cv.y(y2 + 1.9), (x + 48.5) * mm, cv.y(y2 - 3.9), stroke=1, fill=0)
    _bubble(cv, x + 56, y2 - 1.0, "2")                     # レ点
    cv.c.setLineWidth(0.9)
    p = cv.c.beginPath()
    p.moveTo((x + 53.5) * mm, cv.y(y2 - 1.2))
    p.lineTo((x + 55.5) * mm, cv.y(y2 + 0.6))
    p.lineTo((x + 59) * mm, cv.y(y2 - 3.0))
    cv.c.drawPath(p, stroke=1, fill=0)
    cv.text(x + 63, y2 + 0.2, "訂正は消しゴム・修正テープできれいに消してください。用紙は折らないでください。", size=8)


def _draw_page_header_small(cv: _Canvas, person: Person) -> None:
    cv.text(L.LEFT, 26, "職業性ストレス簡易調査票（57項目）（つづき）", size=12)
    cv.text(L.LEFT, 34, f"ID：{person.id}　　氏名：{person.name}", size=10)


def _draw_blocks(cv: _Canvas, page: L.Page, style: str = MARK_SHEET) -> None:
    right = L.OPT_X0 + 4 * L.OPT_W
    for b in page.blocks:
        sec = SECTION_BY_KEY[b.section]
        if b.kind == "section":
            how = "番号をぬりつぶしてください。" if style == MARK_SHEET else "数字に○を付けてください。"
            cv.text(L.LEFT, b.y + 5, f"{b.text}　最もあてはまる{how}", size=10)
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
                if style == MARK_SHEET:
                    _bubble(cv, L.option_center_x(k), b.y + b.h / 2, str(k))
                else:
                    # 数字は薄めの灰色（読取時に記入の○と区別しやすくするため）
                    cv.text(L.option_center_x(k), b.y + 4.3, ZEN[k - 1], size=10, center=True, gray=0.5)


def draw_form(c: canvas.Canvas, person: Person, style: str = MARK_SHEET) -> None:
    n_pages = len(L.LAYOUT)
    for page in L.LAYOUT:
        cv = _Canvas(c)
        _draw_markers_and_qr(cv, person, page.number, n_pages, style)
        if page.number == 1:
            _draw_header(cv, person, style)
        else:
            _draw_page_header_small(cv, person)
        _draw_blocks(cv, page, style)
        if page.number == n_pages:
            last = page.blocks[-1]
            cv.text(L.LEFT, last.y + last.h + 7,
                    "以上です。記入もれがないか、ご確認ください。ご協力ありがとうございました。", size=9)
        c.showPage()


def make_forms(people: list[Person], out_dir: Path, combined: bool = True,
               style: str = MARK_SHEET) -> list[Path]:
    """combined=True なら全員分を1つのPDF（まとめて両面印刷用）にする。"""
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    if combined:
        path = out_dir / "調査票_全員分.pdf"
        c = canvas.Canvas(str(path), pagesize=(L.PAGE_W * mm, L.PAGE_H * mm))
        c.setTitle("職業性ストレス簡易調査票")
        for p in people:
            draw_form(c, p, style)
        c.save()
        paths.append(path)
    else:
        for p in people:
            path = out_dir / f"調査票_{p.id}_{p.name}.pdf"
            c = canvas.Canvas(str(path), pagesize=(L.PAGE_W * mm, L.PAGE_H * mm))
            draw_form(c, p, style)
            c.save()
            paths.append(path)
    return paths
