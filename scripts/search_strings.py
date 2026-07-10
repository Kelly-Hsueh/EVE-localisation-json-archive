"""
search_strings.py – Search EVE localisation JSON for a keyword and export matches to CSV.

Scans latest/{server}/{lang}.json files and finds entries whose text (in any
selected language, or a specific one) matches the given keyword.  Matches are
grouped by MessageID; the output CSV includes one row per MessageID with
columns for every language present in the archive for that server, so you
can see the English source alongside all translations.

Usage:
  # Plain substring match, all languages, TQ server
  python scripts/search_strings.py TQ "warp"

  # Case-sensitive regex match, only en + zh
  python scripts/search_strings.py TQ "Warp.*Cyno" --regex --lang en,zh

  # Custom output path
  python scripts/search_strings.py SISI "跃迁" -o cyno_strings.csv

Output CSV columns:
  message_id, en, de, es, fr, it, ja, ko, ru, zh   (only languages found on disk)
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LATEST_DIR = ROOT / "latest"

# Preferred column order; any other language codes found on disk are appended
# alphabetically after these.
PREFERRED_LANG_ORDER = ["en", "de", "es", "fr", "it", "ja", "ko", "ru", "zh"]


def discover_languages(server_dir: Path,
                       requested: list[str] | None) -> list[str]:
    """Return the list of language keys to load, in stable column order."""
    available = sorted(p.stem for p in server_dir.glob("*.json"))
    if requested:
        if missing := [lang for lang in requested if lang not in available]:
            print(
                f"WARNING: requested language(s) not found on disk: {missing}",
                file=sys.stderr)
        langs = [lang for lang in requested if lang in available]
    else:
        langs = available

    ordered = [lang for lang in PREFERRED_LANG_ORDER if lang in langs]
    ordered += sorted(lang for lang in langs
                      if lang not in PREFERRED_LANG_ORDER)
    return ordered


def load_lang_json(server_dir: Path, lang: str) -> dict:
    path = server_dir / f"{lang}.json"
    return json.loads(path.read_text(
        encoding="utf-8")) if path.exists() else {}


def build_matcher(keyword: str, use_regex: bool, ignore_case: bool):
    if use_regex:
        flags = re.IGNORECASE if ignore_case else 0
        pattern = re.compile(keyword, flags)
        return lambda text: bool(pattern.search(text))
    if ignore_case:
        needle = keyword.lower()
        return lambda text: needle in text.lower()
    return lambda text: keyword in text


def search(server: str, keyword: str, languages: list[str] | None,
           use_regex: bool, ignore_case: bool) -> tuple[list[str], list[dict]]:
    """
    Returns (column_langs, rows) where each row is
    {"message_id": str, lang: text, ...} for every matching MessageID.
    """
    server_dir = LATEST_DIR / server.lower()
    if not server_dir.exists():
        raise FileNotFoundError(f"No archive found at {server_dir}")

    all_langs = discover_languages(server_dir, None)
    search_langs = discover_languages(server_dir,
                                      languages) if languages else all_langs

    # Load every language file once (needed for full-row context even if we
    # only *search* a subset of languages).
    data = {lang: load_lang_json(server_dir, lang) for lang in all_langs}

    matcher = build_matcher(keyword, use_regex, ignore_case)

    # Union of all MessageIDs across languages
    all_ids = set()
    for lang_data in data.values():
        all_ids.update(lang_data.keys())

    matched_ids = set()
    for msg_id in all_ids:
        for lang in search_langs:
            entry = data[lang].get(msg_id)
            if not entry:
                continue
            # entries store {"en": ..., "{lang}": ...}; for lang=="en" the
            # field key is "en" in every file.
            text = entry.get("en", "") if lang == "en" else entry.get(lang, "")
            if text and matcher(text):
                matched_ids.add(msg_id)
                break

    def sort_key(mid: str):
        try:
            return (0, int(mid))
        except ValueError:
            return (1, mid)

    rows = []
    for msg_id in sorted(matched_ids, key=sort_key):
        row = {"message_id": msg_id}
        for lang in all_langs:
            entry = data[lang].get(msg_id, {})
            row[lang] = entry.get("en", "") if lang == "en" else entry.get(
                lang, "")
        rows.append(row)

    return all_langs, rows


def write_csv(path: Path, langs: list[str], rows: list[dict]) -> None:
    fieldnames = ["message_id"] + langs
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search EVE localisation archive for "
        "a keyword and export matches to CSV.")
    parser.add_argument("server", choices=["TQ", "SISI", "tq", "sisi"])
    parser.add_argument("keyword",
                        help="Substring or regex pattern to search for")
    parser.add_argument(
        "--regex",
        action="store_true",
        help="Treat keyword as a regular expression (default: plain substring)"
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Case-sensitive match (default: case-insensitive)")
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        help="Comma-separated language codes to search in, e.g. 'en,zh' "
        "(default: search all available languages)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: {server}_{keyword}_matches.csv)")
    args = parser.parse_args()

    server = args.server.upper()
    requested_langs = [lang.strip().lower()
                       for lang in args.lang.split(",")] if args.lang else None

    langs, rows = search(
        server,
        args.keyword,
        requested_langs,
        use_regex=args.regex,
        ignore_case=not args.case_sensitive,
    )

    if not rows:
        print("No matches found.")
        return

    if args.output:
        out_path = args.output
    else:
        safe_kw = re.sub(r"[^\w-]+", "_", args.keyword)[:40]
        out_path = ROOT / f"{server.lower()}_{safe_kw}_matches.csv"

    write_csv(out_path, langs, rows)
    print(f"Matched {len(rows)} MessageID(s). Wrote → {out_path}")


if __name__ == "__main__":
    main()
