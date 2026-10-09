"""スキャンした調査票PDFから、QRコード（本人特定）と○の位置（回答）を読み取る。"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
import pypdfium2 as pdfium

from . import layout as L
from .forms import parse_qr

DPI = 200
PX = DPI / 25.4          # 1mm あたりのピクセル数


@dataclass
class ItemRead:
    item: str
    answer: int | None
    status: str           # "OK" / "未記入" / "複数" / "要確認"
    scores: list[float]   # 各選択肢のインク量（%）


@dataclass
class PageRead:
    source_page: int                  # 元PDF内のページ番号(1始まり)
    person_id: str | None = None
    form_page: int | None = None
    items: list[ItemRead] = field(default_factory=list)
    error: str = ""


def render_pages(pdf_path) -> list[np.ndarray]:
    """PDFの各ページをグレースケール画像にする。"""
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        return [np.array(page.render(scale=DPI / 72, grayscale=True).to_pil().convert("L"))
                for page in doc]
    finally:
        doc.close()


def _flatten_lighting(gray: np.ndarray) -> np.ndarray:
    """影や明るさのムラを取り除き、紙の白さをそろえる。"""
    k = max(15, int(min(gray.shape) / 18)) | 1          # 位置合わせマークより大きい窓
    bg = cv2.dilate(gray, np.ones((k, k), np.uint8))
    bg = cv2.GaussianBlur(bg, (0, 0), k / 3)
    out = gray.astype(np.float32) / np.maximum(bg.astype(np.float32), 1) * 255
    return np.clip(out, 0, 255).astype(np.uint8)


def _find_markers(gray: np.ndarray) -> np.ndarray | None:
    """四隅の黒四角の中心を探す（左上・右上・右下・左下）。"""
    h, w = gray.shape
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    expected = (L.MARKER * PX * w / (L.PAGE_W * PX)) ** 2   # 用紙全体が写っている前提での面積
    cw, ch = int(w * 0.22), int(h * 0.16)
    corners = [(0, 0), (w - cw, 0), (w - cw, h - ch), (0, h - ch)]
    targets = [(0, 0), (w, 0), (w, h), (0, h)]
    found = []
    for (x0, y0), (tx, ty) in zip(corners, targets):
        roi = binary[y0:y0 + ch, x0:x0 + cw]
        contours, _ = cv2.findContours(roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (expected * 0.4 < area < expected * 2.5):
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            if not (0.7 < bw / bh < 1.4) or area / (bw * bh) < 0.75:
                continue
            cx, cy = x0 + x + bw / 2, y0 + y + bh / 2
            dist = (cx - tx) ** 2 + (cy - ty) ** 2
            if best is None or dist < best[0]:
                best = (dist, cx, cy)
        if best is None:
            return None
        found.append(best[1:])
    return np.array(found, dtype=np.float32)


def _warp(gray: np.ndarray) -> np.ndarray | None:
    """マーク位置を基準に、用紙を正規の座標（200dpi・A4）に補正する。"""
    src = _find_markers(gray)
    if src is None:
        return None
    dst = np.array([(x * PX, y * PX) for x, y in L.marker_centers()], dtype=np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    size = (round(L.PAGE_W * PX), round(L.PAGE_H * PX))
    return cv2.warpPerspective(gray, m, size, flags=cv2.INTER_LINEAR, borderValue=255)


def _read_qr(img: np.ndarray) -> tuple[str, int] | None:
    """補正後の画像の右上（QRコードの正しい位置）だけを読む。

    位置を確かめずに読むと、上下逆さの用紙でもQRが読めてしまい、回答を取り違えるため。
    """
    x, y, s = L.QR_BOX
    pad = 6
    crop = img[int((y - pad) * PX):int((y + s + pad) * PX), int((x - pad) * PX):int((x + s + pad) * PX)]
    detector = cv2.QRCodeDetector()
    for candidate in (crop, cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)):
        text, _, _ = detector.detectAndDecode(candidate)
        if text and (parsed := parse_qr(text)):
            return parsed
    return None


def _read_items(img: np.ndarray, page: L.Page, cfg: dict) -> list[ItemRead]:
    ink = (img < cfg.get("ink_threshold", 110)).astype(np.uint8)
    min_ink = cfg.get("min_mark_percent", 2.0)
    sure_ink = cfg.get("sure_mark_percent", 3.0)
    ratio = cfg.get("ambiguous_ratio", 0.5)
    half_w = (L.OPT_W / 2 - 0.8) * PX
    results = []
    for row in page.rows:
        y0, y1 = int((row.y + 0.3) * PX), int((row.y + row.h - 0.3) * PX)
        raw = []
        for k in range(1, 5):
            cx = L.option_center_x(k) * PX
            region = ink[y0:y1, int(cx - half_w):int(cx + half_w)]
            raw.append(100.0 * region.mean())
        base = min(raw)                       # 印刷された数字の分を差し引く
        scores = [round(r - base, 2) for r in raw]
        order = sorted(range(4), key=lambda i: scores[i], reverse=True)
        top, second = scores[order[0]], scores[order[1]]
        if top < min_ink:
            results.append(ItemRead(row.item, None, "未記入", scores))
        elif second >= top * ratio and second >= min_ink:
            results.append(ItemRead(row.item, None, "複数", scores))
        else:
            status = "OK" if top >= sure_ink else "要確認"
            results.append(ItemRead(row.item, order[0] + 1, status, scores))
    return results


def read_page(gray: np.ndarray, source_page: int, cfg: dict) -> PageRead:
    result = PageRead(source_page)
    gray = _flatten_lighting(gray)
    # 上下逆さ・横向きのスキャンにも対応（QRが正しい位置にある向きを採用する）
    rotations = (gray, cv2.rotate(gray, cv2.ROTATE_180),
                 cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE), cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE))
    markers_found = False
    for rotated in rotations:
        img = _warp(rotated)
        if img is None:
            continue
        markers_found = True
        qr = _read_qr(img)
        if qr is None:
            continue
        result.person_id, result.form_page = qr
        page = next((p for p in L.LAYOUT if p.number == result.form_page), None)
        if page is None:
            result.error = f"ページ番号 {result.form_page} が不正です"
            return result
        result.items = _read_items(img, page, cfg)
        return result
    result.error = ("QRコードを読み取れません（QRの汚れ・かすれ、または本システムで作成した調査票ではない可能性）"
                    if markers_found else
                    "四隅の黒い四角（位置合わせマーク）が見つかりません（用紙の端が切れている、"
                    "または本システムで作成した調査票ではない可能性）")
    return result


def read_pdf(pdf_path, cfg: dict) -> list[PageRead]:
    return [read_page(g, i, cfg) for i, g in enumerate(render_pages(pdf_path), start=1)]
