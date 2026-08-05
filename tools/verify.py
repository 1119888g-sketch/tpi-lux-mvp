#!/usr/bin/env python3
"""Round-trip: подставляем русские исходники обратно в шаблоны и сверяем
результат с оригинальными страницами. Расхождений быть не должно ни на байт.

Это страховка от визуальной регрессии: если извлечение строк что-то испортило
в разметке, здесь это видно сразу и с точным местом.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL_DIR = ROOT / "src" / "templates"
STRINGS = ROOT / "src" / "i18n" / "strings.json"

PLACEHOLDER_RE = re.compile(r"\{\{([0-9a-f]{8})\}\}")


def render_ru(tpl: str, strings: dict) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key not in strings:
            raise KeyError(key)
        return strings[key]["src"]

    return PLACEHOLDER_RE.sub(repl, tpl)


def first_diff(a: str, b: str) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            lo = max(0, i - 60)
            return (
                f"позиция {i} (строка {a[:i].count(chr(10)) + 1})\n"
                f"        оригинал: …{a[lo:i + 60]!r}\n"
                f"        сборка:   …{b[lo:i + 60]!r}"
            )
    return f"длина: оригинал {len(a)}, сборка {len(b)}"


def main() -> int:
    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    failures = 0
    checked = 0

    for tpl_path in sorted(TPL_DIR.glob("*.html")):
        original_path = ROOT / tpl_path.name
        if not original_path.exists():
            continue
        checked += 1
        original = original_path.read_text(encoding="utf-8")
        try:
            rebuilt = render_ru(tpl_path.read_text(encoding="utf-8"), strings)
        except KeyError as e:
            print(f"  ✗ {tpl_path.name}: в словаре нет ключа {e}")
            failures += 1
            continue

        if rebuilt == original:
            print(f"  ✓ {tpl_path.name}")
        else:
            print(f"  ✗ {tpl_path.name}: {first_diff(original, rebuilt)}")
            failures += 1

    print()
    if failures:
        print(f"РАСХОЖДЕНИЯ: {failures} из {checked} страниц")
        return 1
    print(f"round-trip чистый: {checked} страниц воспроизведены байт-в-байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
