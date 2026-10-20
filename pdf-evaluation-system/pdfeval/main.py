"""ストレスチェック調査票 読取・集計システム

  python -m pdfeval forms   名簿から本人用QRコード入り調査票PDFを作成
  python -m pdfeval run     inbox のスキャンPDFを読取 → 本人別フォルダに保存 → 集計Excel・結果通知書PDFを作成
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
    "contact": "相談窓口：〇〇部 健康管理担当（内線 0000）",
    "interview_request": "申出先：〇〇部 健康管理担当（内線 0000）",
}


def load_config(path: Path) -> dict:
    """設定を読む。新しい版で増えた項目は既定値で補い、旧版の見本の文言は新しい既定値に更新する。"""
    cfg = json.loads(path.read_text(encoding="utf-8"))
    default_path = BASE_DIR / "config.json"
    if not default_path.exists() or default_path.resolve() == path.resolve():
        return cfg
    defaults = json.loads(default_path.read_text(encoding="utf-8")).get("report", {})
    rep = cfg.setdefault("report", {})
    changed = False
    for key, value in defaults.items():
        if key not in rep or rep[key] == _OLD_PLACEHOLDERS.get(key):
            rep[key] = value
            changed = True
    if changed:
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cfg


def cmd_settings(config_path: Path, cfg: dict, action: str, key: str, value: str) -> int:
    from .settings import list_settings, set_setting
    if action == "list":      # キー␟名前␟現在の値␟説明（Macアプリ用。空欄があっても列がずれない区切り文字）
        for k, label, current, hint in list_settings(cfg):
            print("\x1f".join((k, label, current, hint)))
        return 0
    try:
        saved = set_setting(config_path, key, value)
    except ValueError as e:
        print(e)
        return 1
    print(f"保存しました：{saved or '（空欄）'}")
    return 0


def cmd_preview(base: Path, cfg: dict) -> int:
    """今の設定で、架空の人の結果通知書（見本）を作る。"""
    from .questionnaire import ALL_ITEMS, REVERSED
    answers = {i: (1 if i in REVERSED else 4) if i[0] == "B" else 2 for i in ALL_ITEMS}   # 高ストレス者の例
    res = score(answers, cfg["criteria"])
    out = base / "見本_結果通知書.pdf"
    write_report(out, Person("E0000", "見本 太郎", "見本部署"), res, cfg)
    print(out)
    return 0


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


def build_outputs(base: Path, cfg: dict, roster: dict[str, Person]) -> None:
    output = base / cfg["output_dir"]
    results = []
    known = {person_folder(output, p).name: p for p in roster.values()}
    for folder in sorted(p for p in output.iterdir() if p.is_dir() and not p.name.startswith("_")):
        person = known.get(folder.name)
        if person is None:
            pid, _, name = folder.name.partition("_")
            person = Person(pid, name)
        sheet = load_answer_sheet(folder, person)
        if sheet is None:
            continue
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
    parser.add_argument("command", nargs="?", default="run", choices=["run", "forms", "settings-list", "settings-set", "preview-report"])
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config.json")
    parser.add_argument("--base", type=Path, default=None,
                        help="名簿・inbox・output を置く基準フォルダ (既定: 設定ファイルと同じ場所)")
    parser.add_argument("--separate", action="store_true", help="forms: 1人1ファイルで出力する")
    parser.add_argument("--key", default="", help="settings-set: 変更する項目")
    parser.add_argument("--value", default="", help="settings-set: 新しい値")
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
    if args.command.startswith("settings-"):
        return cmd_settings(args.config, cfg, args.command[len("settings-"):], args.key, args.value)
    if args.command == "preview-report":
        return cmd_preview(base, cfg)
    return cmd_run(base, cfg)
