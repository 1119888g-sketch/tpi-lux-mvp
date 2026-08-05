#!/usr/bin/env python3
"""Собирает трёхъязычный сайт TPI LUX из шаблонов и словаря.

    python3 tools/build.py

На выходе — папка dist/, готовая к заливке на любой хостинг как есть.
Никаких зависимостей: только стандартная библиотека Python.

    dist/
      index.html        определение языка + редирект
      styles.css        общие для всех языков
      crown.png
      assets/
      ka/ ru/ en/       по комплекту страниц на язык

Основной язык — грузинский: корень ведёт на /ka/, x-default тоже на него.
Если перевод строки пуст, подставляется русский исходник, и это видно
в отчёте о покрытии — сайт не ломается на полпути перевода.
"""

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL_DIR = ROOT / "src" / "templates"
STRINGS = ROOT / "src" / "i18n" / "strings.json"
DIST = ROOT / "dist"

SITE_URL = "https://tpilux.com"

# Порядок важен: первый язык — основной.
LANGS = {
    "ka": {"name": "ქართული", "locale": "ka_GE", "label": "KA"},
    "ru": {"name": "Русский", "locale": "ru_RU", "label": "RU"},
    "en": {"name": "English", "locale": "en_US", "label": "EN"},
}
DEFAULT_LANG = "ka"

# Файлы, общие для всех языков, лежат в корне dist/.
SHARED = ["styles.css", "crown.png", "crown.jpg", ".nojekyll"]
SHARED_DIRS = ["assets"]

# Ресурсы в корне — из языковой папки к ним на уровень выше.
ASSET_REF_RE = re.compile(
    r"""((?:src|href|poster)\s*=\s*["'])(crown\.png|crown\.jpg|styles\.css|assets/)"""
)
PLACEHOLDER_RE = re.compile(r"\{\{([0-9a-f]{8})\}\}")
HTML_LANG_RE = re.compile(r"(<html\b[^>]*\blang\s*=\s*[\"'])[^\"']*([\"'])")
CANONICAL_RE = re.compile(r"(<link\b[^>]*\brel\s*=\s*[\"']canonical[\"'][^>]*\bhref\s*=\s*[\"'])[^\"']*([\"'])")
OG_URL_RE = re.compile(r"(<meta\b[^>]*\bproperty\s*=\s*[\"']og:url[\"'][^>]*\bcontent\s*=\s*[\"'])[^\"']*([\"'])")
OG_LOCALE_RE = re.compile(r"(<meta\b[^>]*\bproperty\s*=\s*[\"']og:locale[\"'][^>]*\bcontent\s*=\s*[\"'])[^\"']*([\"'])")


def load_strings() -> dict:
    return json.loads(STRINGS.read_text(encoding="utf-8"))


def render(tpl: str, strings: dict, lang: str, missing: set) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        entry = strings.get(key)
        if entry is None:
            missing.add(key)
            return m.group(0)
        if lang == "ru":
            return entry["src"]
        value = (entry.get(lang) or "").strip()
        if not value:
            missing.add(key)
            return entry["src"]
        return value

    return PLACEHOLDER_RE.sub(repl, tpl)


def alternates_block(page: str, indent: str = "    ") -> str:
    lines = []
    for code in LANGS:
        href = f"{SITE_URL}/{code}/{page}"
        lines.append(f'{indent}<link rel="alternate" hreflang="{code}" href="{href}">')
    lines.append(
        f'{indent}<link rel="alternate" hreflang="x-default"'
        f' href="{SITE_URL}/{DEFAULT_LANG}/{page}">'
    )
    return "\n".join(lines)


def localise_head(html: str, lang: str, page: str) -> str:
    meta = LANGS[lang]
    page_url = f"{SITE_URL}/{lang}/{page}"

    html = HTML_LANG_RE.sub(rf"\g<1>{lang}\g<2>", html, count=1)
    html = CANONICAL_RE.sub(lambda m: m.group(1) + page_url + m.group(2), html, count=1)
    html = OG_URL_RE.sub(lambda m: m.group(1) + page_url + m.group(2), html, count=1)

    if OG_LOCALE_RE.search(html):
        html = OG_LOCALE_RE.sub(
            lambda m: m.group(1) + meta["locale"] + m.group(2), html, count=1
        )

    # Соседние языки — для Open Graph и для поисковиков.
    extra = [
        f'    <meta property="og:locale:alternate" content="{LANGS[c]["locale"]}">'
        for c in LANGS
        if c != lang
    ]
    block = alternates_block(page) + "\n" + "\n".join(extra) + "\n  </head>"
    return html.replace("  </head>", block, 1)


