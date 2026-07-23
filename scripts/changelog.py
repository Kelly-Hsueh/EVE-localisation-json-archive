"""
changelog.py – Generate Markdown changelogs for EVE localization updates.

Per-MessageID grouping: all languages for the same MessageID are rendered
together, with EN shown once.  Smart diff collapses unchanged lines with […].
"""

import difflib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LATEST_DIR = ROOT / "latest"

TRUNC_LIMIT = 500  # chars for plain-text (non-diff) blocks
CONTEXT_LINES = 2  # surrounding unchanged lines kept in multi-line diffs
CHAR_CONTEXT = 40  # chars of context kept around inline single-line changes

# ---------------------------------------------------------------------------
# Low-level text helpers
# ---------------------------------------------------------------------------


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= TRUNC_LIMIT:
        return text, False
    return text[:TRUNC_LIMIT], True


def _empty_group(langs: list[str]) -> str:
    """'ZH, ES, and RU: *empty*' notice."""
    upper = [code.upper() for code in sorted(langs)]
    if len(upper) == 1:
        phrase = upper[0]
    elif len(upper) == 2:
        phrase = f"{upper[0]} and {upper[1]}"
    else:
        phrase = ", ".join(upper[:-1]) + f", and {upper[-1]}"
    return f"{phrase}: *empty*\n\n"


def fmt_block(lang_key: str, text: str) -> str:
    """Plain ```text block.  Empty values render as inline *empty*."""
    if not text:
        return f"{lang_key.upper()}: *empty*\n\n"
    display, truncated = _truncate(text)
    parts = [f"{lang_key.upper()}", "", "```text", display]
    if truncated:
        parts.append(f"(truncated, {len(text):,} chars total)")
    parts += ["```", ""]
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Smart diff helpers
# ---------------------------------------------------------------------------


def _single_line_diff(old: str, new: str) -> str:
    """
    Compact diff for a pair of single-line strings.
    Uses [...] to elide long unchanged prefix/suffix.
    """
    pfx_len = 0
    for a, b in zip(old, new):
        if a == b:
            pfx_len += 1
        else:
            break

    sfx_len = 0
    max_sfx = min(len(old) - pfx_len, len(new) - pfx_len)
    for i in range(1, max_sfx + 1):
        if old[-i] == new[-i]:
            sfx_len += 1
        else:
            break

    prefix = old[:pfx_len]
    suffix = old[len(old) - sfx_len:] if sfx_len else ""
    old_mid = old[pfx_len:len(old) - sfx_len if sfx_len else len(old)]
    new_mid = new[pfx_len:len(new) - sfx_len if sfx_len else len(new)]

    pfx_disp = f"[…]{prefix[-CHAR_CONTEXT:]}" if len(
        prefix) > CHAR_CONTEXT else prefix
    sfx_disp = f"{suffix[:CHAR_CONTEXT]}[…]" if len(
        suffix) > CHAR_CONTEXT else suffix

    return f"- {pfx_disp}{old_mid}{sfx_disp}\n+ {pfx_disp}{new_mid}{sfx_disp}"


def _equal_block_lines(old_lines: list[str], i1: int, i2: int, is_first: bool,
                       is_last: bool) -> list[str]:
    """Context lines for one equal opcode block, with […] collapsing."""
    n = i2 - i1
    if n <= CONTEXT_LINES * 2:
        return [f"  {line}" for line in old_lines[i1:i2]]
    out = []
    if not is_first:
        out.extend(f"  {line}" for line in old_lines[i1:i1 + CONTEXT_LINES])
    out.append("[…]")
    if not is_last:
        out.extend(f"  {line}" for line in old_lines[i2 - CONTEXT_LINES:i2])
    return out


def _multiline_diff_lines(old_lines: list[str],
                          new_lines: list[str]) -> list[str]:
    """Unified diff lines with […] collapsing of unchanged sections."""
    matcher = difflib.SequenceMatcher(None,
                                      old_lines,
                                      new_lines,
                                      autojunk=False)
    opcodes = list(matcher.get_opcodes())
    n_ops = len(opcodes)
    result = []
    for i, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            result.extend(
                _equal_block_lines(old_lines, i1, i2, i == 0, i == n_ops - 1))
        elif tag in ("replace", "delete"):
            result.extend(f"- {line}" for line in old_lines[i1:i2])
            if tag == "replace":
                result.extend(f"+ {line}" for line in new_lines[j1:j2])
        elif tag == "insert":
            result.extend(f"+ {line}" for line in new_lines[j1:j2])
    return result


def smart_diff_block(lang_key: str, old: str, new: str) -> str:
    """
    ```diff block with […] collapsing of unchanged sections.

    Single-line: character-level context around the change.
    Multi-line:  CONTEXT_LINES surrounding lines kept; rest collapsed.
    """
    old_lines = old.splitlines()
    new_lines = new.splitlines()

    if len(old_lines) <= 1 and len(new_lines) <= 1:
        o = old_lines[0] if old_lines else ""
        n = new_lines[0] if new_lines else ""
        content = _single_line_diff(o, n)
    else:
        content = "\n".join(_multiline_diff_lines(old_lines, new_lines))

    return f"{lang_key.upper()}\n\n```diff\n{content}\n```\n\n"


