#!/usr/bin/env python3
"""Нарезка непереведённых строк на батчи для машинного перевода.

    python3 tools/mt_batch.py [размер_батча] [--from en]

Кладёт в .mt/batch-NN.json пачки вида
    {"id": "...", "src": "...", "where": "...", "page": "...", "limit": 42}
и .mt/glossary.txt — свод терминов, который подмешивается в каждый промпт.

`--from en` кладёт .mt/batch-en-NN.json, где в "src" английский текст: это
независимая проверка перевода через второй исходный язык. Переводчик такого
батча русского не видит, поэтому совпадение результатов что-то значит.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xlsx_export import CYRILLIC_RE, PAGE_ORDER, PAGE_TITLES, build_rows, scan_templates  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MT = ROOT / ".mt"
UI_MAX_SRC, UI_GROWTH = 30, 1.7  # те же пороги, что в check.py


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    size = int(argv[0]) if argv else 40
    from_en = "--from" in sys.argv and "en" in sys.argv
    prefix = "batch-en" if from_en else "batch"

    data = json.loads((ROOT / "src/i18n/strings.json").read_text(encoding="utf-8"))
    glossary = json.loads((ROOT / "src/i18n/glossary.json").read_text(encoding="utf-8"))
    rows = build_rows(data, scan_templates())

    todo = []
    for r in rows:
        entry = data[r["id"]]
        # при переводе с английского строки уже переведены машинно — берём все,
        # кроме непереводимых (бренды, адреса) и тех, где нет английского
        if not from_en and (entry.get("ka") or "").strip():
            continue
        if not CYRILLIC_RE.search(r["src"]):
            continue
        source = (entry.get("en") or "").strip() if from_en else r["src"]
        if not source:
            continue
        item = {"id": r["id"], "page": r["group"], "where": r["where"], "src": source}
        if len(r["src"]) <= UI_MAX_SRC:
            item["limit"] = int(max(len(r["src"]) * UI_GROWTH, len(r["src"]) + 6))
        todo.append(item)

    MT.mkdir(exist_ok=True)
    for old in MT.glob(f"{prefix}-[0-9]*.json"):
        old.unlink()

    batches = [todo[i:i + size] for i in range(0, len(todo), size)]
    for n, batch in enumerate(batches, start=1):
        (MT / f"{prefix}-{n:02d}.json").write_text(
            json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    terms = [t for t in glossary.get("terms", []) if t.get("ka")]
    (MT / "glossary.txt").write_text(
        "\n".join(f"{t['ru']} = {t['ka']}" for t in terms) + "\n", encoding="utf-8"
    )
    print(f"строк к переводу: {len(todo)}, батчей: {len(batches)} по {size}, терминов: {len(terms)}")


if __name__ == "__main__":
    main()
