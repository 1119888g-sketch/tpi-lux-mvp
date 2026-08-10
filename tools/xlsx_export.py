#!/usr/bin/env python3
"""Выгрузка строк сайта в .xlsx для вычитки носителем языка.

    python3 tools/xlsx_export.py [выходной_файл.xlsx]

Носитель правит только жёлтую колонку «ქართული» и колонку комментария.
Обратный импорт — tools/xlsx_import.py.
"""
import json
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
STRINGS = ROOT / "src" / "i18n" / "strings.json"
GLOSSARY = ROOT / "src" / "i18n" / "glossary.json"
TEMPLATES = ROOT / "src" / "templates"

# порядок страниц как в навигации сайта
PAGE_ORDER = [
    "index.html",
    "architectural-lighting.html",
    "led-garlands-figures.html",
    "christmas-decoration.html",
    "electrical-installation.html",
    "lighting-control.html",
    "security-low-voltage.html",
    "climate-ventilation.html",
    "playgrounds-urban.html",
    "event-show-solutions.html",
    "script.js",
]
PAGE_TITLES = {
    "index.html": "Главная",
    "architectural-lighting.html": "Архитектурное освещение",
    "led-garlands-figures.html": "Гирлянды и фигуры",
    "christmas-decoration.html": "Новогоднее оформление",
    "electrical-installation.html": "Электромонтаж",
    "lighting-control.html": "Управление светом",
    "security-low-voltage.html": "Безопасность и слаботочка",
    "climate-ventilation.html": "Климат и вентиляция",
    "playgrounds-urban.html": "Детские площадки",
    "event-show-solutions.html": "Event & Show Solutions",
    "script.js": "Системные сообщения",
}
SHARED = "Общие элементы (меню, шапка, подвал)"

TAG_LABEL = {
    "title": "Заголовок вкладки браузера (SEO)",
    "h1": "Главный заголовок страницы (H1)",
    "h2": "Заголовок раздела (H2)",
    "h3": "Подзаголовок (H3)",
    "h4": "Подзаголовок (H4)",
    "p": "Абзац текста",
    "li": "Пункт списка",
    "a": "Ссылка / кнопка",
    "button": "Кнопка",
    "label": "Подпись поля формы",
    "option": "Пункт выпадающего списка",
    "th": "Заголовок колонки таблицы",
    "td": "Ячейка таблицы",
    "span": "Короткая подпись",
    "div": "Текстовый блок",
    "strong": "Выделенный текст",
    "em": "Выделенный текст",
    "figcaption": "Подпись к изображению",
    "summary": "Заголовок раскрывающегося блока",
    "b": "Выделенное число / текст",
    "i": "Выделенный текст",
    "small": "Мелкая подпись",
    "time": "Дата / время",
    "address": "Адрес",
    "blockquote": "Цитата",
}
ATTR_LABEL = {
    "description": "Описание страницы для Google (SEO, 150–160 симв.)",
    "og:description": "Описание для соцсетей",
    "twitter:description": "Описание для соцсетей",
    "og:title": "Заголовок для соцсетей",
    "twitter:title": "Заголовок для соцсетей",
    "@aria-label": "Подпись для незрячих (озвучивает скринридер)",
    "@placeholder": "Подсказка внутри поля формы",
    "@alt": "Описание картинки (alt)",
    "@title": "Всплывающая подсказка",
}
# классы, которые CSS выводит КАПСОМ
UPPERCASE_CLASSES = ("section-kicker", "badge-new")
CAPS_NOTE = " ⚠ на сайте выводится КАПСОМ"

TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def scan_templates():
    """{page: [(key, метка элемента)]} в порядке появления в вёрстке."""
    order = {}
    for path in sorted(TEMPLATES.iterdir()):
        text = path.read_text(encoding="utf-8")
        tags = [(m.end(), m.group(1).lower(), m.group(2)) for m in TAG_RE.finditer(text)]
        rows = []
        for m in re.finditer(r"\{\{([0-9a-f]+)\}\}", text):
            pos = m.start()
            # строка внутри атрибута (<meta content="{{k}}">, aria-label и т.п.):
            # смысл такой строки знает только ctx — метку из вёрстки не берём
            if text.rfind("<", 0, pos) > text.rfind(">", 0, pos):
                rows.append((m.group(1), None))
                continue
            tag, attrs = "", ""
            for end, name, a in tags:
                if end <= pos:
                    tag, attrs = name, a
                else:
                    break
            label = TAG_LABEL.get(tag, "Текст на странице")
            if any(c in attrs for c in UPPERCASE_CLASSES):
                label += CAPS_NOTE
            elif tag == "span" and "service-hero-panel" in text[max(0, pos - 400):pos]:
                label += CAPS_NOTE
            rows.append((m.group(1), label))
        order[path.name] = rows
    return order


