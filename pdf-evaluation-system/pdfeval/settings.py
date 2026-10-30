"""アプリの画面から変更できる設定（結果通知書に載る相談先など）。

config.json を直接書き換えなくても済むように、項目ごとに読み書きする。
"""
from __future__ import annotations

import json
from pathlib import Path

# (キー, 画面に出す名前, 通知書での頭の文字, 入力の説明)
SETTINGS = (
    ("company_name", "会社名", "", "集団分析の見出しに載ります（例：株式会社〇〇）。空欄なら載りません"),
    ("group_label", "所属の呼び方", "", "集団分析での呼び方（例：所属、部署、事業所、課）"),
    ("contact", "相談先", "相談先：", "結果通知書の下に載る相談先の名前"),
    ("contact_detail", "連絡先（電話・メールなど）", "", "相談先・申出先の後ろに（ ）で載ります。空欄なら載りません"),
    ("interview_request", "医師面接の申出先", "申出先：", "高ストレス者の通知書に載る申出先"),
    ("implementer", "実施者", "実施者：", "例：〇〇クリニック 産業医 山田 一郎"),
    ("exam_name", "実施名", "", "例：2026年度 ストレスチェック"),
    ("title", "通知書のタイトル", "", "例：ストレスチェック結果のお知らせ"),
)
# 判定図の全国平均値・係数（数値。空欄＝未設定）
NUMERIC = (
    ("judgment_chart/quantity_control/mean_x", "判定図：仕事の量的負担の全国平均", ""),
    ("judgment_chart/quantity_control/mean_y", "判定図：仕事のコントロールの全国平均", ""),
    ("judgment_chart/quantity_control/coef_x", "判定図：仕事の量的負担の係数", "マニュアルの係数（プラス・マイナスに注意）"),
    ("judgment_chart/quantity_control/coef_y", "判定図：仕事のコントロールの係数", "マニュアルの係数（プラス・マイナスに注意）"),
    ("judgment_chart/support/mean_x", "判定図：上司の支援の全国平均", ""),
    ("judgment_chart/support/mean_y", "判定図：同僚の支援の全国平均", ""),
    ("judgment_chart/support/coef_x", "判定図：上司の支援の係数", "マニュアルの係数（プラス・マイナスに注意）"),
    ("judgment_chart/support/coef_y", "判定図：同僚の支援の係数", "マニュアルの係数（プラス・マイナスに注意）"),
)
_NUMERIC = {k: label for k, label, _ in NUMERIC}
_BY_KEY = {k: (label, prefix) for k, label, prefix, _ in SETTINGS}


def _get_path(cfg: dict, key: str):
    node = cfg
    for part in key.split("/"):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _strip(value: str, prefix: str) -> str:
    return value[len(prefix):] if prefix and value.startswith(prefix) else value


def list_settings(cfg: dict) -> list[tuple[str, str, str, str]]:
    """(キー, 名前, 現在の値（頭の文字なし）, 説明) の一覧。"""
    rep = cfg.get("report", {})
    rows = [(k, label, _strip(str(rep.get(k, "")), prefix), hint) for k, label, prefix, hint in SETTINGS]
    for k, label, hint in NUMERIC:
        v = _get_path(cfg, k)
        rows.append((k, label, "" if v is None else f"{v:g}",
                     (hint + "。" if hint else "") + "厚生労働省「仕事のストレス判定図」の値。空欄にすると未設定に戻ります"))
    return rows


def _save(config_path: Path, cfg: dict) -> None:
    tmp = config_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(config_path)                 # 途中で止まっても設定が壊れないよう、書き終えてから置き換える


def set_setting(config_path: Path, key: str, value: str) -> str:
    """1項目を変更して config.json に保存し、保存した値を返す。"""
    if key in _NUMERIC:
        text = value.strip().replace("−", "-").replace("ー", "-").replace("－", "-").replace("．", ".")
        text = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        if text:
            try:
                number = float(text)
            except ValueError:
                raise ValueError(f"数字で入力してください（例：7.5、-0.05）：{value}")
        else:
            number = None
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        node = cfg
        parts = key.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = number
        _save(config_path, cfg)
        return "（未設定）" if number is None else f"{number:g}"
    if key not in _BY_KEY:
        raise ValueError(f"変更できない項目です: {key}")
    _, prefix = _BY_KEY[key]
    value = " ".join(value.split())          # 改行や余分な空白を取り除く
    value = _strip(value, prefix)
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg.setdefault("report", {})[key] = (prefix + value) if (prefix and value) else value
    _save(config_path, cfg)
    return cfg["report"][key]


# ---------- 集団分析での所属のまとめ方（会社ごとに設定） ----------
def group_label(cfg: dict) -> str:
    return str(cfg.get("report", {}).get("group_label") or "所属").strip() or "所属"


def group_of(dept: str, cfg: dict) -> str:
    """名簿の所属を、集団分析で使う名前に置き換える（まとめ方が設定されていなければそのまま）。"""
    dept = (dept or "").strip()
    mapped = str(cfg.get("group_map", {}).get(dept, "")).strip()
    return mapped or dept or f"（{group_label(cfg)}なし）"


def set_group(config_path: Path, dept: str, value: str) -> str:
    """名簿の所属 dept を、集団分析で value にまとめる。value が空なら元に戻す。"""
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    gm = cfg.setdefault("group_map", {})
    value = " ".join(value.split())
    if value and value != dept:
        gm[dept] = value
    else:
        gm.pop(dept, None)
    _save(config_path, cfg)
    return value or dept
