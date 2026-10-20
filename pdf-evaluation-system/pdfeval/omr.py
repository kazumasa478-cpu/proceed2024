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
    style: str = ""                   # "M"=マークシート形式 / "C"=旧形式（○で囲む）
    items: list[ItemRead] = field(default_factory=list)
    error: str = ""


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _image_pages(path) -> list[np.ndarray]:
    """JPEG/PNG/TIFF（複数ページTIFFも可）をグレースケール画像にする。"""
    from PIL import Image, ImageOps, ImageSequence
    pages = []
    with Image.open(path) as im:
        for frame in ImageSequence.Iterator(im):
            g = ImageOps.exif_transpose(frame.copy()).convert("L")
            if max(g.size) > 3600:                      # スマホ写真などは縮小して処理を速くする
                g.thumbnail((3600, 3600))
            pages.append(np.array(g))
    return pages


def render_pages(pdf_path) -> list[np.ndarray]:
    """PDF（または画像）の各ページをグレースケール画像にする。"""
    if str(pdf_path).lower().endswith(tuple(IMAGE_SUFFIXES)):
        return _image_pages(pdf_path)
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


def _judge(item: str, scores: list[float], min_ink: float, sure_ink: float, ratio: float) -> ItemRead:
    order = sorted(range(4), key=lambda i: scores[i], reverse=True)
    top, second = scores[order[0]], scores[order[1]]
    if top < min_ink:
        return ItemRead(item, None, "未記入", scores)
    if second >= top * ratio and second >= min_ink:
        return ItemRead(item, None, "複数", scores)
    return ItemRead(item, order[0] + 1, "OK" if top >= sure_ink else "要確認", scores)


def _read_bubbles(img: np.ndarray, page: L.Page, cfg: dict) -> list[ItemRead]:
    """マークシート形式：各楕円の内側がどれだけ塗られているか（%）で判定する。

    印刷の線と数字は薄い灰色なので、記入したインクだけが数えられる。
    塗りつぶしは60〜100%、空欄は数%になり、差がはっきり出る。
    """
    ink = img < cfg.get("bubble_ink_threshold", 150)
    min_ink = cfg.get("bubble_min_percent", 20.0)
    sure_ink = cfg.get("bubble_sure_percent", 35.0)
    ratio = cfg.get("ambiguous_ratio", 0.5)
    rx, ry = L.BUBBLE_W / 2 * 0.8 * PX, L.BUBBLE_H / 2 * 0.75 * PX   # 線を避けて内側だけを見る
    w, h = int(rx) + 1, int(ry) + 1
    yy, xx = np.mgrid[-h:h + 1, -w:w + 1]
    mask = (xx / rx) ** 2 + (yy / ry) ** 2 <= 1
    results = []
    for row in page.rows:
        cy = int(round((row.y + row.h / 2) * PX))
        raw = []
        for k in range(1, 5):
            cx = int(round(L.option_center_x(k) * PX))
            region = ink[cy - h:cy + h + 1, cx - w:cx + w + 1]
            raw.append(100.0 * region[mask].mean())
        base = min(raw)
        results.append(_judge(row.item, [round(r - base, 1) for r in raw], min_ink, sure_ink, ratio))
    return results


def _read_items(img: np.ndarray, page: L.Page, cfg: dict) -> list[ItemRead]:
    """旧形式（数字を○で囲む）の読取。"""
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
        results.append(_judge(row.item, scores, min_ink, sure_ink, ratio))
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
        result.person_id, result.form_page, result.style = qr
        page = next((p for p in L.LAYOUT if p.number == result.form_page), None)
        if page is None:
            result.error = f"ページ番号 {result.form_page} が不正です"
            return result
        reader = _read_bubbles if result.style == "M" else _read_items
        result.items = reader(img, page, cfg)
        return result
    result.error = ("QRコードを読み取れません（QRの汚れ・かすれ、または本システムで作成した調査票ではない可能性）"
                    if markers_found else
                    "四隅の黒い四角（位置合わせマーク）が見つかりません（用紙の端が切れている、"
                    "または本システムで作成した調査票ではない可能性）")
    return result


def read_pdf(pdf_path, cfg: dict) -> list[PageRead]:
    return [read_page(g, i, cfg) for i, g in enumerate(render_pages(pdf_path), start=1)]
