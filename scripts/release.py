"""
release.py – Create GitHub Releases with localization JSON assets.

Requires environment variables:
  GITHUB_TOKEN   – Personal access token or Actions token
  GITHUB_REPO    – owner/repo, e.g. "your-org/eve-localization-archive"

Only languages that actually changed are uploaded as release assets.
The changes.md file is always included when provided.
"""

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
LATEST_DIR = ROOT / "latest"


def _api_headers() -> dict:
    if token := os.environ.get("GITHUB_TOKEN"):
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    else:
        raise RuntimeError("GITHUB_TOKEN environment variable not set.")


def _repo() -> str:
    if repo := os.environ.get("GITHUB_REPO"):
        return repo
    else:
        raise RuntimeError("GITHUB_REPO environment variable not set.")


def create_release(
    server: str,
    build: int,
    changed_langs: list[str],
    changes_md_path=None,
    body: str = "",
    draft: bool = False,
) -> str:
    """
    Create a GitHub Release and upload assets.

    Tag format: tq-{build} / sisi-{build}

    Returns the HTML URL of the created release.
    """
    repo = _repo()
    headers = _api_headers()
    server_lower = server.lower()

    tag = f"{server_lower}-{build}"
    release_name = f"EVE Localization {server.upper()} Build {build}"

    api_base = f"https://api.github.com/repos/{repo}"
    create_url = f"{api_base}/releases"

    payload = {
        "tag_name": tag,
        "name": release_name,
        "body": body
        or f"Localization update for {server.upper()} build {build}.",
        "draft": draft,
        "prerelease": (server_lower == "sisi"),
    }

    # ------------------------------------------------------------------
    # Create release (with orphan-tag recovery)
    # ------------------------------------------------------------------
    r = requests.post(create_url, headers=headers, json=payload, timeout=30)

    if r.status_code == 422:
        # Log the raw body so we can diagnose unexpected cases.
        print(f"POST /releases returned 422: {r.text}")

        # Two possible causes:
        #   (a) A release already exists for this tag  → GET /releases/tags/{tag} returns 200
        #   (b) The git tag exists but has no release  → GET /releases/tags/{tag} returns 404
        #       (happens when the release is deleted from the UI without deleting the tag)
        r2 = requests.get(f"{api_base}/releases/tags/{tag}",
                          headers=headers,
                          timeout=30)
        print(f"GET /releases/tags/{tag} → HTTP {r2.status_code}")

        if r2.status_code == 200:
            # Case (a): reuse the existing release
            print(f"Release {tag} already exists, reusing.")
            release = r2.json()

        elif r2.status_code == 404:
            # Case (b): orphan git tag — delete it and retry
            print(
                f"Orphan git tag '{tag}' found (tag exists but no release attached). "
                "Deleting tag ref and retrying release creation...")
            delete_url = f"{api_base}/git/refs/tags/{tag}"
            print(f"DELETE {delete_url}")
            r3 = requests.delete(delete_url, headers=headers, timeout=30)
            print(f"DELETE → HTTP {r3.status_code}  body: {r3.text!r}")

            if r3.status_code == 204:
                pass  # deleted successfully
            elif r3.status_code == 422:
                # Ref already gone (race condition) — safe to proceed
                print("Tag ref already absent (422 on DELETE); proceeding.")
            else:
                raise RuntimeError(
                    f"Unexpected response deleting tag ref '{tag}': "
                    f"HTTP {r3.status_code} — {r3.text}")

            # Retry release creation
            r = requests.post(create_url,
                              headers=headers,
                              json=payload,
                              timeout=30)
            if not r.ok:
                print(f"Retry POST /releases → HTTP {r.status_code}: {r.text}")
            r.raise_for_status()
            release = r.json()

        else:
            print(f"Unexpected GET status {r2.status_code}: {r2.text}")
            r2.raise_for_status()

    else:
        r.raise_for_status()
        release = r.json()

    upload_url = release["upload_url"].split("{")[
        0]  # strip URI template suffix
    html_url = release["html_url"]
    print(f"Release: {html_url}")

    # ------------------------------------------------------------------
    # Upload changed language JSON files
    # ------------------------------------------------------------------
    session = requests.Session()
    session.headers.update(headers)

    for lang in changed_langs:
        output_key = "en" if lang == "en-us" else lang
        json_path = LATEST_DIR / server_lower / f"{output_key}.json"
        if not json_path.exists():
            print(f"  WARNING: {json_path} not found, skipping.")
            continue

        asset_name = f"{output_key}_{build}.json"
        print(f"  Uploading {asset_name}...")
        with open(json_path, "rb") as f:
            data = f.read()
        r = session.post(
            f"{upload_url}?name={asset_name}",
            headers={"Content-Type": "application/json"},
            data=data,
            timeout=120,
        )
        r.raise_for_status()
        print(f"  ✓ {asset_name} uploaded ({len(data):,} bytes)")

    # ------------------------------------------------------------------
    # Upload changes.md
    # ------------------------------------------------------------------
    if changes_md_path and Path(changes_md_path).exists():
        print("  Uploading changes.md...")
        with open(changes_md_path, "rb") as f:
            data = f.read()
        r = session.post(
            f"{upload_url}?name=changes.md",
            headers={"Content-Type": "text/markdown"},
            data=data,
            timeout=60,
        )
        r.raise_for_status()
        print(f"  ✓ changes.md uploaded ({len(data):,} bytes)")

    return html_url


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Create GitHub Release for EVE localization.")
    parser.add_argument("server", choices=["TQ", "SISI", "tq", "sisi"])
    parser.add_argument("build", type=int)
    parser.add_argument("langs", nargs="+", help="Changed language codes")
    parser.add_argument("--changes", type=Path, help="Path to changes.md")
    parser.add_argument("--draft", action="store_true")
    args = parser.parse_args()

    url = create_release(
        args.server.upper(),
        args.build,
        args.langs,
        changes_md_path=args.changes,
        draft=args.draft,
    )
    print(f"Release URL: {url}")
