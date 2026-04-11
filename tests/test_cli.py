import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hugobloxorcid import cli


def make_work(put_code: str, title: str, doi: str | None = None) -> dict:
    external_ids = []
    if doi:
        external_ids.append({"external-id-type": "doi", "external-id-value": doi})

    return {
        "put-code": put_code,
        "title": {"title": {"value": title}},
        "publication-date": {"year": {"value": "2024"}, "month": {"value": "04"}, "day": {"value": "10"}},
        "external-ids": {"external-id": external_ids},
        "contributors": {"contributor": [{"credit-name": {"value": "Alice Example"}}]},
        "type": "journal-article",
    }


def make_funding(put_code: str, title: str) -> dict:
    return {
        "put-code": put_code,
        "title": {"title": {"value": title}},
        "short-description": {"value": "Supports an open teaching initiative"},
        "organization": {"name": "Open Science Foundation"},
        "amount": {"value": "25000", "currency-code": "EUR"},
        "start-date": {"year": {"value": "2025"}, "month": {"value": "01"}, "day": {"value": "01"}},
        "end-date": {"year": {"value": "2025"}, "month": {"value": "12"}, "day": {"value": "31"}},
        "url": {"value": "https://example.org/grants/789"},
        "external-ids": {
            "external-id": [{"external-id-type": "grant_number", "external-id-value": "GI-2025-01"}]
        },
        "contributors": {"contributor": [{"credit-name": {"value": "Alice Example"}}]},
        "type": "award",
    }


class ImportDeduplicationTests(unittest.TestCase):
    def run_import(self, output_dir: Path, work: dict | None, funding: dict | None = None) -> tuple[int, str]:
        orcid_id = "0000-0000-0000-0001"
        project_dir = output_dir.parent / "projects"

        def fake_http_get_json(url: str) -> dict:
            if url.endswith(f"/{orcid_id}/person"):
                return {"name": {"given-names": {"value": "Alice"}, "family-name": {"value": "Example"}}}
            if url.endswith(f"/{orcid_id}/works"):
                if not work:
                    return {"group": []}
                return {"group": [{"work-summary": [{"put-code": work["put-code"]}]}]}
            if work and url.endswith(f"/{orcid_id}/work/{work['put-code']}"):
                return work
            if url.endswith(f"/{orcid_id}/fundings"):
                if not funding:
                    return {"group": []}
                return {"group": [{"funding-summary": [{"put-code": funding["put-code"]}]}]}
            if funding and url.endswith(f"/{orcid_id}/funding/{funding['put-code']}"):
                return funding
            raise AssertionError(f"Unexpected URL requested: {url}")

        stdout = io.StringIO()
        with patch.object(cli, "http_get_json", side_effect=fake_http_get_json), patch.object(
            cli, "fetch_crossref_metadata", return_value={}
        ), patch.object(cli, "download_pdf_from_sources", return_value=False), patch.object(
            cli, "generate_featured_from_pdf", return_value=False
        ), patch.object(
            sys,
            "argv",
            [
                "hugoblox-orcid-import",
                orcid_id,
                "--output",
                str(output_dir),
                "--projects-output",
                str(project_dir),
                "--no-download-pdf",
            ],
        ), contextlib.redirect_stdout(stdout):
            exit_code = cli.main()

        return exit_code, stdout.getvalue()

    def test_skips_existing_publication_when_doi_matches_but_slug_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "publications"
            existing = output_dir / "2024-older-folder-name"
            existing.mkdir(parents=True)
            (existing / "index.md").write_text(
                "---\n"
                "title: \"Older Imported Version\"\n"
                "hugoblox:\n"
                "  ids:\n"
                "    doi: \"10.1234/existing\"\n"
                "---\n",
                encoding="utf-8",
            )

            exit_code, output = self.run_import(output_dir, make_work("123", "A Brand New Title", "10.1234/existing"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(sorted(p.name for p in output_dir.iterdir()), ["2024-older-folder-name"])
            self.assertIn("Imported 0 publications, skipped 1 existing entries.", output)

    def test_skips_existing_publication_when_orcid_work_id_matches_without_doi(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "publications"
            existing = output_dir / "2024-previous-import"
            existing.mkdir(parents=True)
            (existing / "index.md").write_text(
                "---\n"
                "title: \"Previous Imported Version\"\n"
                "hugoblox:\n"
                "  ids:\n"
                "    orcid: \"0000-0000-0000-0001:456\"\n"
                "---\n",
                encoding="utf-8",
            )

            exit_code, output = self.run_import(output_dir, make_work("456", "A Different New Title"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(sorted(p.name for p in output_dir.iterdir()), ["2024-previous-import"])
            self.assertIn("Imported 0 publications, skipped 1 existing entries.", output)

    def test_imports_grant_into_project_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            output_dir = base_dir / "publications"
            project_dir = base_dir / "projects"

            exit_code, output = self.run_import(output_dir, None, make_funding("789", "Teaching Innovation Grant"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(sorted(p.name for p in project_dir.iterdir()), ["2025-teaching-innovation-grant"])

            index_text = (project_dir / "2025-teaching-innovation-grant" / "index.md").read_text(encoding="utf-8")
            self.assertIn('title: "Teaching Innovation Grant"', index_text)
            self.assertIn('grant_number: "GI-2025-01"', index_text)
            self.assertIn('funder: "Open Science Foundation"', index_text)
            self.assertIn("Imported 0 publications and 1 grants, skipped 0 existing entries.", output)


if __name__ == "__main__":
    unittest.main()
