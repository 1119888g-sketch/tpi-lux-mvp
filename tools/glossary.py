#!/usr/bin/env python3
"""Готовит глоссарий к вычитке носителем и проверяет его соблюдение.

    python3 tools/glossary.py            выгрузить docs/GLOSSARY.md и .csv
    python3 tools/glossary.py --audit    проверить, что перевод следует глоссарию

Смысл в том, чтобы носитель вычитывал 60 терминов, а не 479 строк: термины
согласуются один раз и дальше держат единообразие по всему сайту.
"""

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "src" / "i18n" / "glossary.json"
STRINGS = ROOT / "src" / "i18n" / "strings.json"
DOCS = ROOT / "docs"

# Русские окончания, которые отсекаем, чтобы «освещения» нашлось по «освещение».
STEM_CUT = re.compile(r"(ами|ями|ого|ему|ыми|ими|ах|ях|ов|ев|ам|ям|ой|ей|ые|ие|ый|ий|ая|яя|ое|ее|у|ю|а|я|о|е|ы|и|ь)$")


def stem(word: str) -> str:
    w = word.lower()
    return STEM_CUT.sub("", w) if len(w) > 5 else w


def term_pattern(ru: str) -> re.Pattern:
    parts = [re.escape(stem(w)) + r"\w*" for w in ru.split()]
    return re.compile(r"\b" + r"\W+".join(parts), re.IGNORECASE)


def load():
    g = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    s = json.loads(STRINGS.read_text(encoding="utf-8"))
    return g["terms"], s


def count_usage(terms, strings):
    """Сколько раз термин реально встречается в текстах сайта."""
    sources = [v["src"] for v in strings.values()]
    for t in terms:
        pat = term_pattern(t["ru"])
        t["_uses"] = sum(1 for s in sources if pat.search(s))
    return terms


def export(terms):
    DOCS.mkdir(exist_ok=True)
    check = [t for t in terms if t["status"] == "check"]
    ok = [t for t in terms if t["status"] == "ok"]
    done = [t for t in terms if t["status"] == "done"]

    lines = [
        "# Глоссарий TPI LUX — на вычитку носителем",
        "",
        f"Всего терминов: **{len(terms)}**. "
        f"Требуют решения: **{len(check)}**. Нужна беглая проверка: **{len(ok)}**. "
        f"Уже вычитано: **{len(done)}**.",
        "",
        "Грузинские варианты — черновик (машинный + сверка двух моделей). "
        "Задача вычитки: подтвердить или заменить. После вычитки термин фиксируется "
        "и дальше используется во всём переводе без вариаций.",
        "",
        "Колонка «в тексте» — сколько строк сайта содержат термин: "
        "чем больше число, тем дороже ошибка.",
        "",
        "## 1. Требуют решения",
        "",
        "Спорные места: калька с русского, заимствование или конкурирующие нормы.",
        "",
        "| Русский | Грузинский (черновик) | English | В тексте | На что смотреть |",
        "|---|---|---|---|---|",
    ]
    for t in sorted(check, key=lambda x: -x["_uses"]):
        note = t.get("note", "").replace("|", "/")
        lines.append(
            f'| {t["ru"]} | {t["ka"]} | {t["en"]} | {t["_uses"]} | {note} |'
        )

    lines += [
        "",
        "## 2. Беглая проверка",
        "",
        "Термины устоявшиеся — достаточно подтвердить, что звучит естественно.",
        "",
        "| Русский | Грузинский (черновик) | English | В тексте |",
        "|---|---|---|---|",
    ]
    for t in sorted(ok, key=lambda x: -x["_uses"]):
        lines.append(f'| {t["ru"]} | {t["ka"]} | {t["en"]} | {t["_uses"]} |')

    if done:
        lines += [
            "",
            "## 3. Зафиксировано",
            "",
            "| Русский | Грузинский | English | В тексте |",
            "|---|---|---|---|",
        ]
        for t in sorted(done, key=lambda x: -x["_uses"]):
            lines.append(f'| {t["ru"]} | {t["ka"]} | {t["en"]} | {t["_uses"]} |')

    lines += [
        "",
        "---",
        "",
        "**Как вернуть правки:** прислать этот файл с исправленной колонкой "
        "«Грузинский» и пометкой по спорным. Мы перенесём в `src/i18n/glossary.json` "
        "и поставим статус `done`.",
        "",
    ]

    md = DOCS / "GLOSSARY.md"
    md.write_text("\n".join(lines), encoding="utf-8")

    csv_path = DOCS / "glossary.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ru", "ka_draft", "ka_final", "en", "status", "uses", "note"])
        for t in sorted(terms, key=lambda x: (x["status"] != "check", -x["_uses"])):
            w.writerow([t["ru"], t["ka"], "", t["en"], t["status"], t["_uses"], t.get("note", "")])

    print(f"  docs/GLOSSARY.md   — {len(terms)} терминов ({len(check)} спорных)")
    print(f"  docs/glossary.csv  — та же таблица для переводчика (колонка ka_final пустая)")


def audit(terms, strings):
    """Где термин есть в русском, а согласованного грузинского в переводе нет."""
    misses = []
    for key, entry in strings.items():
        ka = (entry.get("ka") or "").strip()
        if not ka:
            continue
        for t in terms:
            if t["status"] == "check":
                continue
            if term_pattern(t["ru"]).search(entry["src"]) and t["ka"] not in ka:
                misses.append((key, t["ru"], t["ka"], entry["src"][:60]))

    if not misses:
        print("глоссарий соблюдён во всех переведённых строках")
        return 0
    print(f"расхождений с глоссарием: {len(misses)}\n")
    for key, ru, ka, src in misses[:40]:
        print(f"  {key}: ожидался «{ka}» ({ru})\n      {src}…")
    if len(misses) > 40:
        print(f"  … ещё {len(misses) - 40}")
    return 1


def main() -> int:
    terms, strings = load()
    count_usage(terms, strings)
    if "--audit" in sys.argv:
        return audit(terms, strings)
    export(terms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
