"""職業性ストレス簡易調査票（57項目）の設問・尺度・採点定義。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    key: str            # "A" など
    title: str
    options: tuple[str, str, str, str]
    items: tuple[str, ...]
    groups: tuple[tuple[int, str], ...] = ()   # (この番号の前に入れる小見出し)


SECTIONS = (
    Section("A", "Ａ　あなたの仕事についてうかがいます",
            ("そうだ", "まあそうだ", "ややちがう", "ちがう"),
            ("非常にたくさんの仕事をしなければならない",
             "時間内に仕事が処理しきれない",
             "一生懸命働かなければならない",
             "かなり注意を集中する必要がある",
             "高度の知識や技術が必要なむずかしい仕事だ",
             "勤務時間中はいつも仕事のことを考えていなければならない",
             "からだを大変よく使う仕事だ",
             "自分のペースで仕事ができる",
             "自分で仕事の順番・やり方を決めることができる",
             "職場の仕事の方針に自分の意見を反映できる",
             "自分の技能や知識を仕事で使うことが少ない",
             "私の部署内で意見のくい違いがある",
             "私の部署と他の部署とはうまが合わない",
             "私の職場の雰囲気は友好的である",
             "私の職場の作業環境（騒音、照明、温度、換気など）はよくない",
             "仕事の内容は自分にあっている",
             "働きがいのある仕事だ")),
    Section("B", "Ｂ　最近１か月間のあなたの状態についてうかがいます",
            ("ほとんどなかった", "ときどきあった", "しばしばあった", "ほとんどいつもあった"),
            ("活気がわいてくる", "元気がいっぱいだ", "生き生きする",
             "怒りを感じる", "内心腹立たしい", "イライラしている",
             "ひどく疲れた", "へとへとだ", "だるい",
             "気がはりつめている", "不安だ", "落着かない",
             "ゆううつだ", "何をするのも面倒だ", "物事に集中できない",
             "気分が晴れない", "仕事が手につかない", "悲しいと感じる",
             "めまいがする", "体のふしぶしが痛む", "頭が重かったり頭痛がする",
             "首筋や肩がこる", "腰が痛い", "目が疲れる",
             "動悸や息切れがする", "胃腸の具合が悪い", "食欲がない",
             "便秘や下痢をする", "よく眠れない")),
    Section("C", "Ｃ　あなたの周りの方々についてうかがいます",
            ("非常に", "かなり", "多少", "全くない"),
            ("上司", "職場の同僚", "配偶者、家族、友人等") * 3,
            groups=((1, "次の人たちはどのくらい気軽に話ができますか？"),
                    (4, "あなたが困った時、次の人たちはどのくらい頼りになりますか？"),
                    (7, "あなたの個人的な問題を相談したら、次の人たちはどのくらいきいてくれますか？"))),
    Section("D", "Ｄ　満足度について",
            ("満足", "まあ満足", "やや不満足", "不満足"),
            ("仕事に満足だ", "家庭生活に満足だ")),
)

SECTION_BY_KEY = {s.key: s for s in SECTIONS}
ALL_ITEMS = [f"{s.key}{i}" for s in SECTIONS for i in range(1, len(s.items) + 1)]  # 57項目

# 回答は「そうだ=1 … ちがう=4」のように左から1〜4。
# 採点は「ストレスが高い方を4点、低い方を1点」に揃える。
# ここに挙げた項目は「5 − 回答」で逆転する（それ以外は回答のまま）。
# ※厚生労働省「ストレスチェック制度実施マニュアル」の合計点数方式に準拠。運用前に必ず照合してください。
REVERSED = (
    {f"A{n}" for n in (1, 2, 3, 4, 5, 6, 7, 11, 12, 13, 15)}
    | {"B1", "B2", "B3"}
)

# 尺度（結果通知書・Excelの内訳表示用）
SCALES = (
    ("A", "心理的な仕事の負担（量）", ("A1", "A2", "A3")),
    ("A", "心理的な仕事の負担（質）", ("A4", "A5", "A6")),
    ("A", "身体的負担度", ("A7",)),
    ("A", "職場の対人関係", ("A12", "A13", "A14")),
    ("A", "職場環境", ("A15",)),
    ("A", "仕事のコントロール", ("A8", "A9", "A10")),
    ("A", "技能の活用", ("A11",)),
    ("A", "仕事の適性", ("A16",)),
    ("A", "働きがい", ("A17",)),
    ("B", "活気", ("B1", "B2", "B3")),
    ("B", "イライラ感", ("B4", "B5", "B6")),
    ("B", "疲労感", ("B7", "B8", "B9")),
    ("B", "不安感", ("B10", "B11", "B12")),
    ("B", "抑うつ感", ("B13", "B14", "B15", "B16", "B17", "B18")),
    ("B", "身体愁訴", tuple(f"B{n}" for n in range(19, 30))),
    ("C", "上司からのサポート", ("C1", "C4", "C7")),
    ("C", "同僚からのサポート", ("C2", "C5", "C8")),
    ("C", "家族・友人からのサポート", ("C3", "C6", "C9")),
    ("D", "仕事や生活の満足度", ("D1", "D2")),
)

DOMAINS = {
    "A": ("仕事のストレス要因", 17),
    "B": ("心身のストレス反応", 29),
    "C": ("周囲のサポート", 9),
}


def item_label(item: str) -> str:
    sec = SECTION_BY_KEY[item[0]]
    text = sec.items[int(item[1:]) - 1]
    if sec.key == "C":
        text = ("話しやすさ", "頼りになる", "相談をきく")[(int(item[1:]) - 1) // 3] + "：" + text
    return text


def stress_point(item: str, answer: int) -> int:
    """回答(1〜4)を「4=ストレス高」の点数にする。"""
    return 5 - answer if item in REVERSED else answer


@dataclass
class Result:
    a: int
    b: int
    c: int
    high_stress: bool
    reason: str
    scales: list[tuple[str, str, float]]   # (領域, 尺度名, 1項目あたり平均点 1.0〜4.0)
    missing: list[str]


def score(answers: dict[str, int | None], criteria: dict) -> Result:
    """合計点数方式で採点し、高ストレス者かを判定する。未回答は判定不能として扱う。"""
    missing = [i for i in ALL_ITEMS if not answers.get(i)]
    pts = {i: stress_point(i, a) for i, a in answers.items() if a}

    def total(prefix: str) -> int:
        return sum(p for i, p in pts.items() if i.startswith(prefix))

    a, b, c = total("A"), total("B"), total("C")
    if criteria.get("b_only", 77) <= b:
        high, reason = True, f"心身のストレス反応が{b}点（基準{criteria['b_only']}点以上）"
    elif a + c >= criteria.get("ac", 76) and b >= criteria.get("b_with_ac", 63):
        high, reason = True, (f"仕事のストレス要因＋周囲のサポートが{a + c}点（基準{criteria['ac']}点以上）"
                              f"かつ心身のストレス反応が{b}点（基準{criteria['b_with_ac']}点以上）")
    else:
        high, reason = False, "高ストレスの基準に該当しません"

    scales = []
    for dom, name, items in SCALES:
        vals = [pts[i] for i in items if i in pts]
        scales.append((dom, name, round(sum(vals) / len(vals), 2) if vals else 0.0))
    return Result(a, b, c, high, reason, scales, missing)


def scale_level(avg: float, thresholds: dict) -> str:
    """尺度の1項目平均点(4=ストレス高)を3段階で表す（本システムの簡易区分）。"""
    if avg == 0:
        return "－"
    if avg >= thresholds.get("caution", 3.0):
        return "要注意"
    if avg <= thresholds.get("good", 2.0):
        return "良好"
    return "ふつう"
