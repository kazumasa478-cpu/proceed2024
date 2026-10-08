"""調査票のページレイアウト。印刷用PDFの作成とスキャン読取(OMR)の両方がこの座標を使う。

座標はすべて mm、原点はページ左上（y は下向き）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .questionnaire import SECTIONS

PAGE_W, PAGE_H = 210.0, 297.0
MARKER = 7.0                    # 四隅の位置合わせマーク（黒四角）の一辺
MARKER_INSET = 10.0             # 用紙端からマークまで
QR_BOX = (167.0, 18.0, 22.0)    # QRコード (x, y, 一辺)

LEFT = 18.0
NO_W = 8.0
OPT_X0 = 112.0                  # 選択肢列の左端
OPT_W = 20.0                    # 選択肢1列の幅
ROW_H = 6.0
SEC_TITLE_H = 7.0
COL_HEAD_H = 8.0
GROUP_H = 5.5
BOTTOM = 276.0
PAGE1_TOP = 66.0                # 1ページ目は氏名欄・説明の下から
PAGEN_TOP = 45.0


def marker_centers() -> list[tuple[float, float]]:
    """左上・右上・右下・左下 の順。"""
    c = MARKER_INSET + MARKER / 2
    return [(c, c), (PAGE_W - c, c), (PAGE_W - c, PAGE_H - c), (c, PAGE_H - c)]


def option_center_x(k: int) -> float:
    """選択肢 k(1〜4) の列中心 x。"""
    return OPT_X0 + OPT_W * (k - 0.5)


@dataclass
class Block:
    kind: str           # "section" / "colhead" / "group" / "row"
    y: float            # 上端
    h: float
    section: str
    text: str = ""
    item: str = ""      # kind == "row" のとき "A1" など
    no: int = 0


@dataclass
class Page:
    number: int
    blocks: list[Block] = field(default_factory=list)

    @property
    def rows(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "row"]


def build_layout() -> list[Page]:
    pages = [Page(1)]
    y = PAGE1_TOP

    def ensure(height: float) -> None:
        nonlocal y
        if y + height > BOTTOM:
            pages.append(Page(len(pages) + 1))
            y = PAGEN_TOP

    def add(block_kind: str, h: float, **kw) -> None:
        nonlocal y
        pages[-1].blocks.append(Block(block_kind, y, h, **kw))
        y += h

    for sec in SECTIONS:
        groups = dict(sec.groups)
        # セクション見出し＋列見出し＋最初の1行は同じページにまとめる
        first_extra = GROUP_H if 1 in groups else 0
        ensure(SEC_TITLE_H + COL_HEAD_H + first_extra + ROW_H)
        add("section", SEC_TITLE_H, section=sec.key, text=sec.title)
        add("colhead", COL_HEAD_H, section=sec.key)
        for no, text in enumerate(sec.items, start=1):
            if no in groups:
                ensure(GROUP_H + ROW_H)
                add("group", GROUP_H, section=sec.key, text=groups[no])
            elif y + ROW_H > BOTTOM:
                ensure(ROW_H)
                add("colhead", COL_HEAD_H, section=sec.key)   # 改ページ後も列見出しを出す
            add("row", ROW_H, section=sec.key, text=text, item=f"{sec.key}{no}", no=no)
    return pages


LAYOUT = build_layout()
