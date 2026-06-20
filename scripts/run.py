"""
run.py – Orchestrator for the EVE Online localization archive pipeline.

Usage:
  python scripts/run.py TQ
  python scripts/run.py SISI
  python scripts/run.py TQ SISI         # process both
  python scripts/run.py TQ --force      # re-download even if hash unchanged

Steps:
  1. fetch   – detect new builds, download changed pickles
  2. backup  – copy current latest JSON to a temp dir (for diffing)
  3. merge   – export updated JSON files
  4. changelog – generate changes.md and update cumulative changelog
  5. release – create GitHub Release with assets
  6. commit  – handled externally by the GitHub Actions workflow
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Make sure sibling scripts are importable regardless of cwd
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import fetch as fetch_module
import merge as merge_module
import changelog as changelog_module
import release as release_module

ROOT = SCRIPTS_DIR.parent
LATEST_DIR = ROOT / "latest"


def backup_latest(server: str) -> Path:
    """Copy latest/{server}/ to a temp dir and return its path."""
    src = LATEST_DIR / server.lower()
    tmp = Path(tempfile.mkdtemp(prefix=f"eve_prev_{server.lower()}_"))
    if src.exists():
        shutil.copytree(src, tmp / server.lower())
        return tmp / server.lower()
    return tmp  # empty dir – first run


def process_server(server: str, force: bool = False) -> bool:
    """
    Run the full pipeline for *server*.

    Returns True if a release was created.
    """
    server = server.upper()
    print(f"\n{'='*60}")
    print(f"  Processing {server}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------
    # 1. Fetch
    # ------------------------------------------------------------------
    result = fetch_module.fetch_server(server, force=force)
    build = result["build"]
    changed = result["changed"]

    if not changed:
        print(f"[{server}] No localization changes detected. Done.")
        return False

    changed_langs = list(changed.keys())
    print(f"[{server}] Changed languages: {changed_langs}")

    # ------------------------------------------------------------------
    # 2. Backup current JSON for diffing
    # ------------------------------------------------------------------
    old_json_dir = backup_latest(server)

    # ------------------------------------------------------------------
    # 3. Merge pickles → JSON
    # ------------------------------------------------------------------
    # If English changed, merge it first so other languages can reference it
    exported = merge_module.export_changed(server, changed)
    print(f"[{server}] Exported {len(exported)} JSON files.")

    # ------------------------------------------------------------------
    # 4. Changelog
    # ------------------------------------------------------------------
    changes_path = ROOT / "changes.md"
    summary, md, diffs = changelog_module.generate_changelog(
        server,
        build,
        changed_langs,
        old_json_dir=old_json_dir,
    )

    if md:
        # changes.md (release artifact) contains the full diff including Details
        changes_path.write_text(md, encoding="utf-8")
        print(f"[{server}] Wrote {changes_path}")

        # Cumulative repo changelog also stores the full content
        cumulative_path = ROOT / f"CHANGELOG_{server}.md"
        changelog_module.prepend_to_changelog(cumulative_path, md)
        print(f"[{server}] Updated {cumulative_path}")
    else:
        print(f"[{server}] No diff content generated (possibly first run).")

    # ------------------------------------------------------------------
    # 5. GitHub Release
    # ------------------------------------------------------------------
    if os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPO"):
        # Release body = summary table only; full diff is in the changes.md asset
        body = summary or f"Localization update for {server} build {build}."
        url = release_module.create_release(
            server,
            build,
            changed_langs,
            changes_md_path=changes_path if md else None,
            body=body,
        )
        print(f"[{server}] Release created: {url}")
    else:
        msg = (f"\033[33m[{server}] [NOTICE] Skipping GitHub Release "
               f"(GITHUB_TOKEN or GITHUB_REPO not set).\033[0m")
        print(msg, file=sys.stderr)

    # Cleanup temp backup
    shutil.rmtree(old_json_dir.parent, ignore_errors=True)

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="EVE localization archive pipeline.")
    parser.add_argument(
        "servers",
        nargs="+",
        choices=["TQ", "SISI", "tq", "sisi"],
        help='Servers to process, e.g. "TQ SISI"',
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download all languages regardless of hash",
    )
    args = parser.parse_args()

    any_released = False
    for server in args.servers:
        released = process_server(server.upper(), force=args.force)
        any_released = any_released or released

    sys.exit(
        0 if any_released else 0)  # always exit 0; GH Actions checks outputs
