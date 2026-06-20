"""
changelog.py – Generate Markdown changelogs for EVE localization updates.

Reads current latest/{server}/*.json files and compares them against the
previous versions from the GitHub Release for the previous build.

Output
------
A single Markdown file: changes.md (for release assets)
Appended section in:   CHANGELOG_TQ.md / CHANGELOG_SISI.md
"""

import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LATEST_DIR = ROOT / "latest"

TRUNC_LIMIT = 500  # characters before we truncate long strings

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def truncate(text: str) -> tuple[str, bool]:
    """Return (possibly-truncated text, was_truncated)."""
    if len(text) <= TRUNC_LIMIT:
        return text, False
    return text[:TRUNC_LIMIT], True


def fmt_block(lang_key: str, text: str, style: str = "text") -> str:
    """Render a fenced code block for *lang_key* and *text*."""
    display, was_truncated = truncate(text)
    lines = [f"{lang_key.upper()}", "", f"```{style}", display]
    if was_truncated:
        lines.append(f"(truncated, {len(text):,} chars total)")
    lines += ["```", ""]
    return "\n".join(lines)


def diff_block(lang_key: str, old: str, new: str) -> str:
    """Render a diff block for *lang_key*."""
    old_trunc, old_was = truncate(old)
    new_trunc, new_was = truncate(new)

    if old_was or new_was:
        # Too long – show plain blocks instead of diff
        return (
            f"{lang_key.upper()} (before)\n\n"
            f"```text\n{old_trunc}" +
            (f"\n(truncated, {len(old):,} chars total)" if old_was else "") +
            f"\n```\n\n"
            f"{lang_key.upper()} (after)\n\n"
            f"```text\n{new_trunc}" +
            (f"\n(truncated, {len(new):,} chars total)" if new_was else "") +
            "\n```\n")

    return (f"{lang_key.upper()}\n\n"
            f"```diff\n"
            f"- {old}\n"
            f"+ {new}\n"
            f"```\n")


