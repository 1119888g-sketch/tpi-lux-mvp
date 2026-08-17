#!/usr/bin/env python3
"""Применение терминов, исправленных носителем, к глоссарию и строкам.

    python3 tools/apply_terms.py [--dry-run]

Носитель вписал правки терминов в колонку «Комментарий» листа «Термины»,
поэтому xlsx_import их не подхватил — он читает только колонку перевода.

Почему замена не механическая. Грузинский агглютинативен, и термин в тексте
стоит в той форме, которой требует фраза. Слепая подстановка словарной формы
ломает согласование, поэтому ниже для каждого термина задана форма, в которой
он реально встречается, и форма, на которую его меняем.

Строки, где термин заменён, помечаются term_review — это правка поверх уже
вычитанного носителем текста, и подтвердить её должен тоже он.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRINGS = ROOT / "src" / "i18n" / "strings.json"
GLOSSARY = ROOT / "src" / "i18n" / "glossary.json"
REVIEW = ROOT / "docs" / "term-review-needed.md"

# Словарная форма термина: что стояло → что ставит носитель.
GLOSSARY_FIXES = {
    "под ключ": "სრული მომსახურეობა",
    "слаботочные сети": "დაბალი ძაბვის ქსელები",
    "светотехнический расчёт": "ტექგანათების გაანგარიშება",
    "светодиодный": "დიოდური განათება",
    "диммирование": "განათების რეგულირება",
    "городские пространства": "საქალაქო სივრცეები",
    "подрядчик": "კონტრაქტორი",
}

# Замены в тексте — по формам, а не по словарной основе.
# Порядок важен: более длинная форма идёт раньше, иначе её съест короткая.
TEXT_FIXES = [
    # «сделаем под ключ» стоит в творительном: сохраняем падеж
    ("სრული ციკლით", "სრული მომსახურეობით", "под ключ, творительный падеж"),
    # оба — определения в родительном, подставляется как есть
    ("სუსტი დენების", "დაბალი ძაბვის", "слаботочные сети"),
    # определение в родительном; число остаётся на главном слове
    ("შუქტექნიკური", "ტექგანათების", "светотехнический расчёт"),
    # ВНИМАНИЕ: носитель дал «დიოდური განათება» — это существительное с
    # определением. Перед «гирляндами» нужно прилагательное, иначе фраза
    # рассыпается. Ставим «დიოდური» и просим подтвердить.
    ("შუქდიოდური", "დიოდური", "светодиодный, форма прилагательного"),
    # оба относительных прилагательных, не склоняются
    ("ურბანული", "საქალაქო", "городской"),
    # формы «подрядчика» — от длинной к короткой, иначе короткая съест длинную
    ("მენარდეების", "კონტრაქტორების", "подрядчиков, род. мн."),
    ("მენარდის", "კონტრაქტორის", "подрядчика, род. ед."),
    ("მენარდე", "კონტრაქტორი", "подрядчик, им. ед."),
]

dry = "--dry-run" in sys.argv

data = json.loads(STRINGS.read_text(encoding="utf-8"))
glossary = json.loads(GLOSSARY.read_text(encoding="utf-8"))

# ── глоссарий ────────────────────────────────────────────────────────────
terms_changed = []
for term in glossary.get("terms", []):
    ru = term.get("ru", "")
    if ru in GLOSSARY_FIXES:
        old = (term.get("ka") or "").strip()
        new = GLOSSARY_FIXES[ru]
        if old != new:
            terms_changed.append((ru, old, new))
            if not dry:
                term["ka"] = new
                term["status"] = "native"

# ── строки ───────────────────────────────────────────────────────────────
touched = {}
for key, entry in data.items():
    ka = entry.get("ka") or ""
    if not ka:
        continue
    new_ka, applied = ka, []
    for old, new, why in TEXT_FIXES:
        if old in new_ka:
            n = new_ka.count(old)
            new_ka = new_ka.replace(old, new)
            applied.append(f"{old} → {new} ({why}){' ×' + str(n) if n > 1 else ''}")
    if applied:
        touched[key] = dict(before=ka, after=new_ka, applied=applied,
                            ru=entry.get("src", ""), was=entry.get("st_ka", "—"))
        if not dry:
            entry["ka"] = new_ka
            entry["term_review"] = True

# ── отчёт ────────────────────────────────────────────────────────────────
print(f"терминов в глоссарии обновлено: {len(terms_changed)}")
for ru, old, new in terms_changed:
    print(f"  {ru}: {old} → {new}")
print(f"\nстрок затронуто: {len(touched)}")

if dry:
    print("\n--dry-run: файлы не тронуты")
    for key, t in list(touched.items())[:5]:
        print(f"\n  [{key}] {t['ru'][:60]}")
        print(f"    было:  {t['before'][:90]}")
        print(f"    стало: {t['after'][:90]}")
    sys.exit()

STRINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
GLOSSARY.write_text(json.dumps(glossary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

lines = [
    "# Термины: строки на подтверждение носителю",
    "",
    "Носитель прислал правки терминов в колонке «Комментарий». Они применены,",
    "но термин в грузинском стоит в форме, которой требует фраза, поэтому подставлялась",
    "не словарная форма, а падежная — её и нужно проверить.",
    "",
    "Отдельно прошу посмотреть **светодиодный**: в правке дано «დიოდური განათება»",
    "(существительное с определением), а перед «гирляндами» нужно прилагательное —",
    "поставлено «დიოდური». Если это неверно, скажите, как правильно.",
    "",
    f"Всего строк: {len(touched)}",
    "",
]
for key, t in sorted(touched.items(), key=lambda x: x[1]["ru"]):
    lines += [
        f"## {t['ru'][:80] or key}",
        "",
        f"- было:  {t['before']}",
        f"- стало: {t['after']}",
        f"- замены: {'; '.join(t['applied'])}",
        "",
    ]
REVIEW.write_text("\n".join(lines), encoding="utf-8")

print(f"\nзаписано: {STRINGS.relative_to(ROOT)}, {GLOSSARY.relative_to(ROOT)}, {REVIEW.relative_to(ROOT)}")
print("дальше:   python3 tools/check.py && python3 tools/build.py")
