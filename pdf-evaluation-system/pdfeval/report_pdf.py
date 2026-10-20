"""本人に手渡す「結果のお知らせ」（A4・1枚）を作成する。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from pypdf import PdfWriter

from . import layout as L
from .forms import FONT, Person, _Canvas
from .questionnaire import DOMAINS, Result, scale_level

LEVEL_COLOR = {"良好": HexColor("#2E8B7A"), "ふつう": HexColor("#C9A227"),
               "要注意": HexColor("#C8553D"), "－": HexColor("#999999")}
TRACK = HexColor("#E6E6E6")

ADVICE = {
    "B": "心身のストレス反応が強めに出ています。睡眠と休養を優先し、つらい状態が続くときは早めに相談窓口や医療機関に相談してください。",
    "A": "仕事の量・負担や職場環境などから、ストレスを受けやすい状況です。抱え込まず、上司や担当者に業務の調整を相談してみてください。",
    "C": "周囲からの支えを得にくいと感じています。身近な人や相談窓口など、話しやすい相手に声をかけてみてください。",
}
GOOD = "現在、目立ったストレスの偏りはみられません。今の生活リズムやストレス対処を続けてください。"


def _donut(cv: _Canvas, cx: float, cy: float, r: float, frac: float, color, center_big: str,
           center_small: str) -> None:
    """円グラフ（ドーナツ型）。frac は 0〜1。12時方向から時計回り。"""
    c = cv.c
    x, y, rr = cx * mm, cv.y(cy), r * mm
    c.setFillColor(TRACK)
    c.setStrokeColor(white)
    c.circle(x, y, rr, stroke=0, fill=1)
    if frac > 0:
        c.setFillColor(color)
        extent = -360 * min(frac, 0.9999)
        c.wedge(x - rr, y - rr, x + rr, y + rr, 90, extent, stroke=0, fill=1)
    c.setFillColor(white)
    c.circle(x, y, rr * 0.62, stroke=0, fill=1)
    c.setFillGray(0.1)
    c.setFont(FONT, 15)
    c.drawCentredString(x, y - 1.0 * mm, center_big)
    c.setFont(FONT, 7.5)
    c.drawCentredString(x, y - 5.5 * mm, center_small)


def _chip(cv: _Canvas, x: float, y: float, level: str) -> None:
    c = cv.c
    c.setFillColor(LEVEL_COLOR[level])
    c.roundRect(x * mm, cv.y(y + 4.2), 13 * mm, 4.6 * mm, 1.2 * mm, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont(FONT, 7.5)
    c.drawCentredString((x + 6.5) * mm, cv.y(y + 3.0), level)


def _wrap(text: str, width_mm: float, size: float) -> list[str]:
    lines, cur = [], ""
    for ch in text:
        if pdfmetrics.stringWidth(cur + ch, FONT, size) > width_mm * mm:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + ([cur] if cur else [])


def draw_report(c: canvas.Canvas, person: Person, res: Result, cfg: dict) -> None:
    cv = _Canvas(c)
    rep = cfg.get("report", {})
    th = cfg.get("scale_thresholds", {})
    left, right = 16.0, L.PAGE_W - 16.0
    width = right - left

    # --- 見出し ---
    cv.text(left, 22, rep.get("title", "ストレスチェック結果のお知らせ"), size=17)
    cv.text(right - 58, 15, f"実施：{rep.get('exam_name', '')}", size=8)
    cv.text(right - 58, 20, f"発行日：{date.today():%Y年%m月%d日}", size=8)
    cv.line(left, 25.5, right, 25.5, width=1.2)
    cv.text(left, 32, f"ID：{person.id}", size=10)
    cv.text(left + 38, 32, f"氏名：{person.name}　様", size=12)
    cv.text(left + 115, 32, f"所属：{person.dept}", size=10)

    # --- 判定 ---
    y = 37
    color = HexColor("#C8553D") if res.high_stress else HexColor("#2E8B7A")
    c.setFillColor(color)
    c.roundRect(left * mm, cv.y(y + 19), width * mm, 19 * mm, 2 * mm, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont(FONT, 15)
    verdict = "あなたは「高ストレス者」に該当します" if res.high_stress else "あなたは「高ストレス者」に該当しません"
    c.drawString((left + 5) * mm, cv.y(y + 8.5), verdict)
    c.setFont(FONT, 8.5)
    c.drawString((left + 5) * mm, cv.y(y + 15), "判定理由：" + res.reason)
    y += 22
    if res.high_stress:
        for line in _wrap("医師による面接指導を受けることをお勧めします。面接指導を希望される場合は、次の申出先へお申し出ください。"
                          + rep.get("interview_request", ""), width, 9):
            cv.text(left, y + 3.5, line, size=9)
            y += 5
        y += 1

    # --- 領域ごとの円グラフ ---
    cv.text(left, y + 5, "■ 領域ごとの結果（円グラフ：ストレスの高さ。濃い部分が多いほどストレスが高い状態です）", size=9.5)
    y += 9
    domain_scores = {"A": res.a, "B": res.b, "C": res.c}
    col_w = width / 3
    for i, (key, (name, n)) in enumerate(DOMAINS.items()):
        score = domain_scores[key]
        frac = (score - n) / (3 * n)
        level = scale_level(score / n, th)
        cx = left + col_w * (i + 0.5)
        _donut(cv, cx, y + 21, 18, frac, LEVEL_COLOR[level], f"{round(frac * 100)}%",
               f"{score}点 / {4 * n}点")
        cv.text(cx, y + 45, name, size=10, center=True)
        _chip(cv, cx - 6.5, y + 47, level)
    y += 56

    # --- 尺度別の内訳（2列） ---
    cv.text(left, y + 4, "■ 項目別の内訳", size=9.5)
    cv.text(left + 30, y + 4, "（ストレスの高さを 1.0〜4.0 で表示。2.0以下=良好、3.0以上=要注意）", size=7.5, gray=0.35)
    y += 7
    scales = res.scales
    halves = (scales[:9], scales[9:])
    half_w = (width - 6) / 2
    dom_names = {k: v[0] for k, v in DOMAINS.items()} | {"D": "満足度"}
    for col, group in enumerate(halves):
        x0 = left + col * (half_w + 6)
        yy = y
        prev = None
        for dom, name, avg in group:
            if dom != prev:
                cv.rect(x0, yy, half_w, 5, fill_gray=0.9, stroke_gray=0.9)
                cv.text(x0 + 1.5, yy + 3.7, dom_names[dom], size=8)
                yy += 5.5
                prev = dom
            level = scale_level(avg, th)
            cv.text(x0 + 2, yy + 3.6, name, size=8.5)
            bar_x, bar_w = x0 + 44, half_w - 44 - 25
            cv.rect(bar_x, yy + 1.2, bar_w, 2.8, fill_gray=0.9, stroke_gray=0.9, line=0.1)
            if avg:
                c.setFillColor(LEVEL_COLOR[level])
                c.rect(bar_x * mm, cv.y(yy + 4.0), bar_w * (avg - 1) / 3 * mm, 2.8 * mm, stroke=0, fill=1)
            cv.text(bar_x + bar_w + 1.5, yy + 3.6, f"{avg:.1f}" if avg else "－", size=8)
            _chip(cv, x0 + half_w - 13, yy - 0.2, level)
            yy += 5.4
    y = max(y + 5.5 * 3 + 5.4 * 9, yy) + 4

    # --- アドバイス ---
    cv.text(left, y + 4, "■ セルフケアのためのアドバイス", size=9.5)
    y += 7
    tips = [ADVICE[k] for k in ("B", "A", "C") if scale_level(domain_scores[k] / DOMAINS[k][1], th) == "要注意"]
    for tip in tips or [GOOD]:
        lines = _wrap("・" + tip, width - 2, 8.5)
        for line in lines:
            cv.text(left + 1, y + 3.5, line, size=8.5)
            y += 4.6
        y += 0.8
    if res.missing:
        cv.text(left + 1, y + 3.5, f"※未回答の項目が{len(res.missing)}件あります（未回答の項目は点数に含めていません）。",
                size=8, gray=0.3)
        y += 5

    # --- フッター ---
    fy = L.PAGE_H - 30
    cv.line(left, fy, right, fy, gray=0.6, width=0.5)
    foot = [rep.get("contact", ""), rep.get("implementer", ""),
            "この結果は、あなたの同意なく会社（事業者）に提供されることはありません。",
            "※判定は厚生労働省「ストレスチェック制度実施マニュアル」の合計点数方式（評価基準の設定例）によります。"
            "項目別の3段階表示は本書独自の簡易区分です。"]
    yy = fy + 4.5
    for line in [l for l in foot if l]:
        for wrapped in _wrap(line, width, 7.5):
            cv.text(left, yy, wrapped, size=7.5, gray=0.25)
            yy += 4
    c.showPage()


def write_report(path: Path, person: Person, res: Result, cfg: dict) -> None:
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    c = canvas.Canvas(str(path), pagesize=(L.PAGE_W * mm, L.PAGE_H * mm))
    c.setTitle(f"ストレスチェック結果 {person.name}")
    draw_report(c, person, res, cfg)
    c.save()


def combine(paths: list[Path], dest: Path) -> None:
    writer = PdfWriter()
    for p in paths:
        writer.append(str(p))
    with dest.open("wb") as f:
        writer.write(f)