# ---------------------------------------------------------------------------
# Load JSON helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(
        encoding="utf-8")) if path.exists() else {}


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def compute_diff(old: dict, new: dict, lang: str) -> dict:
    """
    Compare old and new merged JSON for *lang*.

    Both dicts are { msg_id: { "en": str, lang: str } }.

    Returns:
      {
        "added":     { msg_id: new_entry },
        "removed":   { msg_id: old_entry },
        "src_mod":   { msg_id: { "old": old_entry, "new": new_entry } },
        "tr_mod":    { msg_id: { "old": old_entry, "new": new_entry } },
      }
    """
    added = {}
    removed = {}
    src_mod = {}
    tr_mod = {}

    all_ids = set(old.keys()) | set(new.keys())
    for msg_id in all_ids:
        if msg_id not in old:
            added[msg_id] = new[msg_id]
        elif msg_id not in new:
            removed[msg_id] = old[msg_id]
        else:
            o = old[msg_id]
            n = new[msg_id]
            en_changed = o.get("en", "") != n.get("en", "")
            tr_changed = o.get(lang, "") != n.get(lang, "")

            if en_changed:
                src_mod[msg_id] = {"old": o, "new": n}
            elif tr_changed:
                tr_mod[msg_id] = {"old": o, "new": n}

    return {
        "added": added,
        "removed": removed,
        "src_mod": src_mod,
        "tr_mod": tr_mod,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _render_summary(build: int, diffs: dict[str, dict]) -> str:
    rows = []
    for lang, d in sorted(diffs.items()):
        added = len(d["added"])
        modified = len(d["src_mod"]) + len(d["tr_mod"])
        removed = len(d["removed"])
        rows.append(f"| {lang} | {added} | {modified} | {removed} |")

    table = ("| Language | Added | Modified | Removed |\n"
             "|----------|-------|----------|---------|\n" + "\n".join(rows))
    return f"# Build {build}\n\n## Summary\n\n{table}\n"


def _render_entry(msg_id: str, category: str, entry_data: dict,
                  lang: str) -> str:
    """Render a single changelog entry."""
    lines = [f"**MessageID: {msg_id}**", ""]

    if category == "added":
        lines.append("### Added")
        lines.append("")
        lines.append(fmt_block("en", entry_data.get("en", "")))
        if lang != "en":
            lines.append(fmt_block(lang, entry_data.get(lang, "")))

    elif category == "removed":
        lines.append("### Removed")
        lines.append("")
        lines.append(fmt_block("en", entry_data.get("en", "")))
        if lang != "en":
            lines.append(fmt_block(lang, entry_data.get(lang, "")))

    elif category == "tr_mod":
        old_entry = entry_data["old"]
        new_entry = entry_data["new"]
        lines.append("### Translation Modified")
        lines.append("")
        lines.append(fmt_block("en", new_entry.get("en", "")))
        lines.append(
            diff_block(lang, old_entry.get(lang, ""), new_entry.get(lang, "")))

    elif category == "src_mod":
        old_entry = entry_data["old"]
        new_entry = entry_data["new"]
        lines.append("### Source Modified")
        lines.append("")
        lines.append(
            diff_block("en", old_entry.get("en", ""), new_entry.get("en", "")))
        if lang != "en":
            en_changed = old_entry.get("en", "") != new_entry.get("en", "")
            tr_changed = old_entry.get(lang, "") != new_entry.get(lang, "")
            if tr_changed:
                lines.append(
                    diff_block(lang, old_entry.get(lang, ""),
                               new_entry.get(lang, "")))
            else:
                lines.append(fmt_block(lang, new_entry.get(lang, "")))

    return "\n".join(lines) + "\n\n"


def _collect_detail_events(
        diffs: dict[str, dict]) -> list[tuple[str, str, str, dict]]:
    """
    Collect all events as (msg_id, lang, category, data) and sort by msg_id.
    """
    events = []
    for lang, d in diffs.items():
        for msg_id, entry in d["added"].items():
            events.append((msg_id, lang, "added", entry))
        for msg_id, entry in d["removed"].items():
            events.append((msg_id, lang, "removed", entry))
        for msg_id, entry in d["tr_mod"].items():
            events.append((msg_id, lang, "tr_mod", entry))
        for msg_id, entry in d["src_mod"].items():
            events.append((msg_id, lang, "src_mod", entry))

    # Sort by numeric msg_id where possible
    def sort_key(e):
        try:
            return (int(e[0]), e[1])
        except ValueError:
            return (float("inf"), e[0], e[1])

    events.sort(key=sort_key)
    return events


def render_changes_md(build: int, diffs: dict[str, dict]) -> str:
    """Render the full changes.md content."""
    summary = _render_summary(build, diffs)
    events = _collect_detail_events(diffs)

    detail_lines = ["## Details\n"]
    detail_lines.extend(
        _render_entry(msg_id, category, data, lang)
        for msg_id, lang, category, data in events)
    return summary + "\n" + "\n".join(detail_lines)


# ---------------------------------------------------------------------------
# Cumulative changelog update
# ---------------------------------------------------------------------------


def prepend_to_changelog(changelog_path: Path, new_section: str) -> None:
    """Prepend *new_section* to the cumulative changelog file."""
    existing = changelog_path.read_text(
        encoding="utf-8") if changelog_path.exists() else ""
    separator = "\n---\n\n" if existing else ""
    changelog_path.write_text(new_section + separator + existing,
                              encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_changelog(
    server: str,
    build: int,
    changed_langs: list[str],
    old_json_dir: Path | None = None,
) -> tuple[str, dict]:
    """
    Generate changelog for *changed_langs* on *server*.

    *old_json_dir*: directory containing previous JSON files.
      Defaults to latest/{server}/ (before the new files are written).
      In practice, pass the path to JSON files extracted from the previous release.

    Returns (changes_md_text, diffs_dict).
    """
    server_lower = server.lower()
    new_dir = LATEST_DIR / server_lower
    prev_dir = old_json_dir or (LATEST_DIR / server_lower)

    diffs = {}
    for lang in changed_langs:
        output_key = "en" if lang == "en-us" else lang
        new_path = new_dir / f"{output_key}.json"
        old_path = prev_dir / f"{output_key}.json"

        new_data = load_json(new_path)
        old_data = load_json(old_path)

        diff = compute_diff(old_data, new_data, output_key)
        if any(diff.values()):
            diffs[output_key] = diff

    if not diffs:
        return "", "", {}

    summary = _render_summary(build, diffs)
    md = render_changes_md(build, diffs)
    return summary, md, diffs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate EVE localization changelog.")
    parser.add_argument("server", choices=["TQ", "SISI", "tq", "sisi"])
    parser.add_argument("build", type=int)
    parser.add_argument("langs",
                        nargs="+",
                        help='Changed language codes, e.g. zh ja')
    parser.add_argument("--old-dir",
                        type=Path,
                        help="Directory with previous JSON files")
    parser.add_argument("--output", type=Path, default=Path("changes.md"))
    args = parser.parse_args()

    summary, md, diffs = generate_changelog(
        args.server.upper(),
        args.build,
        args.langs,
        old_json_dir=args.old_dir,
    )

    if md:
        args.output.write_text(md, encoding="utf-8")
        print(f"Wrote {args.output}")

        # Also update cumulative changelog
        changelog_file = ROOT / f"CHANGELOG_{args.server.upper()}.md"
        prepend_to_changelog(changelog_file, md)
        print(f"Updated {changelog_file}")
    else:
        print("No changes detected; no changelog generated.")
