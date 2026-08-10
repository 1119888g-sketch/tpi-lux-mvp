#!/usr/bin/env python3
"""Сведение четырёх переводов в один результат и отбор строк для носителя.

    python3 tools/mt_merge.py [--write]

Четыре независимых варианта на строку:
    claude   Claude, перевод с русского      ← основной
    codex    Codex,  перевод с русского
    claude-en  Claude, перевод с английского ← обратная сверка через второй язык
    codex-en   Codex,  перевод с английского

Логика простая: русский и английский — два разных описания одного смысла.
Если независимые переводы с двух языков сошлись, ошибиться всем сразу трудно —
такую строку носителю показывать незачем. Расхождение почти всегда означает
двусмысленность в оригинале или термин без устоявшегося перевода.

--write кладёт основной вариант в src/i18n/strings.json:
    st_ka = "mt-agreed"  переводы сошлись, носителю не показываем
    st_ka = "mt"         ушло к носителю на проверку
"""
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import ENTITY_RE, LATIN_OK, WORD_RE, scripts_in  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MT = ROOT / ".mt"
STRINGS = ROOT / "src" / "i18n" / "strings.json"
MERGED = MT / "merged.json"

AGREE = 0.75           # выше — считаем, что варианты говорят одно и то же
NEED_CONFIRMATIONS = 2  # столько независимых подтверждений закрывают строку
PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
GEO_VOWELS = "აეიოუ"


def load_json_loose(path):
    """Терпимый парсер: срезает markdown-ограду и мусор вокруг массива."""
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def collect(pattern):
    out = {}
    for path in sorted(MT.glob(pattern)):
        items = load_json_loose(path)
        if items is None:
            print(f"  ⚠ не разобрался: {path.name}")
            continue
        for it in items:
            if isinstance(it, dict) and it.get("id") and (it.get("ka") or "").strip():
                out[it["id"]] = it["ka"].strip()
    return out


def defects(text, src, limit):
    """Ошибки, которые ловит check.py, плюс превышение лимита UI."""
    bad = []
    for m in WORD_RE.finditer(text):
        word, s = m.group(), scripts_in(m.group())
        if "GEO" in s and "CYR" in s:
            bad.append(f"смешение письма: «{word}»")
        elif "GEO" in s and "LAT" in s and word.lower() not in LATIN_OK:
            bad.append(f"мхедрули+латиница: «{word}»")
    cyr = [w for w in WORD_RE.findall(text) if scripts_in(w) == {"CYR"}]
    if cyr and text.strip() != src.strip():
        bad.append("остались русские слова: " + ", ".join(cyr[:4]))
    if sorted(ENTITY_RE.findall(src)) != sorted(ENTITY_RE.findall(text)):
        bad.append("HTML-сущности не совпали")
    if not any(s == "GEO" for w in WORD_RE.findall(text) for s in scripts_in(w)):
        bad.append("грузинского текста нет вовсе")
    if limit and len(text) > limit:
        bad.append(f"длиннее лимита: {len(text)} > {limit}")
    return bad


def norm(text):
    text = unicodedata.normalize("NFC", text.lower())
    return " ".join(PUNCT_RE.sub(" ", text).split())


def geo_stem(word):
    while len(word) > 4 and word[-1] in GEO_VOWELS:
        word = word[:-1]
    return word


def similarity(a, b):
    """Порядок слов в грузинском свободный, окончания меняются — поэтому
    к посимвольному сравнению добавляем пересечение основ и берём лучшее."""
    if not a or not b:
        return 0.0
    na, nb = norm(a), norm(b)
    if na == nb:
        return 1.0
    chars = SequenceMatcher(None, na, nb).ratio()
    sa = {geo_stem(w) for w in na.split()}
    sb = {geo_stem(w) for w in nb.split()}
    jaccard = len(sa & sb) / len(sa | sb) if sa | sb else 0.0
    return max(chars, jaccard)


