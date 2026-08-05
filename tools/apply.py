#!/usr/bin/env python3
"""Заливает переводы в словарь.

    python3 tools/apply.py en < batch.tsv
    python3 tools/apply.py ka --status done < reviewed.tsv

Формат входа: «ключ<TAB>перевод», по строке на запись. Пустые строки и
строки, начинающиеся с #, игнорируются.

Ничего не затирает молча: если у ключа уже есть перевод и он отличается,
это показывается в отчёте.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STRINGS = ROOT / "src" / "i18n" / "strings.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("lang", choices=["ka", "en"])
    ap.add_argument("--status", default="draft", choices=["draft", "done"],
                    help="draft — ждёт вычитки носителем, done — вычитано")
    args = ap.parse_args()

    strings = json.loads(STRINGS.read_text(encoding="utf-8"))
    applied = replaced = unknown = 0
    problems = []

    for raw in sys.stdin:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" not in line:
            problems.append(f"нет табуляции: {line[:70]}")
            continue
        key, value = line.split("\t", 1)
        key, value = key.strip(), value.strip()
        entry = strings.get(key)
        if entry is None:
            problems.append(f"ключа нет в словаре: {key}")
            unknown += 1
            continue
        prev = (entry.get(args.lang) or "").strip()
        if prev and prev != value:
            problems.append(f"{key}: заменён прежний перевод\n      было: {prev}\n      стало: {value}")
            replaced += 1
        entry[args.lang] = value
        # Статус хранится отдельно на язык: английский может быть готов,
        # пока грузинский ещё ждёт носителя.
        entry[f"st_{args.lang}"] = args.status
        applied += 1

    STRINGS.write_text(
        json.dumps(strings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    total = len(strings)
    done = sum(1 for e in strings.values() if (e.get(args.lang) or "").strip())
    print(f"применено: {applied} (заменено: {replaced}, неизвестных ключей: {unknown})")
    print(f"покрытие {args.lang}: {done}/{total} ({done * 100 // total}%)")
    if problems:
        print("\nтребует внимания:")
        for p in problems:
            print(f"  • {p}")
    return 1 if unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
