"""
merge.py – Export merged language JSON files from pickle data.

For each changed language, merge it with the English (en-us) pickle and write:
  latest/{server}/{lang}.json

JSON schema per entry:
  { "en": "...", "{lang}": "..." }

If lang IS en-us the output is:
  { "en": "..." }

Based on merge_zh_en.py reference implementation.
"""

import json
import pickle
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICKLES_DIR = ROOT / "pickles"
LATEST_DIR = ROOT / "latest"

# ---------------------------------------------------------------------------
# Pickle loading
# ---------------------------------------------------------------------------


def load_pickle(path: Path) -> dict:
    """Load a localisation pickle and return the message dict."""
    with open(path, "rb") as f:
        raw = pickle.load(f)
    return raw[1]


def extract_text(value) -> str:
    """Normalise a pickle value to a plain string."""
    if value is None:
        return ""
    if isinstance(value, tuple):
        return value[0] if value and value[0] is not None else ""
    return str(value)


# ---------------------------------------------------------------------------
# Core merge
# ---------------------------------------------------------------------------


def merge_lang_en(lang: str, lang_pickle: Path, en_pickle: Path) -> dict:
    """
    Merge *lang* data with English.

    Returns dict keyed by str(msg_id):
      { "en": "...", "{lang_key}": "..." }

    lang_key is normalised: "en-us" → "en", everything else unchanged.
    """
    lang_data = load_pickle(lang_pickle)

    if lang == "en-us":
        # For English itself just export the single field.
        merged = {}
        for msg_id in sorted(lang_data.keys()):
            en_text = extract_text(lang_data.get(msg_id, ""))
            merged[str(msg_id)] = {"en": en_text}
        return merged

    en_data = load_pickle(en_pickle)
    all_ids = set(lang_data.keys()) | set(en_data.keys())
    merged = {}
    for msg_id in sorted(all_ids):
        lang_text = extract_text(lang_data.get(msg_id))
        en_text = extract_text(en_data.get(msg_id))
        merged[str(msg_id)] = {"en": en_text, lang: lang_text}
    return merged


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_language(server: str, lang: str, pickle_path: Path) -> Path:
    """
    Export merged JSON for *lang* on *server*.

    Returns path to written JSON file.
    """
    server_lower = server.lower()
    en_pickle = PICKLES_DIR / server_lower / "localization_fsd_en-us.pickle"

    if lang != "en-us" and not en_pickle.exists():
        raise FileNotFoundError(f"English pickle not found at {en_pickle}. "
                                "Fetch en-us first or pass --force.")

    # Normalise output language key: en-us → en
    output_key = "en" if lang == "en-us" else lang

    merged = merge_lang_en(lang, pickle_path, en_pickle)

    out_dir = LATEST_DIR / server_lower
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{output_key}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=4)

    print(f"[{server}] Exported {len(merged):,} entries → {out_path}")
    return out_path


def export_changed(server: str, changed: dict) -> dict[str, Path]:
    """
    Export all changed languages.

    *changed* format:
      { lang: { "pickle_path": Path, "hash": str } }

    Returns { lang: output_path }
    """
    # If English changed we must re-export it so other languages get the right
    # base text.  But we also need the English pickle available for other
    # languages – make sure it exists.
    exported = {}

    # Export English first so it's available for other merges.
    if "en-us" in changed:
        info = changed["en-us"]
        out = export_language(server, "en-us", info["pickle_path"])
        exported["en"] = out

    for lang, info in changed.items():
        if lang == "en-us":
            continue
        out = export_language(server, lang, info["pickle_path"])
        exported[lang] = out

    return exported


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Merge EVE localisation pickles to JSON.")
    parser.add_argument("server", choices=["TQ", "SISI", "tq", "sisi"])
    parser.add_argument("lang", help='Language code, e.g. "zh", "ja", "en-us"')
    args = parser.parse_args()

    server = args.server.upper()
    lang = args.lang.lower()
    pickle_file = PICKLES_DIR / server.lower(
    ) / f"localization_fsd_{lang}.pickle"
    if not pickle_file.exists():
        print(f"Pickle not found: {pickle_file}")
        raise SystemExit(1)

    export_language(server, lang, pickle_file)
