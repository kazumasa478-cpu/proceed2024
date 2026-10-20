"""ストレスチェック調査票 読取・集計システム

  python -m pdfeval forms   名簿から本人用QRコード入り調査票PDFを作成
  python -m pdfeval run     inbox のスキャンPDFを読取 → 本人別フォルダに保存 → 集計Excel・結果通知書PDFを作成
  python -m pdfeval todo    要確認の人（読取に自信がない回答が残っている人）と読取不可のページを表示
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

from . import __version__
from .excel_report import write_summary
from .forms import Person, make_forms, read_roster
from .omr import read_pdf
from .organizer import load_answer_sheet, person_folder, safe_name, save_page_pdf, update_answers
from .questionnaire import score
from .report_pdf import combine, write_report

log = logging.getLogger("pdfeval")
BASE_DIR = Path(__file__).resolve().parent.parent


# 以前の版の見本の文言。設定がこのままなら新しい既定値に置き換える
_OLD_PLACEHOLDERS = {
    ("report", "contact"): "相談窓口：〇〇部 健康管理担当（内線 0000）",
    ("report", "interview_request"): "申出先：〇〇部 健康管理担当（内線 0000）",
}


def load_config(path: Path) -> dict:
    """設定を読む。新しい版で増えた項目は既定値で補い、旧版の見本の文言は新しい既定値に更新する。"""
    cfg = json.loads(path.read_text(encoding="utf-8"))
    default_path = BASE_DIR / "config.json"
    if not default_path.exists() or default_path.resolve() == path.resolve():
        return cfg
    defaults = json.loads(default_path.read_text(encoding="utf-8"))
    changed = False
    for section, values in defaults.items():
        if isinstance(values, dict):
            target = cfg.setdefault(section, {})
            for key, value in values.items():
                if key not in target or target[key] == _OLD_PLACEHOLDERS.get((section, key)):
                    target[key] = value
                    changed = True
        elif section not in cfg:
            cfg[section] = values
            changed = True
    if changed:
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cfg


def _roster(base: Path, cfg: dict) -> dict[str, Person]:
    path = base / cfg["roster"]
    if not path.exists():
        raise SystemExit(f"名簿が見つかりません: {path}（列: ID,氏名,所属 のCSV）")
    return {p.id: p for p in read_roster(path)}


def cmd_forms(base: Path, cfg: dict, separate: bool) -> int:
    people = list(_roster(base, cfg).values())
    for path in make_forms(people, base / cfg["forms_dir"], combined=not separate):
        log.info("調査票を作成: %s", path.relative_to(base))
    log.info("%d名分。両面印刷せず片面で印刷してください（1人2枚）。", len(people))
    return 0


def _unique(dest: Path) -> Path:
    n = 2
    candidate = dest
    while candidate.exists():
        candidate = dest.with_name(f"{dest.stem}_{n}{dest.suffix}")
        n += 1
    return candidate


def read_inbox(base: Path, cfg: dict, roster: dict[str, Person]) -> int:
    inbox, output = base / cfg["input_dir"], base / cfg["output_dir"]
    inbox.mkdir(parents=True, exist_ok=True)
    errors = 0
    for pdf in sorted(p for p in inbox.iterdir() if p.suffix.lower() == ".pdf"):
        try:
            pages = read_pdf(pdf, cfg.get("omr", {}))
        except Exception:
            log.exception("PDFを開けません: %s", pdf.name)
            errors += 1
            continue
        failed = False
        for pr in pages:
            if pr.error:
                dest = _unique(output / "_読取不可" / f"{pdf.stem}_p{pr.source_page}.pdf")
                save_page_pdf(pdf, pr.source_page, dest)
                log.warning("%s %dページ目: %s → %s", pdf.name, pr.source_page, pr.error, dest.relative_to(base))
                failed = True
                continue
            person = roster.get(pr.person_id) or Person(pr.person_id, "名簿なし")
            if pr.person_id not in roster:
                log.warning("ID %s が名簿にありません（%s %dページ目）", pr.person_id, pdf.name, pr.source_page)
            folder = person_folder(output, person)
            save_page_pdf(pdf, pr.source_page, folder / f"調査票スキャン_{pr.form_page}枚目.pdf")
            update_answers(folder, person, pr.items)
            todo = sum(i.status != "OK" for i in pr.items)
            log.info("読取: %s %dページ目 → %s（%d枚目, 要確認%d件）", pdf.name, pr.source_page,
                     folder.relative_to(base), pr.form_page, todo)
        if failed:
            errors += 1
        if cfg.get("move_after_processing", True):
            processed = base / cfg["processed_dir"]
            processed.mkdir(parents=True, exist_ok=True)
            shutil.move(str(pdf), _unique(processed / pdf.name))
    return errors


def _answer_sheets(output: Path, roster: dict[str, Person]):
    """output 内の本人フォルダごとに回答確認シートを読む。"""
    known = {person_folder(output, p).name: p for p in roster.values()}
    if not output.exists():
        return
    for folder in sorted(p for p in output.iterdir() if p.is_dir() and not p.name.startswith("_")):
        person = known.get(folder.name)
        if person is None:
            pid, _, name = folder.name.partition("_")
            person = Person(pid, name)
        sheet = load_answer_sheet(folder, person)
        if sheet is not None:
            yield folder, person, sheet


def list_todo(base: Path, cfg: dict, roster: dict[str, Person]) -> tuple[list[dict], list[Path]]:
    """要確認の人（回答確認シートに未確定の項目がある人）と、読取不可のページを返す。"""
    output = base / cfg["output_dir"]
    people = []
    for folder, person, sheet in _answer_sheets(output, roster):
        if sheet.unresolved:
            people.append({
                "person": person, "folder": folder,
                "items": [(i, sheet.statuses.get(i, "未読取")) for i in sheet.unresolved],
                "scans": sorted(folder.glob("調査票スキャン_*.pdf")),
            })
    unreadable = sorted((output / "_読取不可").glob("*.pdf")) if (output / "_読取不可").exists() else []
    return people, unreadable


def cmd_todo(base: Path, cfg: dict, tsv: bool) -> int:
    people, unreadable = list_todo(base, cfg, _roster(base, cfg))
    if tsv:   # Macアプリ用: 種別<TAB>開くファイル(|区切り)<TAB>表示名
        for p in people:
            counts: dict[str, int] = {}
            for _, st in p["items"]:
                counts[st] = counts.get(st, 0) + 1
            detail = "・".join(f"{k}{v}件" for k, v in counts.items())
            files = [p["folder"] / "回答確認.xlsx", *p["scans"]]
            print(f"PERSON\t{'|'.join(map(str, files))}\t{p['person'].id} {p['person'].name}（{detail}）")
        for f in unreadable:
            print(f"UNREADABLE\t{f}\t読取不可のページ：{f.name}")
        return 0
    if not people and not unreadable:
        print("要確認の人はいません。")
        return 0
    for p in people:
        items = "、".join(f"{i}（{st}）" for i, st in p["items"])
        print(f"■ {p['person'].id} {p['person'].name}：{len(p['items'])}件 … {items}")
        print(f"    修正するファイル: {p['folder'] / '回答確認.xlsx'}")
    for f in unreadable:
        print(f"■ 読取不可のページ: {f}")
    return 0


def build_outputs(base: Path, cfg: dict, roster: dict[str, Person]) -> None:
    output = base / cfg["output_dir"]
    results = []
    for folder, person, sheet in _answer_sheets(output, roster):
        for old in folder.glob("結果通知書_*.pdf"):
            old.unlink()
        if sheet.unresolved:
            log.warning("%s: 要確認 %d件のため結果通知書は未作成（%s を修正してください）",
                        person.name, len(sheet.unresolved), (folder / "回答確認.xlsx").relative_to(base))
            results.append((sheet, None))
            continue
        res = score(sheet.answers, cfg["criteria"])
        write_report(folder / f"結果通知書_{safe_name(person.id)}_{safe_name(person.name)}.pdf", person, res, cfg)
        results.append((sheet, res))

    summary = output / cfg["summary_excel"]
    write_summary(summary, results, cfg)
    reports = sorted(output.glob("*/結果通知書_*.pdf"))
    bundle = output / "結果通知書_印刷用_全員分.pdf"
    bundle.unlink(missing_ok=True)
    if reports:
        combine(reports, bundle)
    done = sum(r is not None for _, r in results)
    log.info("集計: %s（%d名中 %d名の結果確定）", summary.relative_to(base), len(results), done)
    if reports:
        log.info("印刷用: %s（%d枚）", bundle.relative_to(base), len(reports))
    missing = sorted(set(roster) - {s.person.id for s, _ in results})
    if missing:
        log.info("未提出: %d名（%s）", len(missing), ", ".join(missing[:20]) + (" …" if len(missing) > 20 else ""))


def cmd_run(base: Path, cfg: dict) -> int:
    roster = _roster(base, cfg)
    (base / cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
    errors = read_inbox(base, cfg, roster)
    build_outputs(base, cfg, roster)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdfeval", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", default="run", choices=["run", "forms", "todo"])
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config.json")
    parser.add_argument("--base", type=Path, default=None,
                        help="名簿・inbox・output を置く基準フォルダ (既定: 設定ファイルと同じ場所)")
    parser.add_argument("--separate", action="store_true", help="forms: 1人1ファイルで出力する")
    parser.add_argument("--tsv", action="store_true", help="todo: 機械向けのタブ区切りで出力する")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    base = (args.base or args.config.resolve().parent).resolve()
    (base / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(base / "logs" / "pdfeval.log", encoding="utf-8")],
        force=True,
    )
    cfg = load_config(args.config)
    if args.command == "forms":
        return cmd_forms(base, cfg, args.separate)
    if args.command == "todo":
        return cmd_todo(base, cfg, args.tsv)
    return cmd_run(base, cfg)