def attr_label(ctx):
    """Метка для строки, живущей в атрибуте/мета-теге."""
    for c in ctx:
        if ":" not in c:
            continue
        suffix = c.split(":", 1)[1]
        if suffix in ATTR_LABEL:
            return ATTR_LABEL[suffix]
        if "@" in suffix:
            return ATTR_LABEL.get("@" + suffix.split("@", 1)[1], "Служебная подпись")
    return None


def build_rows(data, order, merged=None):
    merged = merged or {}
    pages_of = {k: {c.split(":", 1)[0] for c in v["ctx"]} for k, v in data.items()}
    label_of, first_page = {}, {}
    for page in PAGE_ORDER:
        for key, label in order.get(page, []):
            if label:
                label_of.setdefault(key, label)
            first_page.setdefault(key, page)

    rows, seen = [], set()

    def emit(key, group):
        if key in seen:
            return
        seen.add(key)
        v = data[key]
        default = (
            "Всплывающее сообщение на сайте"
            if all(c.split(":", 1)[0] == "script.js" for c in v["ctx"])
            else "Текст на странице"
        )
        label = label_of.get(key) or attr_label(v["ctx"]) or default
        src = v["src"]
        no_tr = not CYRILLIC_RE.search(src)
        m = merged.get(key, {})
        reasons = list(m.get("reasons", []))
        if not m and not no_tr and not (v.get("ka") or "").strip():
            reasons = ["перевода нет — заполнить с нуля"]
        # второй вариант показываем тот, что дальше всех от основного:
        # именно он показывает, в чём именно сомнение
        alt, alt_sim = "", 2.0
        for name in ("codex", "claude-en", "codex-en", "claude"):
            text, sim = m.get(name, ""), m.get("sims", {}).get(name, 2.0)
            if text and text != m.get("primary") and sim < alt_sim:
                alt, alt_sim = text, sim
        rows.append(
            {
                "id": key,
                "group": group,
                "where": "НЕ ПЕРЕВОДИТЬ — оставить как есть" if no_tr else label,
                "src": src,
                "en": v.get("en", ""),
                "ka": v.get("ka", "") or m.get("primary", "") or (src if no_tr else ""),
                "alt": "" if no_tr else alt,
                "flag": "; ".join(reasons),
                "review": bool(reasons) and not no_tr,
                "locked_row": no_tr,
            }
        )

    # 1) сквозные строки — те, что встречаются на 3+ страницах
    for page in PAGE_ORDER:
        for key, _ in order.get(page, []):
            if len(pages_of.get(key, ())) >= 3:
                emit(key, SHARED)
    for key in data:
        if len(pages_of.get(key, ())) >= 3:
            emit(key, SHARED)

    # 2) построчно по страницам: сначала мета-теги, потом текст по порядку вёрстки
    for page in PAGE_ORDER:
        group = PAGE_TITLES.get(page, page)
        meta = [
            k
            for k, v in data.items()
            if k not in seen
            and any(c.startswith(page + ":") and "@" not in c for c in v["ctx"])
        ]
        for key in meta:
            emit(key, group)
        for key, _ in order.get(page, []):
            if key in data:
                emit(key, group)
        for key, v in data.items():
            if any(c.split(":", 1)[0] == page for c in v["ctx"]):
                emit(key, group)

    for key in data:  # страховка: ничего не потерять
        emit(key, "Прочее")
    return rows


HEAD_FILL = PatternFill("solid", fgColor="1C1C1E")
GROUP_FILL = PatternFill("solid", fgColor="EDE7D8")
KA_FILL = PatternFill("solid", fgColor="FFF6D6")
NOTE_FILL = PatternFill("solid", fgColor="EEF3FB")
ID_FILL = PatternFill("solid", fgColor="F4F4F4")
SKIP_FILL = PatternFill("solid", fgColor="F0F0F0")
THIN = Side(style="thin", color="D4D4D4")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
KA_FONT = Font(name="Sylfaen", size=12)
TOP_WRAP = Alignment(vertical="top", wrap_text=True)


