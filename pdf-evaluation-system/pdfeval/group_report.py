"""全員の結果から「集団分析結果」（A4・1枚）を作成する。

個人が特定されないよう、人数が少ない集団（既定：10人未満）の数値は表示しない。
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from statistics import mean

from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from . import layout as L
from .forms import FONT, _Canvas
from .questionnaire import DOMAINS, SCALES, Result, scale_level
from .report_pdf import LEVEL_COLOR, _chip, _wrap

HIGH = HexColor("#C8553D")
OK = HexColor("#2E8B7A")
MID = HexColor("#C9A227")
GRAY = HexColor("#BFBFBF")
TILE = HexColor("#F2F4F5")

# 仕事のストレス判定図で使う4尺度（各3項目・3〜12点。高いほどその要素が多い）
JUDGE_SCALES = (
    ("仕事の量的負担", ("A1", "A2", "A3"), "高いほど負担が大きい"),
    ("仕事のコントロール", ("A8", "A9", "A10"), "高いほど裁量がある"),
    ("上司の支援", ("C1", "C4", "C7"), "高いほど支援がある"),
    ("同僚の支援", ("C2", "C5", "C8"), "高いほど支援がある"),
)


def _judge_score(answers: dict, items: tuple[str, ...]) -> int | None:
    """回答（そうだ=1 … ちがう=4 / 非常に=1 … 全くない=4）を「多いほど高い」3〜12点にする。"""
    vals = [answers.get(i) for i in items]
    if any(v is None for v in vals):
        return None
    return sum(5 - v for v in vals)


def _pie(cv: _Canvas, cx: float, cy: float, r: float, parts: list[tuple[str, int, object]], title: str) -> None:
    c = cv.c
    total = sum(n for _, n, _ in parts)
    cv.text(cx, cy - r - 4, title, size=9.5, center=True)
    x, y, rr = cx * mm, cv.y(cy), r * mm
    if total == 0:
        c.setFillColor(GRAY)
        c.circle(x, y, rr, stroke=0, fill=1)
    else:
        start = 90.0
        for _, n, color in parts:
            if n == 0:
                continue
            extent = -360.0 * n / total
            c.setFillColor(color)
            if n == total:
                c.circle(x, y, rr, stroke=0, fill=1)
            else:
                c.wedge(x - rr, y - rr, x + rr, y + rr, start, extent, stroke=0, fill=1)
            start += extent
    # 凡例
    ly = cy + r + 5
    for label, n, color in parts:
        pct = f"{n / total * 100:.0f}%" if total else "－"
        c.setFillColor(color)
        c.rect((cx - r) * mm, cv.y(ly - 0.3), 2.6 * mm, 2.6 * mm, stroke=0, fill=1)
        cv.text(cx - r + 3.6, ly, f"{label}　{n}名（{pct}）", size=7.5)
        ly += 4


def _tile(cv: _Canvas, x: float, y: float, w: float, h: float, label: str, value: str, sub: str = "",
          color=None) -> None:
    c = cv.c
    c.setFillColor(TILE)
    c.roundRect(x * mm, cv.y(y + h), w * mm, h * mm, 1.5 * mm, stroke=0, fill=1)
    cv.text(x + 3, y + 5, label, size=8, gray=0.35)
    c.setFillColor(color or HexColor("#222222"))
    c.setFont(FONT, 16)
    c.drawString((x + 3) * mm, cv.y(y + 13), value)
    if sub:
        cv.text(x + 3, y + h - 2.5, sub, size=7, gray=0.4)


def write_group_report(path: Path, results: list[tuple[object, Result | None]], roster_count: int,
                       cfg: dict) -> Path:
    """results: [(回答シート, 採点結果 or None)]。結果が確定した人だけを分析する。"""
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    rep = cfg.get("report", {})
    th = cfg.get("scale_thresholds", {})
    min_n = int(cfg.get("group_min_size", 10))
    done = [(s, r) for s, r in results if r is not None]
    n = len(done)
    high = sum(r.high_stress for _, r in done)

    c = canvas.Canvas(str(path), pagesize=(L.PAGE_W * mm, L.PAGE_H * mm))
    c.setTitle("ストレスチェック 集団分析結果")
    cv = _Canvas(c)
    left, right = 14.0, L.PAGE_W - 14.0
    width = right - left

    # --- 見出し ---
    cv.text(left, 20, "ストレスチェック 集団分析結果", size=17)
    cv.text(right - 62, 14, f"実施：{rep.get('exam_name', '')}", size=8)
    cv.text(right - 62, 19, f"作成日：{date.today():%Y年%m月%d日}", size=8)
    cv.line(left, 23, right, 23, width=1.2)
    y = 26.0
    if n < min_n:
        c.setFillColor(HIGH)
        c.roundRect(left * mm, cv.y(y + 7), width * mm, 7 * mm, 1.2 * mm, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont(FONT, 8.5)
        c.drawString((left + 2.5) * mm, cv.y(y + 4.8),
                     f"結果が確定した受検者が{n}名（{min_n}名未満）です。個人が特定されるおそれがあるため、取り扱いに注意してください。")
        y += 9

    # --- 概要（数字のタイル） ---
    tw = (width - 9) / 4
    rate = f"{n / roster_count * 100:.0f}%" if roster_count else "－"
    pending = len(results) - n
    tiles = [
        ("受検者数（結果確定）", f"{n}名", f"名簿 {roster_count}名" + (f"・要確認 {pending}名" if pending else "")),
        ("受検率", rate, "結果確定者 ÷ 名簿の人数"),
        ("高ストレス者", f"{high}名", f"受検者の {high / n * 100:.1f}%" if n else "－", HIGH if high else None),
        ("心身のストレス反応（平均）", f"{mean(r.b for _, r in done):.1f}点" if n else "－", "29〜116点（高いほどストレス大）"),
    ]
    for i, t in enumerate(tiles):
        _tile(cv, left + i * (tw + 3), y, tw, 19, *t)
    y += 24

    # --- 円グラフ（判定・ストレス反応の分布）と、領域ごとの平均 ---
    b_levels = Counter(scale_level(r.b / DOMAINS["B"][1], th) for _, r in done)
    _pie(cv, left + 22, y + 22, 15, [("高ストレス者", high, HIGH), ("該当しない", n - high, OK)], "高ストレス者の割合")
    _pie(cv, left + 72, y + 22, 15, [("良好", b_levels["良好"], OK), ("ふつう", b_levels["ふつう"], MID),
                                       ("要注意", b_levels["要注意"], HIGH)], "心身のストレス反応の分布")
    bx, bw = left + 108, width - 108
    cv.text(bx, y + 4, "領域ごとの平均（ストレスの高さ）", size=9.5)
    yy = y + 9
    for key, (name, items_n) in DOMAINS.items():
        avg = mean(getattr(r, key.lower()) for _, r in done) if n else 0
        frac = (avg - items_n) / (3 * items_n) if n else 0
        level = scale_level(avg / items_n, th) if n else "－"
        cv.text(bx, yy + 3.5, name, size=8.5)
        bar_w = bw - 34 - 26
        cv.rect(bx + 34, yy + 0.8, bar_w, 3.6, fill_gray=0.9, stroke_gray=0.9, line=0.1)
        if n:
            c.setFillColor(LEVEL_COLOR[level])
            c.rect((bx + 34) * mm, cv.y(yy + 4.4), bar_w * frac * mm, 3.6 * mm, stroke=0, fill=1)
        cv.text(bx + 34 + bar_w + 1.5, yy + 3.5, f"{frac * 100:.0f}%" if n else "－", size=8)
        _chip(cv, bx + bw - 13, yy - 0.2, level)
        yy += 7.5
    cv.text(bx, yy + 2.5, "0%＝最もストレスが低い、100%＝最も高い", size=6.5, gray=0.4)
    y += 54

    # --- 項目別（19尺度）の平均 ---
    cv.text(left, y + 4, "■ 項目別の平均（ストレスの高さ 1.0〜4.0。2.0以下=良好、3.0以上=要注意）", size=9.5)
    y += 7
    scale_avgs = []
    for idx, (dom, name, _) in enumerate(SCALES):
        vals = [r.scales[idx][2] for _, r in done if r.scales[idx][2]]
        scale_avgs.append((dom, name, round(mean(vals), 2) if vals else 0.0))
    half_w = (width - 6) / 2
    dom_names = {k: v[0] for k, v in DOMAINS.items()} | {"D": "満足度"}
    bottom = y
    for col, group in enumerate((scale_avgs[:9], scale_avgs[9:])):
        x0, yy, prev = left + col * (half_w + 6), y, None
        for dom, name, avg in group:
            if dom != prev:
                cv.rect(x0, yy, half_w, 4.6, fill_gray=0.9, stroke_gray=0.9)
                cv.text(x0 + 1.5, yy + 3.4, dom_names[dom], size=7.5)
                yy += 5.0
                prev = dom
            level = scale_level(avg, th)
            cv.text(x0 + 2, yy + 3.3, name, size=8)
            bar_x, bar_w = x0 + 44, half_w - 44 - 25
            cv.rect(bar_x, yy + 1.0, bar_w, 2.8, fill_gray=0.9, stroke_gray=0.9, line=0.1)
            if avg:
                c.setFillColor(LEVEL_COLOR[level])
                c.rect(bar_x * mm, cv.y(yy + 3.8), bar_w * (avg - 1) / 3 * mm, 2.8 * mm, stroke=0, fill=1)
            cv.text(bar_x + bar_w + 1.5, yy + 3.3, f"{avg:.1f}" if avg else "－", size=7.5)
            _chip(cv, x0 + half_w - 13, yy - 0.4, level)
            yy += 4.9
        bottom = max(bottom, yy)
    y = bottom + 3

    # --- 仕事のストレス判定図の4尺度 ---
    cv.text(left, y + 4, "■ 仕事のストレス判定図の4尺度（集団の平均点。各3〜12点）", size=9.5)
    y += 6.5
    jw = width / 4
    for i, (name, items, hint) in enumerate(JUDGE_SCALES):
        vals = [v for s, _ in done if (v := _judge_score(s.answers, items)) is not None]
        x0 = left + i * jw
        c.setFillColor(TILE)
        c.roundRect((x0 + 0.5) * mm, cv.y(y + 13), (jw - 1) * mm, 13 * mm, 1.2 * mm, stroke=0, fill=1)
        cv.text(x0 + 2.5, y + 4.2, name, size=8)
        c.setFillColorRGB(0.13, 0.13, 0.13)
        c.setFont(FONT, 13)
        c.drawString((x0 + 2.5) * mm, cv.y(y + 10.5), f"{mean(vals):.1f}点" if vals else "－")
        cv.text(x0 + 21, y + 10.3, hint, size=6.5, gray=0.4)
    y += 16

    # --- 所属別 ---
    cv.text(left, y + 4, f"■ 所属別（{min_n}名未満の所属は、個人が特定されないよう数値を表示しません）", size=9.5)
    y += 6.5
    by_dept: dict[str, list[Result]] = {}
    for s, r in done:
        by_dept.setdefault(s.person.dept or "（所属なし）", []).append(r)
    cols = [("所属", 44), ("人数", 14), ("高ストレス者", 22), ("仕事の\nストレス要因", 24),
            ("心身の\nストレス反応", 24), ("周囲の\nサポート", 22), ("最も高い項目", width - 150)]
    xs = [left]
    for _, w in cols:
        xs.append(xs[-1] + w)
    cv.rect(left, y, width, 6.5, fill_gray=0.88, stroke_gray=0.88)
    for (label, _), x0 in zip(cols, xs):
        lines = label.split("\n")
        for k, line in enumerate(lines):
            cv.text(x0 + 1.5, y + (3.0 if len(lines) == 2 else 4.4) + k * 3.0, line, size=6.8)
    y += 6.5
    rows = sorted(by_dept.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    max_rows = 6
    for dept, rs in rows[:max_rows]:
        cv.text(xs[0] + 1.5, y + 3.6, dept[:16], size=7.5)
        cv.text(xs[1] + 1.5, y + 3.6, f"{len(rs)}名", size=7.5)
        if len(rs) < min_n:
            cv.text(xs[2] + 1.5, y + 3.6, "人数が少ないため非表示", size=7, gray=0.45)
        else:
            h = sum(r.high_stress for r in rs)
            cv.text(xs[2] + 1.5, y + 3.6, f"{h}名（{h / len(rs) * 100:.0f}%）", size=7.5)
            for k, key in enumerate(("a", "b", "c")):
                cv.text(xs[3 + k] + 1.5, y + 3.6, f"{mean(getattr(r, key) for r in rs):.1f}点", size=7.5)
            top = max(range(len(SCALES)),
                      key=lambda i: mean(r.scales[i][2] for r in rs) if SCALES[i][0] != "D" else 0)
            cv.text(xs[6] + 1.5, y + 3.6, SCALES[top][1], size=7.5)
        cv.line(left, y + 5.2, right, y + 5.2, gray=0.85, width=0.3)
        y += 5.2
    if len(rows) > max_rows:
        cv.text(left + 1.5, y + 3.4, f"ほか {len(rows) - max_rows} 所属は「ストレスチェック集計.xlsx」を参照してください。", size=7, gray=0.4)
        y += 4.6
    if not rows:
        cv.text(left + 1.5, y + 3.6, "結果が確定した受検者がいません。", size=7.5, gray=0.45)
        y += 5.2
    y += 2

    # --- まとめ（自動で作る文） ---
    cv.text(left, y + 4, "■ まとめ", size=9.5)
    y += 6.5
    ranked = sorted((a for a in scale_avgs if a[2] and a[0] != "D"), key=lambda a: a[2], reverse=True)
    if ranked:
        worst = [f"{name}（{avg:.1f}）" for _, name, avg in ranked[:3]]
        best = [f"{name}（{avg:.1f}）" for _, name, avg in ranked[-2:][::-1]]
        lines = [
            f"・ストレスが高めの項目：{'、'.join(worst)}。職場環境改善では、これらへの対策を優先して検討することをお勧めします。",
            f"・比較的良好な項目：{'、'.join(best)}。職場の強みとして維持してください。",
            f"・高ストレス者は{high}名（{high / n * 100:.1f}%）でした。" + (
                "医師による面接指導の申出がしやすい環境づくりを進めてください。" if high else ""),
        ]
    else:
        lines = ["・結果が確定した受検者がいないため、分析できません。"]
    for line in lines:
        for wrapped in _wrap(line, width - 2, 8):
            cv.text(left + 1, y + 3.3, wrapped, size=8)
            y += 4.3

    # --- 注意書き ---
    fy = L.PAGE_H - 17
    cv.line(left, fy, right, fy, gray=0.6, width=0.5)
    notes = [
        "※本書は集団の結果をまとめたもので、個人の結果は含みません。個人の結果を本人の同意なく事業者に提供することはできません。",
        "※項目別の3段階表示は本書独自の簡易区分です。判定図の健康リスク（全国平均=100）は、厚生労働省「仕事のストレス判定図」マニュアルの計算式で実施者が算出してください。",
        rep.get("implementer", ""),
    ]
    yy = fy + 4
    for note in [x for x in notes if x]:
        for wrapped in _wrap(note, width, 6.8):
            cv.text(left, yy, wrapped, size=6.8, gray=0.3)
            yy += 3.4
    c.showPage()
    c.save()
    return path
