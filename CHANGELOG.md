# Changelog

## 0.3.0 - 2026-04-11

- add ORCID funding/grant import into HugoBlox `content/project` leaf bundles
- add `--projects-output` plus `--no-import-grants` CLI controls for project bundle generation
- add regression coverage for grant bundle creation alongside existing publication deduplication tests

## 0.2.0 - 2026-04-10

- add a monthly GitHub Actions workflow for automated ORCID syncs
- skip already imported publications more reliably by matching DOI and ORCID work IDs
- add regression tests for duplicate-avoidance on reruns

## 0.1.0 - 2026-04-08

Initial public packaging of the HugoBlox ORCID importer:

- ORCID-to-HugoBlox publication bundle import
- Crossref enrichment for journal metadata
- PDF-first workflow with PDF-derived `featured.png`
- safeguard against screenshot-only folders without PDFs
- optional HugoBlox APA-style layout overrides