def rewrite_asset_paths(html: str) -> str:
    """Страницы лежат на уровень глубже общих ресурсов."""
    return ASSET_REF_RE.sub(lambda m: m.group(1) + "../" + m.group(2), html)


LANG_SWITCH_TPL = """      <div class="lang-switch" data-lang-switch>
        <button class="lang-current" type="button" aria-haspopup="true" aria-expanded="false" aria-label="{aria}">
          <svg class="lang-globe" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <circle cx="12" cy="12" r="9"></circle>
            <path d="M3 12h18"></path>
            <path d="M12 3c2.5 2.6 3.8 5.7 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.7-3.8-9S9.5 5.6 12 3z"></path>
          </svg>
          <span class="lang-code">{label}</span>
        </button>
        <ul class="lang-menu" role="menu">
{items}
        </ul>
      </div>
"""


def lang_switch(lang: str, page: str) -> str:
    aria = {
        "ka": "ენის შეცვლა",
        "ru": "Сменить язык",
        "en": "Change language",
    }[lang]
    items = []
    for code, meta in LANGS.items():
        current = ' aria-current="true"' if code == lang else ""
        # Переключение сохраняет текущую страницу, а не бросает на главную.
        items.append(
            f'          <li role="none"><a role="menuitem" hreflang="{code}"'
            f' lang="{code}" href="../{code}/{page}"{current}>{meta["name"]}</a></li>'
        )
    return LANG_SWITCH_TPL.format(
        aria=aria, label=LANGS[lang]["label"], items="\n".join(items)
    )


def insert_lang_switch(html: str, lang: str, page: str) -> str:
    marker = '      <button class="menu-toggle"'
    if marker not in html:
        return html
    return html.replace(marker, lang_switch(lang, page) + marker, 1)


ROOT_INDEX = """<!doctype html>
<html lang="{default}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>TPI LUX</title>
    <meta name="robots" content="noindex">
    <link rel="icon" href="crown.png">
    <link rel="canonical" href="{site}/{default}/index.html">
{alternates}
    <meta http-equiv="refresh" content="0; url={default}/index.html">
    <script>
      // Отдаём язык браузера, если он у нас есть; иначе — грузинский.
      (function () {{
        var supported = {supported};
        var target = "{default}";
        var list = navigator.languages || [navigator.language || ""];
        for (var i = 0; i < list.length; i++) {{
          var code = String(list[i]).slice(0, 2).toLowerCase();
          if (supported.indexOf(code) !== -1) {{ target = code; break; }}
        }}
        location.replace(target + "/index.html" + location.hash);
      }})();
    </script>
  </head>
  <body>
    <p><a href="{default}/index.html">TPI LUX</a></p>
  </body>
</html>
"""


def build_root_index() -> str:
    return ROOT_INDEX.format(
        default=DEFAULT_LANG,
        site=SITE_URL,
        supported=json.dumps(list(LANGS)),
        alternates=alternates_block("index.html"),
    )


def main() -> int:
    strings = load_strings()
    pages = sorted(p.name for p in TPL_DIR.glob("*.html"))
    js_tpl_path = TPL_DIR / "script.js"

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    for name in SHARED:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, DIST / name)
    for name in SHARED_DIRS:
        src = ROOT / name
        if src.exists():
            shutil.copytree(
                src, DIST / name, ignore=shutil.ignore_patterns("_orig")
            )

    report = {}
    for lang in LANGS:
        missing: set = set()
        out_dir = DIST / lang
        out_dir.mkdir()

        for page in pages:
            tpl = (TPL_DIR / page).read_text(encoding="utf-8")
            html = render(tpl, strings, lang, missing)
            html = rewrite_asset_paths(html)
            html = localise_head(html, lang, page)
            html = insert_lang_switch(html, lang, page)
            (out_dir / page).write_text(html, encoding="utf-8")

        if js_tpl_path.exists():
            js = render(js_tpl_path.read_text(encoding="utf-8"), strings, lang, missing)
            (out_dir / "script.js").write_text(js, encoding="utf-8")

        total = len(strings)
        done = total - len(missing)
        report[lang] = (done, total)

    (DIST / "index.html").write_text(build_root_index(), encoding="utf-8")
    (DIST / ".nojekyll").touch()

    print(f"собрано в dist/  ({len(pages)} страниц × {len(LANGS)} языка)\n")
    for lang, (done, total) in report.items():
        pct = done * 100 // total if total else 0
        bar = "█" * (pct // 5) + "·" * (20 - pct // 5)
        mark = "  ← основной" if lang == DEFAULT_LANG else ""
        print(f"  {lang}  {bar}  {done:>3}/{total} строк ({pct}%){mark}")
    print("\nпустые переводы подставлены русским исходником — сайт цел")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