def write_instructions(ws):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 108
    lines = [
        ("TPI LUX — вычитка грузинского текста сайта", "h1"),
        ("", ""),
        ("Здесь только спорные места — не весь сайт.", "b"),
        ("Сайт переведён целиком. Каждую строку переводили четыре раза независимо: "
         "две языковые модели с русского и те же две модели с английского, не видя "
         "русского текста. Там, где все переводы сошлись, проверять нечего — эти строки "
         "в файл не попали. Осталось то, где переводы разошлись или автопроверка нашла "
         "дефект. Это и есть настоящие сомнения.", ""),
        ("", ""),
        ("Что делать", "h2"),
        ("В колонке «ქართული — наш перевод» — текущий вариант. Читаете его рядом "
         "с русским оригиналом:", ""),
        ("• верно — не делаете ничего, идёте дальше;", ""),
        ("• неверно или звучит неестественно — пишете свой вариант в жёлтую колонку "
         "«✍ ПРАВКА». Она всегда побеждает наш перевод.", ""),
        ("• хотите пояснить решение или задать вопрос — колонка «Комментарий», "
         "на любом языке.", ""),
        ("", ""),
        ("Колонка «⚠ Почему строка здесь» говорит, что именно вызвало сомнение: "
         "модели дали разный перевод, перевод с русского разошёлся с переводом "
         "с английского, либо автопроверка нашла дефект. Рядом, в колонке «второй "
         "вариант», лежит конкурирующий перевод — иногда он окажется удачнее нашего.", ""),
        ("", ""),
        ("Три просьбы", "h2"),
        ("1. Не удалять, не добавлять и не сортировать строки, не трогать серую колонку ID — "
         "по ней текст возвращается на сайт. Остальные колонки защищены от случайной правки; "
         "пароля нет, снять защиту можно через «Рецензирование → Снять защиту листа».", ""),
        ("2. Строки «НЕ ПЕРЕВОДИТЬ» — бренды, адреса, телефоны. Их менять не нужно.", ""),
        ("3. Пометка «⚠ выводится КАПСОМ» означает, что на сайте надпись печатается "
         "заглавными. В грузинском заглавных нет — пишите как должно читаться, вёрстку "
         "под это поправим.", ""),
        ("", ""),
        ("Лист «Термины» — только спорные термины, по которым нужно ваше решение; "
         "устоявшиеся из него убраны. Правка термина разойдётся по всему сайту, "
         "поэтому их лучше решить первыми.", ""),
        ("", ""),
        ("Готовый файл верните в этом же формате .xlsx.", "b"),
        ("", ""),
        ("— — —", ""),
        ("", ""),
        ("TPI LUX — Georgian website copy review", "h1"),
        ("", ""),
        ("This file holds only the doubtful rows, not the whole site. Every string was "
         "translated four times independently — two language models from Russian and the "
         "same two from English, without seeing the Russian. Where all four agreed, there "
         "is nothing to check and the row was left out.", ""),
        ("On the “Перевод” sheet, the column “ქართული — наш перевод” holds the current "
         "translation. If it is right, do nothing. If it is wrong or sounds unnatural, write "
         "your version in the yellow “✍ ПРАВКА” column — your version always wins. Notes and "
         "questions go in “Комментарий”, in any language.", ""),
        ("The “⚠ Почему строка здесь” column tells you what raised the doubt: the models "
         "disagreed, the Russian-source and English-source translations diverged, or an "
         "automatic check found a defect. The “второй вариант” column holds the competing "
         "translation — sometimes it reads better than ours.", ""),
        ("Please do not delete, add or re-sort rows, and leave the grey ID column untouched — "
         "it is how the text gets back into the site. Rows marked «НЕ ПЕРЕВОДИТЬ» "
         "(brands, e-mails, phone numbers) need no action.", ""),
        ("“⚠ выводится КАПСОМ” means the site renders that label in capitals; Georgian has no "
         "capitals, so write it as it should read and we will adjust the styling.", ""),
        ("The “Термины” sheet lists only the disputed terms that need your decision. "
         "Fixing a term there propagates it across the whole site, so start with them.", ""),
        ("Please send the file back as .xlsx.", "b"),
    ]
    row = 2
    for text, kind in lines:
        cell = ws.cell(row=row, column=2, value=text)
        cell.alignment = Alignment(vertical="top", wrap_text=True)
        if kind == "h1":
            cell.font = Font(bold=True, size=16, color="1C1C1E")
        elif kind == "h2":
            cell.font = Font(bold=True, size=12, color="8A6D2F")
        elif kind == "b":
            cell.font = Font(bold=True, size=11)
        else:
            cell.font = Font(size=11)
        row += 1


# порядок и заголовки колонок листа «Перевод»; импорт ищет их по названию
COLUMNS = [
    ("ID — не трогать", 11),
    ("Раздел сайта", 24),
    ("Где на странице", 30),
    ("Русский — оригинал", 52),
    ("ქართული — наш перевод", 52),
    ("✍ ПРАВКА — если перевод неверен", 52),
    ("Комментарий", 30),
    ("⚠ Почему строка здесь", 30),
    ("ქართული — второй вариант, для сверки", 46),
    ("English — для справки", 44),
]
COL_OURS, COL_FIX, COL_NOTE, COL_FLAG = 5, 6, 7, 8
FLAG_FILL = PatternFill("solid", fgColor="FBE3E4")