# ---------------------------------------------------------------------------
# Per-language diff computation
# ---------------------------------------------------------------------------


def compute_diff(old: dict, new: dict, lang: str) -> dict:
    """
    Diff *lang*'s own archive file.

    Each per-language JSON entry carries both the "en" field and the
    language's own field, so a plain old-vs-new comparison would flag an
    entry as changed for a language even when only the English source text
    moved and that language's own translation stayed identical -- since
    every changed language's file is diffed independently, this used to
    make a single English source edit show up as an Added/Modified entry
    for every language in the build, not just "en".

    To avoid that, additions/removals/modifications are only reported for
    *lang* when *lang*'s own field ("en" for the English row itself,
    otherwise the language code) actually differs between old and new.
    """
    field = "en" if lang == "en" else lang
    added, removed, src_mod, tr_mod = {}, {}, {}, {}
    for msg_id in set(old) | set(new):
        if msg_id not in old:
            n = new[msg_id]
            if n.get(field, ""):
                added[msg_id] = n
        elif msg_id not in new:
            o = old[msg_id]
            if o.get(field, ""):
                removed[msg_id] = o
        else:
            o, n = old[msg_id], new[msg_id]
            if o.get(field, "") == n.get(field, ""):
                continue  # lang's own text is unchanged - nothing to report

            if lang == "en":
                src_mod[msg_id] = {"old": o, "new": n}
            elif o.get("en", "") != n.get("en", ""):
                # Translation changed alongside the source - still worth
                # grouping under "Source Modified" for this language.
                src_mod[msg_id] = {"old": o, "new": n}
            else:
                tr_mod[msg_id] = {"old": o, "new": n}
    return {
        "added": added,
        "removed": removed,
        "src_mod": src_mod,
        "tr_mod": tr_mod
    }


# ---------------------------------------------------------------------------
# Pivot: per-lang diffs  →  per-MessageID structure
# ---------------------------------------------------------------------------
#
# per_msg[msg_id] = {
#   "primary":    "added"|"removed"|"src_mod"|"tr_mod",
#   "en_old":     str,
#   "en_new":     str,
#   "en_changed": bool,
#   "langs": {
#       lang: { "type": str, "tr_old": str, "tr_new": str }
#   }
# }


def pivot_diffs(diffs: dict) -> dict:
    per_msg: dict = {}

    def get(msg_id: str, primary: str) -> dict:
        if msg_id not in per_msg:
            per_msg[msg_id] = {
                "primary": primary,
                "en_old": "",
                "en_new": "",
                "en_changed": False,
                "langs": {},
            }
        return per_msg[msg_id]

    for lang, d in diffs.items():
        for msg_id, entry in d["added"].items():
            m = get(msg_id, "added")
            m["en_new"] = entry.get("en", "")
            if lang != "en":
                m["langs"][lang] = {
                    "type": "added",
                    "tr_old": "",
                    "tr_new": entry.get(lang, "")
                }

        for msg_id, entry in d["removed"].items():
            m = get(msg_id, "removed")
            m["en_old"] = entry.get("en", "")
            if lang != "en":
                m["langs"][lang] = {
                    "type": "removed",
                    "tr_old": entry.get(lang, ""),
                    "tr_new": ""
                }

        for msg_id, data in d["src_mod"].items():
            m = get(msg_id, "src_mod")
            m["en_old"] = data["old"].get("en", "")
            m["en_new"] = data["new"].get("en", "")
            m["en_changed"] = True
            if lang != "en":
                m["langs"][lang] = {
                    "type": "src_mod",
                    "tr_old": data["old"].get(lang, ""),
                    "tr_new": data["new"].get(lang, ""),
                }

        for msg_id, data in d["tr_mod"].items():
            m = get(msg_id, "tr_mod")
            m["en_new"] = m["en_old"] = data["new"].get("en", "")
            if lang != "en":
                m["langs"][lang] = {
                    "type": "tr_mod",
                    "tr_old": data["old"].get(lang, ""),
                    "tr_new": data["new"].get(lang, ""),
                }

    return per_msg


# ---------------------------------------------------------------------------
# Render one MessageID entry (all languages together)
# ---------------------------------------------------------------------------


def _render_langs_plain(langs_data: dict, value_key: str) -> list[str]:
    """Translation blocks for Added/Removed (plain text, empties grouped)."""
    out: list[str] = []
    empty: list[str] = []
    for lang, ldata in sorted(langs_data.items()):
        if val := ldata[value_key]:
            out.append(fmt_block(lang, val))
        else:
            empty.append(lang)
    if empty:
        out.append(_empty_group(empty))
    return out