def main():
    write = "--write" in sys.argv
    batches, en_src = {}, {}
    for path in sorted(MT.glob("batch-[0-9]*.json")):
        for it in json.loads(path.read_text(encoding="utf-8")):
            batches[it["id"]] = it
    for path in sorted(MT.glob("batch-en-[0-9]*.json")):
        for it in json.loads(path.read_text(encoding="utf-8")):
            en_src[it["id"]] = it["src"]

    variants = {
        "claude": collect("out-claude-[0-9]*.json"),
        "codex": collect("out-codex-[0-9]*.raw"),
        "claude-en": collect("out-claude-en-*.json"),
        "codex-en": collect("out-codex-en-*.raw"),
    }
    print("строк: {}   ".format(len(batches))
          + "   ".join(f"{k}: {len(v)}" for k, v in variants.items()))

    data = json.loads(STRINGS.read_text(encoding="utf-8"))
    merged = {}
    stats = {"agreed": 0, "review": 0, "defect": 0, "no_en": 0}
    for key in list(batches) + [k for k in en_src if k not in batches]:
        item = batches.get(key, {})
        src = item.get("src") or data[key]["src"]
        limit = item.get("limit")
        got = {name: v.get(key, "") for name, v in variants.items()}
        bad = {name: defects(text, src, limit) if text else ["нет варианта"]
               for name, text in got.items()}

        # основной берём из перевода с русского: русский текст — первоисточник
        primary, engine = "", "none"
        for name in ("claude", "codex"):
            if got[name] and not bad[name]:
                primary, engine = got[name], name
                break
        if not primary:
            for name in ("claude", "codex"):
                if got[name]:
                    primary, engine = got[name], name
                    break
        if not primary:
            # строка переведена раньше и в машинный прогон не попала —
            # сверяем существующий перевод обратной парой с английского
            primary = (data.get(key, {}).get("ka") or "").strip()
            engine = "было" if primary else "none"

        sims = {name: round(similarity(primary, text), 2)
                for name, text in got.items() if name != engine and text}
        confirmations = sum(1 for s in sims.values() if s >= AGREE)
        cross = [n for n in ("claude-en", "codex-en") if sims.get(n, 0) >= AGREE]

        reasons = []
        if bad.get(engine):
            reasons.append("дефект: " + "; ".join(bad[engine]))
            stats["defect"] += 1
        if not got["claude-en"] and not got["codex-en"]:
            reasons.append("нет обратной сверки с английского")
            stats["no_en"] += 1
        elif not cross:
            reasons.append("перевод с русского и с английского разошлись")
        if got["claude"] and got["codex"] and not any(
            s >= AGREE for n, s in sims.items() if n in ("claude", "codex")
        ):
            reasons.append("движки разошлись между собой")
        if confirmations < NEED_CONFIRMATIONS and not reasons:
            reasons.append("мало совпадений между вариантами")

        review = bool(reasons)
        stats["review" if review else "agreed"] += 1
        merged[key] = {
            "src": src,
            "en": en_src.get(key, ""),
            **got,
            "primary": primary,
            "engine": engine,
            "sims": sims,
            "confirmations": confirmations,
            "review": review,
            "reasons": reasons,
        }

    MERGED.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = len(batches)
    print(f"\nсошлись, носителю не нужны:  {stats['agreed']:4d}  ({stats['agreed'] * 100 // total}%)")
    print(f"на проверку носителю:        {stats['review']:4d}  ({stats['review'] * 100 // total}%)")
    print(f"  из них с дефектом:         {stats['defect']:4d}")
    print(f"  без обратной сверки:       {stats['no_en']:4d}")
    print(f"записано: {MERGED.relative_to(ROOT)}")

    if not write:
        print("\n(--write, чтобы положить основной вариант в strings.json)")
        return

    data = json.loads(STRINGS.read_text(encoding="utf-8"))
    n = 0
    for key, m in merged.items():
        if m["primary"] and key in data:
            data[key]["ka"] = m["primary"]
            data[key]["st_ka"] = "mt" if m["review"] else "mt-agreed"
            n += 1
    STRINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"в strings.json записано: {n}")


if __name__ == "__main__":
    main()
