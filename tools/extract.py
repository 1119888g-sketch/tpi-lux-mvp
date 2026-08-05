#!/usr/bin/env python3
"""Извлекает переводимые строки из HTML-страниц TPI LUX.

На выходе:
  src/templates/<page>.html  — исходная разметка, текст заменён на {{ключ}}
  src/i18n/strings.json      — словарь: ключ → {src, ka, en, ctx}

Ключ — это хеш исходной русской строки, поэтому:
  • перестановка блоков на странице ничего не ломает;
  • одинаковые строки (меню, футер) переводятся один раз на весь сайт.

Разметка не меняется ни на байт — подставляются только текстовые узлы
и значения переводимых атрибутов. Проверяется tools/verify.py.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL_DIR = ROOT / "src" / "templates"
I18N_DIR = ROOT / "src" / "i18n"

PAGES = sorted(p.name for p in ROOT.glob("*.html"))

# Атрибуты, содержащие текст для пользователя.
TEXT_ATTRS = {"alt", "title", "placeholder", "aria-label"}

# content= переводим только у этих meta — остальные (og:url, og:image,
# og:locale, theme-color) это данные, а не текст.
META_TRANSLATABLE = {
    "description",
    "og:title",
    "og:description",
    "og:site_name",
    "twitter:title",
    "twitter:description",
}

TOKEN_RE = re.compile(r"<!--.*?-->|<[^>]*>", re.S)
TAG_NAME_RE = re.compile(r"^<\s*(/?)([a-zA-Z][\w-]*)")
ATTR_RE = re.compile(r"""(\s)([\w:-]+)(\s*=\s*)(["'])(.*?)\4""", re.S)
LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)

# Строки, которые переводить не нужно, даже если в них есть буквы.
SKIP_VALUES = {"TPI", "LUX", "TPI LUX"}


def has_letters(s: str) -> bool:
    return bool(LETTER_RE.search(s))


def make_key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


class Extractor:
    def __init__(self):
        # ключ → запись словаря
        self.strings: dict[str, dict] = {}

    def add(self, text: str, ctx: str) -> str:
        key = make_key(text)
        entry = self.strings.setdefault(
            key, {"src": text, "ka": "", "en": "", "ctx": []}
        )
        if ctx not in entry["ctx"]:
            entry["ctx"].append(ctx)
        return key

    def meta_key(self, tag: str) -> str | None:
        """Для <meta> возвращает name/property, если content переводим."""
        ident = None
        for _, name, _, _, value in ATTR_RE.findall(tag):
            if name.lower() in ("name", "property"):
                ident = value.strip()
        if ident in META_TRANSLATABLE:
            return ident
        return None

    def rewrite_tag(self, tag: str, page: str) -> str:
        name_m = TAG_NAME_RE.match(tag)
        if not name_m:
            return tag
        tag_name = name_m.group(2).lower()
        meta_ident = self.meta_key(tag) if tag_name == "meta" else None

        def repl(m: re.Match) -> str:
            ws, attr, eq, quote, value = m.groups()
            attr_l = attr.lower()
            translatable = attr_l in TEXT_ATTRS or (
                attr_l == "content" and meta_ident is not None
            )
            core = value.strip()
            if not translatable or not core or not has_letters(core):
                return m.group(0)
            if core in SKIP_VALUES:
                return m.group(0)
            label = meta_ident if meta_ident else f"{tag_name}@{attr_l}"
            key = self.add(core, f"{page}:{label}")
            lead = value[: len(value) - len(value.lstrip())]
            trail = value[len(value.rstrip()) :]
            return f"{ws}{attr}{eq}{quote}{lead}{{{{{key}}}}}{trail}{quote}"

        return ATTR_RE.sub(repl, tag)

    def process(self, page: str, html: str) -> str:
        out: list[str] = []
        pos = 0
        # Внутри script/style текста для перевода нет.
        opaque_depth = 0
        opaque_tag = None

        for m in TOKEN_RE.finditer(html):
            text = html[pos : m.start()]
            pos = m.end()

            if text:
                core = text.strip()
                if opaque_depth or not core or not has_letters(core) or core in SKIP_VALUES:
                    out.append(text)
                else:
                    lead = text[: len(text) - len(text.lstrip())]
                    trail = text[len(text.rstrip()) :]
                    key = self.add(core, page)
                    out.append(f"{lead}{{{{{key}}}}}{trail}")

            tag = m.group(0)
            name_m = TAG_NAME_RE.match(tag)
            if name_m:
                closing, tag_name = name_m.group(1), name_m.group(2).lower()
                if tag_name in ("script", "style"):
                    if closing:
                        opaque_depth = max(0, opaque_depth - 1)
                        if opaque_depth == 0:
                            opaque_tag = None
                    elif not tag.rstrip().endswith("/>"):
                        opaque_depth += 1
                        opaque_tag = tag_name

            out.append(tag if opaque_depth and not name_m else self.rewrite_tag(tag, page))

        out.append(html[pos:])
        return "".join(out)


JS_STRING_RE = re.compile(r"(['\"])((?:(?!\1)[^\\]|\\.)*)\1")


def extract_js(ex: "Extractor", source: str, name: str) -> str:
    """Строковые литералы с кириллицей в script.js — тоже интерфейс."""

    def repl(m: re.Match) -> str:
        quote, value = m.group(1), m.group(2)
        if not re.search(r"[А-Яа-яЁё]", value):
            return m.group(0)
        key = ex.add(value, name)
        return f"{quote}{{{{{key}}}}}{quote}"

    return JS_STRING_RE.sub(repl, source)


def main() -> int:
    if not PAGES:
        print("не нашёл HTML-страниц в корне", file=sys.stderr)
        return 1

    TPL_DIR.mkdir(parents=True, exist_ok=True)
    I18N_DIR.mkdir(parents=True, exist_ok=True)

    ex = Extractor()
    for page in PAGES:
        html = (ROOT / page).read_text(encoding="utf-8")
        tpl = ex.process(page, html)
        (TPL_DIR / page).write_text(tpl, encoding="utf-8")
        print(f"  {page:34} → src/templates/{page}")

    js_path = ROOT / "script.js"
    if js_path.exists():
        tpl = extract_js(ex, js_path.read_text(encoding="utf-8"), "script.js")
        (TPL_DIR / "script.js").write_text(tpl, encoding="utf-8")
        print(f"  {'script.js':34} → src/templates/script.js")

    # Сортируем по первому появлению, чтобы переводчик шёл по сайту сверху вниз.
    payload = {k: v for k, v in ex.strings.items()}
    out_path = I18N_DIR / "strings.json"

    # Перевод и статусы вычитки, сделанные ранее, не затираем.
    # Заново вычисляются только src и ctx — всё остальное переносится как есть,
    # иначе повторный запуск стирал бы отметки носителя о вычитке.
    if out_path.exists():
        old = json.loads(out_path.read_text(encoding="utf-8"))
        kept = 0
        for key, entry in payload.items():
            prev = old.get(key)
            if not prev:
                continue
            for field, value in prev.items():
                if field not in ("src", "ctx"):
                    entry[field] = value
            kept += 1
        print(f"\nсохранил переводы и статусы для {kept} строк из прежнего словаря")

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    words = sum(len(e["src"].split()) for e in payload.values())
    shared = sum(1 for e in payload.values() if len(e["ctx"]) > 1)
    print(f"\nстрок: {len(payload)}  (сквозных: {shared})")
    print(f"слов к переводу: {words}")
    print(f"словарь: src/i18n/strings.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