def _render_langs_modified(langs_data: dict) -> list[str]:
    """
    Translation blocks for src_mod / tr_mod.
    Changed → smart diff.  Unchanged → plain block.  Never had content → grouped notice.

    A translation going from real text to empty (deleted from that
    language's pickle while the English source message still exists) is a
    genuine removal and must render as a diff, not disappear into the
    "*empty*" notice alongside languages that were never translated at all.
    """
    out: list[str] = []
    empty: list[str] = []
    for lang, ldata in sorted(langs_data.items()):
        tr_old, tr_new = ldata["tr_old"], ldata["tr_new"]
        if not tr_old and not tr_new:
            empty.append(lang)
        elif tr_old == tr_new:
            out.append(fmt_block(lang, tr_new))
        else:
            out.append(smart_diff_block(lang, tr_old, tr_new))
    if empty:
        out.append(_empty_group(empty))
    return out


_PRIMARY_LABELS: dict[str, str] = {
    "added": "Added",
    "removed": "Removed",
    "src_mod": "Source Modified",
    "tr_mod": "Translation Modified",
}


def render_msg_entry(msg_id: str, msg_data: dict) -> str:
    primary = msg_data["primary"]
    en_old = msg_data["en_old"]
    en_new = msg_data["en_new"]
    langs = msg_data["langs"]

    label = _PRIMARY_LABELS.get(primary, primary)
    # MessageID is the heading so it appears in the Markdown TOC / outline.
    # The change type is appended as a suffix for quick scanning.
    parts = [f"### MessageID: {msg_id} · {label}", ""]

    if primary == "added":
        parts += [fmt_block("en", en_new)]
        parts += _render_langs_plain(langs, "tr_new")
    elif primary == "removed":
        parts += [fmt_block("en", en_old)]
        parts += _render_langs_plain(langs, "tr_old")
    elif primary == "src_mod":
        parts += [smart_diff_block("en", en_old, en_new)]
        parts += _render_langs_modified(langs)
    elif primary == "tr_mod":
        parts += [fmt_block("en", en_new)]
        parts += _render_langs_modified(langs)

    return "\n".join(parts) + "\n\n"


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------


def _summary_row(lang: str, d: dict) -> str:
    modified = len(d["src_mod"]) + len(d["tr_mod"])
    return f"| {lang} | {len(d['added'])} | {modified} | {len(d['removed'])} |"


def _render_summary(build: int, diffs: dict) -> str:
    rows = [_summary_row(lang, d) for lang, d in sorted(diffs.items())]
    table = ("| Language | Added | Modified | Removed |\n"
             "|----------|-------|----------|---------|\n" + "\n".join(rows))
    return f"# Build {build}\n\n## Summary\n\n{table}\n"


# ---------------------------------------------------------------------------
# Full changelog render
# ---------------------------------------------------------------------------


def render_changes_md(build: int, diffs: dict) -> str:
    per_msg = pivot_diffs(diffs)

    def sort_key(mid: str) -> tuple:
        try:
            return (0, int(mid))
        except ValueError:
            return (1, mid)

    detail_parts = ["## Details", ""]
    for msg_id in sorted(per_msg, key=sort_key):
        detail_parts.append(render_msg_entry(msg_id, per_msg[msg_id]))

    return _render_summary(build, diffs) + "\n" + "\n".join(detail_parts)


# ---------------------------------------------------------------------------
# Cumulative changelog
# ---------------------------------------------------------------------------


def prepend_to_changelog(changelog_path: Path, new_section: str) -> None:
    existing = changelog_path.read_text(
        encoding="utf-8") if changelog_path.exists() else ""
    sep = "\n---\n\n" if existing else ""
    changelog_path.write_text(new_section + sep + existing, encoding="utf-8")


# ---------------------------------------------------------------------------
# JSON loader
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(
        encoding="utf-8")) if path.exists() else {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_changelog(
    server: str,
    build: int,
    changed_langs: list[str],
    old_json_dir=None,
) -> tuple[str, str, dict]:
    """
    Returns (summary_md, full_md, diffs).
    summary_md  – just the table (for release body)
    full_md     – summary + details (for changes_{build}.md artifact and cumulative log)
    """
    server_lower = server.lower()
    new_dir = LATEST_DIR / server_lower
    prev_dir = Path(
        old_json_dir) if old_json_dir else LATEST_DIR / server_lower

    diffs = {}
    for lang in changed_langs:
        key = "en" if lang == "en-us" else lang
        new_data = load_json(new_dir / f"{key}.json")
        old_data = load_json(prev_dir / f"{key}.json")
        diff = compute_diff(old_data, new_data, key)
        if any(diff.values()):
            diffs[key] = diff

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

    parser = argparse.ArgumentParser()
    parser.add_argument("server", choices=["TQ", "SISI", "tq", "sisi"])
    parser.add_argument("build", type=int)
    parser.add_argument("langs", nargs="+")
    parser.add_argument("--old-dir", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: changes_{build}.md)",
    )
    args = parser.parse_args()

    summary, md, _ = generate_changelog(args.server.upper(),
                                        args.build,
                                        args.langs,
                                        old_json_dir=args.old_dir)
    if md:
        out_path = args.output or Path(f"changes_{args.build}.md")
        out_path.write_text(md, encoding="utf-8")
        print(f"Wrote {out_path}")
        prepend_to_changelog(ROOT / f"CHANGELOG_{args.server.upper()}.md", md)
    else:
        print("No changes detected.")
