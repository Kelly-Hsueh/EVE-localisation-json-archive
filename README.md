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

scripts/
├── fetch.py            ← download pickles from EVE CDN
├── merge.py            ← export merged language JSON files
├── changelog.py        ← generate Markdown changelogs
├── release.py          ← create GitHub Releases with assets
├── create_release.py   ← create release from deferred metadata (post-push)
└── run.py              ← orchestrator (fetch → merge → changelog → release)

.github/workflows/
└── localisation.yml    ← daily GitHub Actions workflow

CHANGELOG_TQ.md        ← cumulative TQ changelog
CHANGELOG_SISI.md      ← cumulative SISI changelog
```

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
- `changes.md` – detailed diff for that build

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

## Legal

Scripts in this repository are released under the MIT License.  
EVE Online localisation content is © Fenris Creations ehf. All rights reserved.  
This project is not affiliated with or endorsed by Fenris Creations.
