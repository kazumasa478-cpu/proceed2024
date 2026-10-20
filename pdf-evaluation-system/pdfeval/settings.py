"""アプリの画面から変更できる設定（結果通知書に載る相談先など）。

config.json を直接書き換えなくても済むように、項目ごとに読み書きする。
"""
from __future__ import annotations

import json
from pathlib import Path

# (キー, 画面に出す名前, 通知書での頭の文字, 入力の説明)
SETTINGS = (
    ("contact", "相談先", "相談先：", "結果通知書の下に載る相談先の名前"),
    ("contact_detail", "連絡先（電話・メールなど）", "", "相談先・申出先の後ろに（ ）で載ります。空欄なら載りません"),
    ("interview_request", "医師面接の申出先", "申出先：", "高ストレス者の通知書に載る申出先"),
    ("implementer", "実施者", "実施者：", "例：〇〇クリニック 産業医 山田 一郎"),
    ("exam_name", "実施名", "", "例：2026年度 ストレスチェック"),
    ("title", "通知書のタイトル", "", "例：ストレスチェック結果のお知らせ"),
)
_BY_KEY = {k: (label, prefix) for k, label, prefix, _ in SETTINGS}


def _strip(value: str, prefix: str) -> str:
    return value[len(prefix):] if prefix and value.startswith(prefix) else value


def list_settings(cfg: dict) -> list[tuple[str, str, str, str]]:
    """(キー, 名前, 現在の値（頭の文字なし）, 説明) の一覧。"""
    rep = cfg.get("report", {})
    return [(k, label, _strip(str(rep.get(k, "")), prefix), hint) for k, label, prefix, hint in SETTINGS]


def set_setting(config_path: Path, key: str, value: str) -> str:
    """1項目を変更して config.json に保存し、保存した値を返す。"""
    if key not in _BY_KEY:
        raise ValueError(f"変更できない項目です: {key}")
    _, prefix = _BY_KEY[key]
    value = " ".join(value.split())          # 改行や余分な空白を取り除く
    value = _strip(value, prefix)
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg.setdefault("report", {})[key] = (prefix + value) if (prefix and value) else value
    tmp = config_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(config_path)                 # 途中で止まっても設定が壊れないよう、書き終えてから置き換える
    return cfg["report"][key]
