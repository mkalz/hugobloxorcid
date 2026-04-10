# HugoBlox ORCID Importer

[![CI](https://github.com/mkalz/hugobloxorcid/actions/workflows/ci.yml/badge.svg)](https://github.com/mkalz/hugobloxorcid/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

Import publications from **ORCID** into HugoBlox/Hugo `content/publications/` bundles, with optional **Crossref DOI enrichment**, **PDF download**, and **cover image generation**.

## Features

- imports ORCID works into Hugo leaf bundles
- writes `index.md` and `cite.bib`
- enriches DOI-based records from Crossref
- downloads `index.pdf` when a reachable PDF is available
- generates `featured.png` from the PDF
- avoids orphan screenshots when no PDF could be fetched
- skips already imported publications reliably via DOI and ORCID work identifiers
- includes a monthly GitHub Actions sync workflow for hands-free updates
- includes optional HugoBlox template overrides for APA-style publication pages

## Installation

Requires Python 3.10 or newer.

```bash
cd /path/to/hugobloxorcid
python -m pip install -e .[pdf]
```

If you only need the core importer:

```bash
python -m pip install -e .
```

## Usage

### Console entry point

```bash
hugoblox-orcid-import 0000-0003-1471-5827
```

### Script wrapper

```bash
python scripts/orcid_import.py 0000-0003-1471-5827
```

### Common options

```bash
# Rebuild all bundles and try to fetch PDFs
hugoblox-orcid-import 0000-0003-1471-5827 --force

# Regenerate one known slug
hugoblox-orcid-import 0000-0003-1471-5827 --only-slug 2025-mediendidaktik-als-implementierungswissenschaft-der --force

# Skip PDF fetching entirely
hugoblox-orcid-import 0000-0003-1471-5827 --no-download-pdf
```

## Output

Each publication bundle may contain:

- `index.md`
- `cite.bib`
- `index.pdf` when available
- `featured.png` when generated from the PDF

> `featured.png` is only kept when `index.pdf` exists.

## Optional HugoBlox site overrides

Optional layout overrides are included under:

```text
examples/hugo-site-overrides/
```

These can be copied into a HugoBlox site if you want the same APA-style citation rendering and publication metadata layout used during development.

## Monthly GitHub Actions sync

The repository now includes `.github/workflows/monthly-orcid-sync.yml` for an automated ORCID refresh on the **1st day of each month** and via manual dispatch.

Set these repository variables in GitHub:

- `ORCID_ID` **required** – the ORCID iD to sync
- `PUBLICATIONS_PATH` optional – defaults to `content/publications`
- `ORCID_IMPORT_ARGS` optional – extra CLI flags such as `--no-download-pdf`

The workflow commits changes only when new publication bundles are added, and reruns skip already imported entries by matching **DOI** and **ORCID work ID**.

## Development

```bash
python -m pip install -e .[pdf]
python -m compileall src
python -m unittest discover -s tests -p 'test_*.py'
python scripts/orcid_import.py --help
hugoblox-orcid-import --help
```

For maintainers, PyPI publishing is automated via `.github/workflows/publish.yml` using GitHub trusted publishing.

For contributions, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Repository layout

```text
src/hugobloxorcid/        Python package
scripts/orcid_import.py   Simple wrapper script
examples/                 Optional HugoBlox layout overrides
.github/workflows/        Basic CI for GitHub
```

## License

MIT