def write_translation(ws, rows):
    for i, (title, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=i, value=title)
        cell.fill = HEAD_FILL
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.cell(row=1, column=COL_FIX).fill = PatternFill("solid", fgColor="8A6D2F")
    ws.row_dimensions[1].height = 40

    prev_group = None
    for n, r in enumerate(rows, start=2):
        values = [
            r["id"],
            r["group"],
            r["where"],
            r["src"],
            r["ka"],
            "",
            "",
            r.get("flag", ""),
            r.get("alt", ""),
            r["en"],
        ]
        for i, value in enumerate(values, start=1):
            cell = ws.cell(row=n, column=i, value=value)
            cell.alignment = TOP_WRAP
            cell.border = BORDER
            cell.font = Font(size=11)
        ws.cell(row=n, column=1).fill = ID_FILL
        ws.cell(row=n, column=1).font = Font(size=9, color="8C8C8C")
        if r["group"] != prev_group:
            ws.cell(row=n, column=2).font = Font(size=11, bold=True)
            prev_group = r["group"]
        ws.cell(row=n, column=2).fill = GROUP_FILL

        ours = ws.cell(row=n, column=COL_OURS)          # наш перевод — только читать
        ours.font = KA_FONT
        ours.fill = SKIP_FILL if r["locked_row"] else PatternFill("solid", fgColor="F3F7F3")
        fix = ws.cell(row=n, column=COL_FIX)            # сюда носитель пишет правку
        fix.font = KA_FONT
        fix.fill = SKIP_FILL if r["locked_row"] else KA_FILL
        fix.protection = Protection(locked=r["locked_row"])
        note = ws.cell(row=n, column=COL_NOTE)
        note.fill = NOTE_FILL
        note.protection = Protection(locked=False)
        flag = ws.cell(row=n, column=COL_FLAG)
        flag.font = Font(size=10, bold=bool(r.get("flag")), color="9C3B3B")
        if r.get("flag"):
            flag.fill = FLAG_FILL
        ws.cell(row=n, column=9).font = KA_FONT
        ws.cell(row=n, column=9).font = Font(name="Sylfaen", size=10, color="7A7A7A")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(rows) + 1}"
    ws.protection.enable()
    ws.protection.autoFilter = False
    ws.protection.sort = False
    ws.protection.formatColumns = False
    ws.protection.formatRows = False


def write_glossary(ws, glossary):
    headers = [
        ("Русский", 34),
        ("ქართული — проверить", 34),
        ("English", 30),
        ("Статус", 14),
        ("Комментарий", 40),
    ]
    for i, (title, width) in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=i, value=title)
        cell.fill = HEAD_FILL
        cell.font = Font(bold=True, color="FFFFFF", size=11)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[1].height = 30

    status_note = {
        "ok": "перевод устоявшийся — беглая проверка",
        "check": "нужно решение носителя",
        "done": "уже вычитано",
    }
    # устоявшиеся и уже вычитанные термины носителю показывать незачем
    terms = [t for t in glossary.get("terms", []) if t.get("status") == "check"]
    for n, term in enumerate(terms, start=2):
        status = term.get("status", "")
        values = [
            term.get("ru", ""),
            term.get("ka", ""),
            term.get("en", ""),
            status,
            status_note.get(status, ""),
        ]
        for i, value in enumerate(values, start=1):
            cell = ws.cell(row=n, column=i, value=value)
            cell.alignment = TOP_WRAP
            cell.border = BORDER
            cell.font = Font(size=11)
        ka = ws.cell(row=n, column=2)
        ka.font = KA_FONT
        ka.fill = KA_FILL
        if status == "check":
            ws.cell(row=n, column=4).font = Font(size=11, bold=True, color="B8860B")
    ws.freeze_panes = "A2"


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(argv[0]) if argv else ROOT / "TPI_LUX_перевод_KA.xlsx"
    data = json.loads(STRINGS.read_text(encoding="utf-8"))
    glossary = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    merged_path = ROOT / ".mt" / "merged.json"
    merged = json.loads(merged_path.read_text(encoding="utf-8")) if merged_path.exists() else {}
    rows = build_rows(data, scan_templates(), merged)
    if merged and "--all" not in sys.argv:
        # носителю показываем только то, в чём не уверены сами
        rows = [r for r in rows if r["review"]]

    wb = Workbook()
    write_instructions(wb.active)
    wb.active.title = "Инструкция"
    write_translation(wb.create_sheet("Перевод"), rows)
    write_glossary(wb.create_sheet("Термины"), glossary)
    wb.save(out)

    disputed = sum(1 for t in glossary.get("terms", []) if t.get("status") == "check")
    print(
        f"{out}  —  строк на проверку: {len(rows)} из {len(data)}, "
        f"спорных терминов: {disputed}"
    )


if __name__ == "__main__":
    main()
