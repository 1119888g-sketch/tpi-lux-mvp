#!/usr/bin/env python3
"""Проверки качества локализации TPI LUX.

    python3 tools/check.py

Ловит то, что заказчик и разработчик не видят глазами, потому что не читают
по-грузински. Главный случай — смешение письма внутри слова: машинный перевод
дописывает грузинское окончание к русскому корню («трасა»), и для носителя это
выглядит как явный брак.

Коды выхода: 0 — ошибок нет, 1 — есть ошибки (предупреждения не валят сборку).
"""

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRINGS = ROOT / "src" / "i18n" / "strings.json"

LANGS = ("ka", "en")

# Строки короче этого — подписи, кнопки, пункты меню: место ограничено.
UI_MAX_SRC = 30
UI_GROWTH = 1.7

ENTITY_RE = re.compile(r"&[a-zA-Z]+;|&#\d+;")
WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Латиница внутри грузинского текста законна: это термины и марки.
LATIN_OK = {
    "tpi", "lux", "led", "dmx", "dali", "knx", "rgb", "rgbw", "ip",
    "wi", "fi", "usb", "hd", "uv", "smd", "cob", "ac", "dc", "kw", "w",
    "georgia", "premium", "engineering", "service", "event", "show",
    "solutions", "new", "b2b", "iso", "led-", "pro",
}


def script_of(ch: str) -> str | None:
    o = ord(ch)
    if 0x10A0 <= o <= 0x10FF or 0x1C90 <= o <= 0x1CBF or 0x2D00 <= o <= 0x2D2F:
        return "GEO"
    if 0x0400 <= o <= 0x04FF:
        return "CYR"
    if (0x0041 <= o <= 0x005A) or (0x0061 <= o <= 0x007A):
        return "LAT"
    if unicodedata.category(ch).startswith("L"):
        return "OTHER"
    return None


def scripts_in(word: str) -> set:
    return {s for s in (script_of(c) for c in word) if s}


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def check_mixed_script(key: str, lang: str, text: str, rep: Report) -> None:
    """Кириллица + мхедрули в одном слове — всегда брак."""
    for m in WORD_RE.finditer(text):
        word = m.group()
        s = scripts_in(word)
        if len(s) < 2:
            continue
        if "GEO" in s and "CYR" in s:
            rep.error(f"[{lang}] {key}: смешение письма в слове «{word}» — кириллица внутри грузинского")
        elif "GEO" in s and "LAT" in s and word.lower() not in LATIN_OK:
            rep.warn(f"[{lang}] {key}: слово «{word}» смешивает мхедрули и латиницу")


def check_stray_cyrillic(key: str, lang: str, text: str, src: str, rep: Report) -> None:
    """Кириллица в ka/en почти всегда означает недопереведённый кусок."""
    cyr_words = [w for w in WORD_RE.findall(text) if scripts_in(w) == {"CYR"}]
    if not cyr_words:
        return
    # Если строка целиком совпала с исходником — это осознанный «не переводим».
    if text.strip() == src.strip():
        return
    rep.error(
        f"[{lang}] {key}: остались русские слова — {', '.join(cyr_words[:6])}"
    )


def check_entities(key: str, lang: str, text: str, src: str, rep: Report) -> None:
    a, b = sorted(ENTITY_RE.findall(src)), sorted(ENTITY_RE.findall(text))
    if a != b:
        rep.error(f"[{lang}] {key}: HTML-сущности не совпадают с исходником: {a} → {b}")


def check_length(key: str, lang: str, text: str, src: str, rep: Report) -> None:
    if len(src) > UI_MAX_SRC:
        return
    if len(text) > max(len(src) * UI_GROWTH, len(src) + 6):
        rep.warn(
            f"[{lang}] {key}: подпись длиннее исходной в {len(text) / max(len(src), 1):.1f}× "
            f"({len(src)}→{len(text)} симв.) «{src}» → «{text}» — проверить, влезает ли в шапку/кнопку"
        )


def main() -> int:
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    rep = Report()
    coverage = {lang: 0 for lang in LANGS}
    drafts = defaultdict(int)

    for key, entry in strings.items():
        src = entry["src"]
        for lang in LANGS:
            text = (entry.get(lang) or "").strip()
            if not text:
                continue
            coverage[lang] += 1
            if entry.get(f"st_{lang}", "draft") == "draft":
                drafts[lang] += 1

            check_entities(key, lang, text, src, rep)
            check_length(key, lang, text, src, rep)
            if lang == "ka":
                check_mixed_script(key, lang, text, rep)
            check_stray_cyrillic(key, lang, text, src, rep)

    total = len(strings)
    print("покрытие:")
    for lang in LANGS:
        done = coverage[lang]
        pct = done * 100 // total if total else 0
        print(f"  {lang}: {done}/{total} ({pct}%), из них черновиков без вычитки: {drafts[lang]}")

    if rep.warnings:
        print(f"\nпредупреждения ({len(rep.warnings)}):")
        for w in rep.warnings:
            print(f"  ⚠ {w}")

    if rep.errors:
        print(f"\nОШИБКИ ({len(rep.errors)}):")
        for e in rep.errors:
            print(f"  ✗ {e}")
        return 1

    print("\nошибок нет")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
