"""
fetch.py – Download EVE Online localisation pickle files for TQ and SISI.

Flow per server:
  1. GET eveclient_{SERVER}.json → build number
  2. GET eveonline_{build}.txt   → locate resfileindex entry
  3. Download resfileindex        → parse localisation entries
  4. Compare hashes against state/{server}-hashes.json
  5. Download only languages whose hash changed
  6. Return metadata for downstream steps
"""

import json
import re
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_BINARY = "https://binaries.eveonline.com"
BASE_RESOURCE = "https://resources.eveonline.com"

LANGUAGES = ["de", "en-us", "fr", "ja", "ko", "ru", "zh", "es", "it"]

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
PICKLES_DIR = ROOT / "pickles"

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "eve-localization-archive/1.0"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_json(url: str) -> dict:
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def get_text(url: str) -> str:
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def get_bytes(url: str) -> bytes:
    r = SESSION.get(url, timeout=60, stream=True)
    r.raise_for_status()
    return r.content


# ---------------------------------------------------------------------------
# Build number
# ---------------------------------------------------------------------------


def get_build(server: str) -> int:
    data = get_json(f"{BASE_BINARY}/eveclient_{server}.json")
    return int(data["build"])


# ---------------------------------------------------------------------------
# resfileindex helpers
# ---------------------------------------------------------------------------


def get_resfileindex_url(build: int) -> str:
    """Parse eveonline_{build}.txt and return the resfileindex download URL."""
    manifest_url = f"{BASE_BINARY}/eveonline_{build}.txt"
    text = get_text(manifest_url)
    for line in text.splitlines():
        if line.startswith("app:/resfileindex.txt"):
            # format: app:/resfileindex.txt,<download_path>,<hash>,<size1>,<size2>
            parts = line.strip().split(",")
            if len(parts) >= 2:
                return f"{BASE_BINARY}/{parts[1]}"
    raise RuntimeError(
        f"app:/resfileindex.txt entry not found in build manifest {build}")


# Language codes that appear in the resfileindex but are NOT real localisations.
# "main" is a known internal entry; add others here if they appear in future builds.
_NON_LANGUAGE_ENTRIES = frozenset({"main"})


def parse_resfileindex(content: str) -> dict[str, dict]:
    """
    Return a dict keyed by language code, e.g. "zh", with values:
      { "resource_path": str, "download_path": str, "hash": str }

    Entries whose language code is in _NON_LANGUAGE_ENTRIES are silently skipped.
    Any other unrecognised code is warned about but still included so new CCP
    languages are not silently dropped.
    """
    entries = {}
    pattern = re.compile(
        r"res:/localizationfsd/localization_fsd_([a-z\-]+)\.pickle"
        r",([^,]+),([^,]+),",
        re.IGNORECASE,
    )
    for line in content.splitlines():
        if m := pattern.match(line):
            lang = m[1].lower()
            if lang in _NON_LANGUAGE_ENTRIES:
                print(
                    f"\033[31m[WARNING] Skipping non-language entry: {lang}\033[0m",
                    file=sys.stderr)
                continue
            download_path = m[2]
            content_hash = m[3]
            resource_path = f"res:/localizationfsd/localization_fsd_{lang}.pickle"
            entries[lang] = {
                "resource_path": resource_path,
                "download_path": download_path,
                "hash": content_hash,
            }
    return entries


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def load_state_hashes(server: str) -> dict[str, str]:
    path = STATE_DIR / f"{server.lower()}-hashes.json"
    return json.loads(path.read_text()) if path.exists() else {}


def load_state_build(server: str) -> int | None:
    path = STATE_DIR / f"{server.lower()}-build.txt"
    return int(path.read_text().strip()) if path.exists() else None


def save_state_hashes(server: str, hashes: dict[str, str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{server.lower()}-hashes.json"
    path.write_text(json.dumps(hashes, indent=2))


def save_state_build(server: str, build: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{server.lower()}-build.txt"
    path.write_text(str(build))


# ---------------------------------------------------------------------------
# Main fetch routine
# ---------------------------------------------------------------------------


def fetch_server(server: str, force: bool = False) -> dict:
    """
    Fetch localisation data for *server* ("TQ" or "SISI").

    Returns:
      {
        "server": str,
        "build": int,
        "changed": { lang: { "pickle_path": Path, "hash": str } },
        "all_hashes": { lang: str },
      }
    """
    server = server.upper()
    print(f"[{server}] Checking build...")
    build = get_build(server)
    print(f"[{server}] Build: {build}")

    prev_build = load_state_build(server)
    prev_hashes = load_state_hashes(server)

    if not force and prev_build == build:
        print(f"[{server}] Build {build} unchanged, skipping.")
        return {
            "server": server,
            "build": build,
            "changed": {},
            "all_hashes": prev_hashes
        }

    print(f"[{server}] Fetching resfileindex for build {build}...")
    resfileindex_url = get_resfileindex_url(build)
    resfileindex_content = get_text(resfileindex_url)
    entries = parse_resfileindex(resfileindex_content)

    print(f"[{server}] Found {len(entries)} localisation entries.")

    changed = {}
    new_hashes = {lang: info["hash"] for lang, info in entries.items()}

    for lang, info in entries.items():
        new_hash = info["hash"]
        old_hash = prev_hashes.get(lang)

        if not force and old_hash == new_hash:
            print(f"[{server}] {lang}: hash unchanged, skipping.")
            continue

        print(
            f"[{server}] {lang}: hash changed ({old_hash} → {new_hash}), downloading..."
        )

        download_url = f"{BASE_RESOURCE}/{info['download_path']}"
        data = get_bytes(download_url)

        # Derive filename from resource path (always preserve original name)
        filename = info["resource_path"].split("/")[
            -1]  # localization_fsd_zh.pickle

        out_dir = PICKLES_DIR / server.lower()
        out_dir.mkdir(parents=True, exist_ok=True)
        pickle_path = out_dir / filename
        pickle_path.write_bytes(data)

        print(f"[{server}] {lang}: saved {len(data):,} bytes → {pickle_path}")
        changed[lang] = {"pickle_path": pickle_path, "hash": new_hash}

    # Persist state
    save_state_build(server, build)
    save_state_hashes(server, new_hashes)

    return {
        "server": server,
        "build": build,
        "changed": changed,
        "all_hashes": new_hashes,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch EVE localisation pickles.")
    parser.add_argument("server", choices=["TQ", "SISI", "tq", "sisi"])
    parser.add_argument("--force",
                        action="store_true",
                        help="Re-download all regardless of hash")
    args = parser.parse_args()

    result = fetch_server(args.server.upper(), force=args.force)
    print(
        json.dumps(
            {
                k: (str(v) if isinstance(v, Path) else v)
                for k, v in result.items() if k != "changed"
            },
            indent=2,
        ))
    if result["changed"]:
        msg = f"\033[32m[SUCCESS] Changed languages: {list(result['changed'].keys())}\033[0m"
        print(msg, file=sys.stderr)
    else:
        print("\033[33m[NOTICE] No languages changed.\033[0m", file=sys.stderr)
