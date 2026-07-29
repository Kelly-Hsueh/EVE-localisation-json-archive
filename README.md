[![Archive Localisation Data](https://github.com/Kelly-Hsueh/EVE-localisation-json-archive/actions/workflows/localisation.yml/badge.svg)](https://github.com/Kelly-Hsueh/EVE-localisation-json-archive/actions/workflows/localisation.yml)

# EVE Localisation Archive

Automated archive of EVE Online localisation data for Tranquility (TQ) and Singularity (SISI).

## Structure

```
latest/
├── tq/          ← current JSON files for TQ (zh.json, ja.json, …)
└── sisi/        ← current JSON files for SISI

state/
├── tq-build.txt        ← last processed TQ build number
├── sisi-build.txt      ← last processed SISI build number
├── tq-hashes.json      ← last known localisation hashes for TQ
└── sisi-hashes.json    ← last known localisation hashes for SISI

changelog/
├── tq/
│   └── {year}-Q{quarter}/
│       └── {build}.md  ← full summary + Details for that build
└── sisi/
    └── {year}-Q{quarter}/
        └── {build}.md

scripts/
├── fetch.py            ← download pickles from EVE CDN
├── merge.py            ← export merged language JSON files
├── changelog.py        ← generate Markdown changelogs
├── release.py          ← create GitHub Releases with assets
├── create_release.py   ← create release from deferred metadata (post-push)
├── run.py              ← orchestrator (fetch → merge → changelog → release)
└── search_strings.py   ← search localisation strings by keyword, export to CSV

.github/workflows/
└── localisation.yml    ← daily GitHub Actions workflow

CHANGELOG_TQ.md        ← TQ changelog index (one row per build, links into changelog/tq/)
CHANGELOG_SISI.md      ← SISI changelog index (one row per build, links into changelog/sisi/)
```

Each build's full changelog (Summary table + per-MessageID Details) is archived to its own file under `changelog/{server}/{year}-Q{quarter}/{build}.md`, bucketed by quarter so no single directory accumulates too many files. `CHANGELOG_TQ.md` / `CHANGELOG_SISI.md` stay a lightweight index — one table row per build linking out to the full file — so they load quickly regardless of how much history accumulates. Full details remain plain text under `changelog/`, so any editor's workspace search finds them directly.

## JSON Format

Each `latest/{server}/{lang}.json` file contains entries keyed by MessageID:

```json
{
    "123456": {
        "en": "Warp to selected location",
        "zh": "跃迁至所选位置"
    }
}
```

English-only (`en.json`) uses a single field:

```json
{
    "123456": {
        "en": "Warp to selected location"
    }
}
```

## Release Assets

GitHub Releases are tagged `tq-{build}` or `sisi-{build}` and contain:

- `{lang}_{build}.json` – one file per changed language
- `changes_{build}.md` – detailed diff for that build

## Local Usage

> [!IMPORTANT]
> Requires Python 3.10 or later.

```bash
pip install -r requirements.txt

# Check and archive TQ
python scripts/run.py TQ

# Check and archive SISI
python scripts/run.py SISI

# Force re-download everything
python scripts/run.py TQ SISI --force
```

### Searching strings

`search_strings.py` searches the archived JSON for a keyword and exports matching entries to CSV.

```bash
# Plain substring match across all languages, TQ server
python scripts/search_strings.py TQ "warp"

# Regex match, search only ZH columns
python scripts/search_strings.py TQ "跃迁.*启动" --regex --lang zh

# Search SISI, case-sensitive, custom output path
python scripts/search_strings.py SISI "Warp" --case-sensitive -o cyno_strings.csv
```

Output CSV columns: `message_id`, then one column per language present on disk (`en`, `de`, `es`, `fr`, `it`, `ja`, `ko`, `ru`, `zh`).

## Acknowledgements

Thanks to [EstamelGG](https://github.com/EstamelGG) for his help during the design phase.

## Legal

Scripts in this repository are released under the MIT License.  
EVE Online localisation content is © Fenris Creations ehf. All rights reserved.  
This project is not affiliated with or endorsed by Fenris Creations.
