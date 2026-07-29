"""
release.py – Create GitHub Releases with localization JSON assets.

Requires environment variables:
  GITHUB_TOKEN  – Personal access token or Actions token
  GITHUB_REPO   – owner/repo, e.g. "Kelly-Hsueh/EVE-Localisation-Archive"

Only languages that actually changed are uploaded as release assets.
changes_{build}.md is always included when provided.
"""

import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
LATEST_DIR = ROOT / "latest"

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _api_headers() -> dict:
    if token := os.environ.get("GITHUB_TOKEN"):
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    raise RuntimeError("GITHUB_TOKEN environment variable not set.")


def _repo() -> str:
    if repo := os.environ.get("GITHUB_REPO"):
        return repo
    raise RuntimeError("GITHUB_REPO environment variable not set.")


# ---------------------------------------------------------------------------
# Release creation helpers
# ---------------------------------------------------------------------------


def _delete_orphan_tag(api_base: str, headers: dict, tag: str) -> None:
    """Delete a git tag ref that has no release attached."""
    delete_url = f"{api_base}/git/refs/tags/{tag}"
    print(f"DELETE {delete_url}")
    r = requests.delete(delete_url, headers=headers, timeout=30)
    print(f"DELETE → HTTP {r.status_code}  body: {r.text!r}")
    if r.status_code == 204:
        return
    if r.status_code == 422:
        # Already gone — safe to proceed
        print("Tag ref already absent (422 on DELETE); proceeding.")
        return
    raise RuntimeError(f"Unexpected response deleting tag ref '{tag}': "
                       f"HTTP {r.status_code} — {r.text}")


def _ensure_release(api_base: str, headers: dict, tag: str,
                    payload: dict) -> dict:
    """
    Create a GitHub Release, recovering from two 422 edge cases:
      (a) Release already exists for this tag  → reuse it.
      (b) Orphan git tag with no release       → delete the tag ref and retry.
    Returns the release dict.
    """
    create_url = f"{api_base}/releases"
    r = requests.post(create_url, headers=headers, json=payload, timeout=30)

    if r.status_code != 422:
        r.raise_for_status()
        return r.json()

    print(f"POST /releases returned 422: {r.text}")
    r2 = requests.get(f"{api_base}/releases/tags/{tag}",
                      headers=headers,
                      timeout=30)
    print(f"GET /releases/tags/{tag} → HTTP {r2.status_code}")

    if r2.status_code == 200:
        print(f"Release {tag} already exists, reusing.")
        return r2.json()

    if r2.status_code == 404:
        print(f"Orphan git tag '{tag}' found (no release attached). "
              "Deleting tag ref and retrying...")
        _delete_orphan_tag(api_base, headers, tag)
        r = requests.post(create_url,
                          headers=headers,
                          json=payload,
                          timeout=30)
        if not r.ok:
            print(f"Retry POST /releases → HTTP {r.status_code}: {r.text}")
        r.raise_for_status()
        return r.json()

    print(f"Unexpected GET status {r2.status_code}: {r2.text}")
    r2.raise_for_status()
    return {}  # unreachable; satisfies type checkers


# ---------------------------------------------------------------------------
# Asset upload helpers
# ---------------------------------------------------------------------------


def _upload_asset(
    session: requests.Session,
    upload_url: str,
    name: str,
    data: bytes,
    content_type: str,
) -> None:
    r = session.post(
        f"{upload_url}?name={name}",
        headers={"Content-Type": content_type},
        data=data,
        timeout=120,
    )
    r.raise_for_status()
    print(f"  ✓ {name} ({len(data):,} bytes)")


def _upload_assets(
    release: dict,
    headers: dict,
    server_lower: str,
    build: int,
    changed_langs: list[str],
    changes_md_path,
) -> None:
    upload_url = release["upload_url"].split("{")[0]
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
        _upload_asset(session, upload_url, asset_name, json_path.read_bytes(),
                      "application/json")

    if changes_md_path and (md_path := Path(changes_md_path)).exists():
        asset_name = f"changes_{build}.md"
        print(f"  Uploading {asset_name}...")
        _upload_asset(session, upload_url, asset_name, md_path.read_bytes(),
                      "text/markdown")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _publish_release(api_base: str, headers: dict, release_id: int) -> None:
    """Flip draft → published after all assets are uploaded."""
    r = requests.patch(
        f"{api_base}/releases/{release_id}",
        headers=headers,
        json={"draft": False},
        timeout=30,
    )
    r.raise_for_status()
    print(f"Release published (id={release_id}).")


def create_release(
    server: str,
    build: int,
    changed_langs: list[str],
    changes_md_path=None,
    body: str = "",
    draft: bool = False,
) -> str:
    repo = _repo()
    headers = _api_headers()
    server_lower = server.lower()
    tag = f"{server_lower}-{build}"

    payload = {
        "tag_name": tag,
        "name": f"{server.upper()} Build {build}",
        "body": body
        or f"Localization update for {server.upper()} build {build}.",
        "draft": True,
        "prerelease": server_lower == "sisi",
    }

    api_base = f"https://api.github.com/repos/{repo}"
    release = _ensure_release(api_base, headers, tag, payload)

    print(f"Draft release created: {release['html_url']}")
    _upload_assets(release, headers, server_lower, build, changed_langs,
                   changes_md_path)

    if not draft:
        _publish_release(api_base, headers, release["id"])

    return release["html_url"]


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
    parser.add_argument("--changes",
                        type=Path,
                        help="Path to changes_{build}.md")
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
