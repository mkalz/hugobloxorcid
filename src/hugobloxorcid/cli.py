#!/usr/bin/env python3
"""Import publications from ORCID into Hugo content/publications."""

from __future__ import annotations

import argparse
import datetime
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

API_BASE = "https://pub.orcid.org/v3.0"
CROSSREF_API_BASE = "https://api.crossref.org/works"
USER_AGENT = "hugoblox-orcid-importer/1.0 (+https://github.com/HugoBlox/kit)"
PDF_FILE_NAME = "index.pdf"

PUBLICATION_TYPE_MAP = {
    "article-journal": "article-journal",
    "journal-article": "article-journal",
    "conference-paper": "paper-conference",
    "paper-conference": "paper-conference",
    "proceedings-article": "paper-conference",
    "book-chapter": "chapter",
    "chapter": "chapter",
    "book": "book",
    "report": "report",
    "thesis": "thesis",
    "dissertation": "thesis",
    "preprint": "manuscript",
}


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-")


def http_get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def safe_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def first_text(value) -> str | None:
    if isinstance(value, list):
        for item in value:
            if item:
                text = str(item).strip()
                if text:
                    return text
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def map_publication_type(value: str | None) -> str:
    if not value:
        return "article-journal"
    return PUBLICATION_TYPE_MAP.get(str(value).strip().lower(), "article-journal")


def parse_crossref_date(record: dict) -> str | None:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        node = safe_get(record, key) or {}
        parts = safe_get(node, "date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            values = parts[0]
            year = str(values[0])
            month = str(values[1]) if len(values) > 1 else "01"
            day = str(values[2]) if len(values) > 2 else "01"
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(text).split())


def fetch_crossref_metadata(doi: str | None) -> dict:
    if not doi:
        return {}
    try:
        payload = http_get_json(f"{CROSSREF_API_BASE}/{urllib.parse.quote(doi, safe='')}")
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return {}
    message = safe_get(payload, "message", {})
    return message if isinstance(message, dict) else {}


def extract_crossref_authors(record: dict) -> list[str]:
    authors: list[str] = []
    for author in record.get("author", []) or []:
        given = str(safe_get(author, "given", "") or "").strip()
        family = str(safe_get(author, "family", "") or "").strip()
        name = f"{given} {family}".strip()
        if not name:
            name = str(safe_get(author, "name", "") or "").strip()
        if name:
            authors.append(name)
    return authors


def maybe_download_pdf(url: str, target_path: Path) -> bool:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower():
                return False
            data = response.read()
            if not data:
                return False
            target_path.write_bytes(data)
            return True
    except Exception:
        return False


def build_front_matter(data: dict) -> str:
    def quote(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    lines = ["---"]
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        elif isinstance(value, str):
            if "\n" in value:
                lines.append(f"{key}: |")
                for line in value.strip().splitlines():
                    lines.append(f"  {line}")
            else:
                lines.append(f"{key}: {quote(value)}")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
                continue
            lines.append(f"{key}:")
            for item in value:
                if isinstance(item, str):
                    lines.append(f"  - {quote(item)}")
                elif isinstance(item, dict):
                    lines.append("  -")
                    for subkey, subvalue in item.items():
                        if isinstance(subvalue, str):
                            lines.append(f"      {subkey}: {quote(subvalue)}")
                        elif isinstance(subvalue, dict):
                            lines.append(f"      {subkey}:")
                            for nested_key, nested_value in subvalue.items():
                                lines.append(f"        {nested_key}: {quote(str(nested_value))}")
                        elif isinstance(subvalue, list):
                            lines.append(f"      {subkey}:")
                            for subitem in subvalue:
                                lines.append(f"        - {quote(str(subitem))}")
                        else:
                            lines.append(f"      {subkey}: {subvalue}")
                else:
                    lines.append(f"  - {item}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for subkey, subvalue in value.items():
                if isinstance(subvalue, str):
                    lines.append(f"  {subkey}: {quote(subvalue)}")
                elif isinstance(subvalue, dict):
                    lines.append(f"  {subkey}:")
                    for nested_key, nested_value in subvalue.items():
                        if isinstance(nested_value, str):
                            lines.append(f"    {nested_key}: {quote(nested_value)}")
                        else:
                            lines.append(f"    {nested_key}: {nested_value}")
                elif isinstance(subvalue, list):
                    lines.append(f"  {subkey}:")
                    for subitem in subvalue:
                        lines.append(f"    - {quote(str(subitem))}")
                else:
                    lines.append(f"  {subkey}: {subvalue}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def format_bibtex_entry(record: dict, key: str) -> str:
    fields = []
    for field, value in record.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        if isinstance(value, list):
            fields.append(f"  {field} = {{{'; '.join(value)}}}")
        else:
            fields.append(f"  {field} = {{{value}}}")
    fields_text = ",\n".join(fields)
    return f"@article{{{key},\n{fields_text}\n}}\n"


def generate_title_screenshot(title: str, target_path: Path, width: int = 800, height: int = 650) -> None:
    background = Image.new("RGB", (width, height), "#f8f8f8")
    draw = ImageDraw.Draw(background)
    try:
        header_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 42)
        body_font = ImageFont.truetype("DejaVuSans.ttf", 32)
    except OSError:
        header_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    def text_size(text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        if hasattr(draw, "textsize"):
            return draw.textsize(text, font=font)
        return font.getsize(text)

    header_height = 120
    draw.rectangle([(0, 0), (width, header_height)], fill="#263859")
    header_text = "Paper title"
    header_size = text_size(header_text, header_font)
    draw.text(
        ((width - header_size[0]) / 2, (header_height - header_size[1]) / 2),
        header_text,
        font=header_font,
        fill="#ffffff",
    )

    content_width = width - 80
    words = title.split()
    lines: list[str] = []
    current_line = ""
    for word in words:
        if current_line:
            candidate = f"{current_line} {word}"
        else:
            candidate = word
        line_width = text_size(candidate, body_font)[0]
        if line_width <= content_width:
            current_line = candidate
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    y_offset = header_height + 40
    for line in lines:
        draw.text((40, y_offset), line, font=body_font, fill="#222222")
        y_offset += text_size(line, body_font)[1] + 14

    background.save(target_path, format="PNG")


def generate_featured_from_pdf(pdf_path: Path, target_path: Path, width: int = 800, height: int = 650) -> bool:
    def save_fitted(image: Image.Image) -> None:
        fitted = ImageOps.contain(image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (width, height), "#ffffff")
        x = (width - fitted.width) // 2
        y = (height - fitted.height) // 2
        canvas.paste(fitted, (x, y))
        canvas.save(target_path, format="PNG")

    if fitz is not None:
        try:
            with fitz.open(pdf_path) as pdf_doc:
                if not pdf_doc.page_count:
                    return False

                # Prefer the largest embedded image (figure) from early pages.
                best_image = None
                best_area = 0
                pages_to_scan = min(pdf_doc.page_count, 6)
                min_area = 250 * 250

                for page_index in range(pages_to_scan):
                    page = pdf_doc.load_page(page_index)
                    for img_meta in page.get_images(full=True):
                        xref = img_meta[0]
                        img_dict = pdf_doc.extract_image(xref)
                        img_bytes = img_dict.get("image")
                        if not img_bytes:
                            continue
                        with Image.open(io.BytesIO(img_bytes)) as raw_img:
                            area = raw_img.width * raw_img.height
                            if area >= min_area and area > best_area:
                                best_area = area
                                best_image = raw_img.convert("RGB")

                if best_image is not None:
                    save_fitted(best_image)
                    return True

                page = pdf_doc.load_page(0)
                pix = page.get_pixmap(alpha=False)
                first_page = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                save_fitted(first_page)
                return True
        except Exception:
            pass

    try:
        with Image.open(pdf_path) as pdf_image:
            if hasattr(pdf_image, "seek"):
                pdf_image.seek(0)

            first_page = pdf_image.convert("RGB")
            save_fitted(first_page)
            return True
    except Exception:
        return False


def parse_orcid_id(value: str) -> str:
    value = value.strip()
    value = value.replace("https://orcid.org/", "").replace("http://orcid.org/", "")
    value = value.strip("/")
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", value):
        raise ValueError(f"Invalid ORCID iD: {value}")
    return value


def extract_work_authors(work: dict, fallback_author: str | None, orcid_id: str) -> list[str]:
    authors: list[str] = []

    contributors = safe_get(work, "contributors") or {}
    contributor_items = contributors.get("contributor", []) if isinstance(contributors, dict) else []

    for contributor in contributor_items:
        if not isinstance(contributor, dict):
            continue
        name = None

        credit_name = safe_get(contributor, "credit-name")
        if isinstance(credit_name, dict):
            name = safe_get(credit_name, "value")

        if not name:
            contributor_name = safe_get(contributor, "contributor-name")
            if isinstance(contributor_name, dict):
                name = safe_get(contributor_name, "value")

        if not name:
            name = safe_get(contributor, "name")

        if not name:
            contributor_orcid = safe_get(contributor, "contributor-orcid")
            if isinstance(contributor_orcid, dict):
                name = safe_get(contributor_orcid, "path")

        if name:
            authors.append(str(name).strip())

    if not authors:
        if fallback_author:
            authors = [fallback_author]
        else:
            authors = [orcid_id]

    return authors


def extract_author_name(person_data: dict) -> str | None:
    name = person_data.get("name", {})
    given = name.get("given-names", {}).get("value")
    family = name.get("family-name", {}).get("value")
    if given and family:
        return f"{given} {family}".strip()
    if given:
        return given
    if family:
        return family
    return None


def parse_publication_date(date_node: dict) -> str | None:
    if not date_node:
        return None
    year = safe_get(date_node.get("year") or {}, "value")
    month = safe_get(date_node.get("month") or {}, "value")
    day = safe_get(date_node.get("day") or {}, "value")
    if not year:
        return None
    month = month or "01"
    day = day or "01"
    try:
        return datetime.date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def normalize_url(url: str) -> str:
    return url.strip()


def to_url_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        if value.get("value"):
            return [value["value"]]
        if value.get("url") and isinstance(value["url"], dict) and value["url"].get("value"):
            return [value["url"]["value"]]
        return []
    if isinstance(value, list):
        urls: list[str] = []
        for item in value:
            urls.extend(to_url_list(item))
        return urls
    return []


def collect_work_urls(work: dict, doi: str | None) -> list[str]:
    urls: list[str] = []
    urls.extend(to_url_list(work.get("url")))

    citation = work.get("citation") or {}
    citation_value = citation.get("work-citation")
    if isinstance(citation_value, str):
        urls.extend(re.findall(r"https?://[^\s'\"<>]+", citation_value))

    if doi:
        urls.append(f"https://doi.org/{doi}")

    cleaned: list[str] = []
    for url in urls:
        if not url:
            continue
        normalized = normalize_url(url)
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def choose_pdf_link(urls: list[str]) -> str | None:
    for url in urls:
        if url.lower().endswith(".pdf"):
            return url
    return None


def title_slug(title: str, max_words: int = 4) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    return "-".join(words[:max_words]) if words else "publication"


def folder_slug_from_title(title: str, date_value: str | None) -> str:
    year = None
    if date_value:
        year = date_value.split("-")[0]
    year_part = year if year else "unknown"
    return slugify(f"{year_part}-{title_slug(title)}")[:120]


def fetch_text(url: str, timeout: int = 20) -> str | None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            charset_match = re.search(r"charset=([^;]+)", content_type, re.I)
            encoding = charset_match.group(1) if charset_match else "utf-8"
            return body.decode(encoding, errors="replace")
    except Exception:
        return None


def find_pdf_urls_in_html(html: str, base_url: str) -> list[str]:
    candidates: list[str] = []
    patterns = [
        r'(?i)(?:href|src|content|data-pdf-url|data-url)\s*=\s*["\']([^"\']+?\.pdf(?:\?[^"\']*)?)["\']',
        r'(?i)https?://[^\s"\'<>]+?\.pdf(?:\?[^\s"\'<>]*)?',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, html):
            candidate = urllib.parse.urljoin(base_url, match)
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def derive_pdf_urls(url: str, doi: str | None) -> list[str]:
    candidates: list[str] = []
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    doi_value = (doi or "").strip()
    quoted_doi = urllib.parse.quote(doi_value, safe="") if doi_value else ""

    if doi_value and ("springer.com" in host or doi_value.startswith("10.1007/")):
        candidates.extend(
            [
                f"https://link.springer.com/content/pdf/{doi_value}.pdf",
                f"https://link.springer.com/content/pdf/{quoted_doi}.pdf",
            ]
        )

    if doi_value and "tandfonline.com" in host:
        candidates.append(f"https://www.tandfonline.com/doi/pdf/{doi_value}?download=true")

    if doi_value and ("wiley.com" in host or "onlinelibrary.wiley.com" in host):
        candidates.extend(
            [
                f"https://onlinelibrary.wiley.com/doi/pdf/{doi_value}",
                f"https://onlinelibrary.wiley.com/doi/epdf/{doi_value}",
                f"https://onlinelibrary.wiley.com/doi/pdfdirect/{doi_value}",
            ]
        )

    if doi_value and "emerald.com" in host:
        candidates.append(f"https://www.emerald.com/insight/content/doi/{doi_value}/full/pdf")

    cleaned: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned


def download_pdf_from_page(url: str, target_path: Path) -> bool:
    html = fetch_text(url)
    if not html:
        return False
    pdf_urls = find_pdf_urls_in_html(html, url)
    for pdf_url in pdf_urls:
        if maybe_download_pdf(pdf_url, target_path):
            return True
    return False


def download_pdf_from_sources(urls: list[str], target_path: Path, doi: str | None = None) -> bool:
    expanded_urls: list[str] = []
    for url in urls:
        if url and url not in expanded_urls:
            expanded_urls.append(url)
        for derived in derive_pdf_urls(url, doi):
            if derived not in expanded_urls:
                expanded_urls.append(derived)

    for url in expanded_urls:
        if maybe_download_pdf(url, target_path):
            return True

    for url in expanded_urls:
        if download_pdf_from_page(url, target_path):
            return True

    return False


def parse_work(work: dict, orcid_id: str, author_name: str | None) -> tuple[dict, str, list[str], str | None]:
    title_data = work.get("title") or {}
    title_value = safe_get(title_data, "title") or {}
    title = safe_get(title_value, "value")

    subtitle_data = safe_get(title_data, "subtitle") or {}
    subtitle = safe_get(subtitle_data, "value")

    if not title:
        work_title = work.get("work-title") or {}
        work_title_value = safe_get(work_title, "title") or {}
        title = safe_get(work_title_value, "value")

    year = parse_publication_date(work.get("publication-date"))
    put_code = work.get("put-code") or str(work.get("id"))

    doi = None
    external_ids_data = work.get("external-ids") or {}
    for item in external_ids_data.get("external-id", []) or []:
        type_ = safe_get(item, "external-id-type")
        value = safe_get(item, "external-id-value")
        if value and isinstance(type_, str) and type_.lower() == "doi":
            doi = str(value).lower().replace("doi:", "").strip()
            break

    crossref = fetch_crossref_metadata(doi)
    crossref_title = first_text(crossref.get("title"))
    crossref_subtitle = first_text(crossref.get("subtitle"))

    if not title and crossref_title:
        title = crossref_title
    if not subtitle and crossref_subtitle:
        subtitle = crossref_subtitle
    if subtitle and title and subtitle not in title:
        title = f"{title}: {subtitle}"
    elif subtitle and not title:
        title = subtitle

    publication_venue = first_text(crossref.get("container-title")) or safe_get(safe_get(work, "journal-title") or {}, "value")
    publication_short = first_text(crossref.get("short-container-title")) or publication_venue

    if not author_name and work.get("source"):
        author_name = safe_get(safe_get(work, "source") or {}, "source-name")
        if isinstance(author_name, dict):
            author_name = safe_get(author_name, "value")

    authors = extract_work_authors(work, author_name, orcid_id)
    crossref_authors = extract_crossref_authors(crossref)
    if crossref_authors:
        authors = crossref_authors

    date_value = year or parse_crossref_date(crossref) or datetime.date.today().isoformat()

    abstract = (
        clean_text(crossref.get("abstract"))
        or safe_get(safe_get(work, "short-description") or {}, "value")
        or safe_get(safe_get(work, "description") or {}, "value")
        or ""
    )

    url_candidates = collect_work_urls(work, doi)
    if crossref:
        resource = safe_get(crossref, "resource") or {}
        primary = safe_get(resource, "primary") or {}
        resource_url = safe_get(primary, "URL")
        if resource_url:
            url_candidates.insert(0, resource_url)

        for link in crossref.get("link", []) or []:
            url = safe_get(link, "URL")
            if url:
                url_candidates.append(url)

        doi_url = safe_get(crossref, "URL")
        if doi_url:
            url_candidates.append(doi_url)

    cleaned_urls: list[str] = []
    for url in url_candidates:
        normalized = normalize_url(url) if url else ""
        if normalized and normalized not in cleaned_urls:
            cleaned_urls.append(normalized)
    url_candidates = cleaned_urls

    direct_pdf = choose_pdf_link(url_candidates)
    if not direct_pdf:
        for link in crossref.get("link", []) or []:
            content_type = str(safe_get(link, "content-type", "") or "").lower()
            if "pdf" in content_type:
                direct_pdf = safe_get(link, "URL")
                if direct_pdf and direct_pdf not in url_candidates:
                    url_candidates.append(direct_pdf)
                break

    tags = []
    keyword_data = work.get("keywords") or {}
    keyword_items = (keyword_data.get("keyword") or []) if isinstance(keyword_data, dict) else []
    for kw in keyword_items:
        if isinstance(kw, dict):
            kw_value = kw.get("content") or kw.get("value") or kw.get("keyword")
            if kw_value:
                tags.append(str(kw_value).strip())
        elif isinstance(kw, str):
            tags.append(kw.strip())
    for subject in crossref.get("subject", []) or []:
        if subject:
            tags.append(str(subject).strip())

    seen = set()
    tags = [t for t in tags if t and not (t in seen or seen.add(t))]

    publication_type = map_publication_type(first_text(crossref.get("type")) or safe_get(work, "type"))
    source_url = next((url for url in url_candidates if not url.lower().endswith(".pdf")), None)
    if not source_url and url_candidates:
        source_url = url_candidates[0]

    bib_record = {
        "author": "; ".join(authors),
        "title": title or "Untitled",
        "year": date_value[:4] if date_value else None,
        "journal": publication_venue,
        "volume": first_text(crossref.get("volume")),
        "number": first_text(crossref.get("issue")),
        "pages": first_text(crossref.get("page")),
        "doi": doi,
        "url": source_url,
        "abstract": abstract or None,
    }
    bib_key = (slugify(title or put_code) or put_code).replace("-", "_")
    fields = {k: v for k, v in bib_record.items() if v}

    links = [
        {"type": "source", "url": source_url} if source_url else None,
        {"type": "pdf", "url": direct_pdf} if direct_pdf else None,
    ]

    return {
        "title": title or "Untitled publication",
        "authors": authors,
        "date": date_value,
        "hugoblox": {"ids": {"doi": doi}} if doi else {},
        "publication_types": [publication_type],
        "publication": publication_venue,
        "publication_short": publication_short,
        "volume": first_text(crossref.get("volume")),
        "issue": first_text(crossref.get("issue")),
        "pages": first_text(crossref.get("page")),
        "abstract": abstract,
        "links": [link for link in links if link],
        "featured": False,
        "summary": abstract or title or "",
        "tags": tags,
    }, format_bibtex_entry(fields, bib_key), url_candidates, doi


def main() -> int:
    parser = argparse.ArgumentParser(description="Import ORCID publications into HugoBlox content/publications")
    parser.add_argument("orcid", help="ORCID iD or ORCID URL")
    parser.add_argument("--output", default="content/publications", help="Output folder for content/publications")
    parser.add_argument("--author", help="Default author name for imported works")
    parser.set_defaults(download_pdf=True)
    parser.add_argument(
        "--download-pdf",
        dest="download_pdf",
        action="store_true",
        help="Attempt to download PDFs from direct links or DOI landing pages (default)",
    )
    parser.add_argument(
        "--no-download-pdf",
        dest="download_pdf",
        action="store_false",
        help="Skip PDF download and PDF-based cover generation",
    )
    parser.add_argument(
        "--featured-from-title-fallback",
        action="store_true",
        help="Create a title-based fallback only if a PDF exists but its preview image cannot be rendered",
    )
    parser.add_argument(
        "--only-slug",
        help="Only process a single publication folder slug (for targeted regeneration)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing publication folders")
    args = parser.parse_args()

    orcid_id = parse_orcid_id(args.orcid)
    content_root = Path(args.output)
    content_root.mkdir(parents=True, exist_ok=True)

    person_data = None
    if not args.author:
        try:
            person_data = http_get_json(f"{API_BASE}/{orcid_id}/person")
        except Exception:
            pass
    author_name = args.author or (extract_author_name(person_data) if person_data else None)

    try:
        works_data = http_get_json(f"{API_BASE}/{orcid_id}/works")
    except Exception as exc:
        print(f"Error fetching ORCID works: {exc}", file=sys.stderr)
        return 2

    groups = works_data.get("group", [])
    if not groups:
        print("No works found for ORCID", orcid_id)
        return 0

    created = 0
    skipped = 0
    warnings = []

    for group in groups:
        summaries = group.get("work-summary", [])
        if not summaries:
            continue
        work_summary = summaries[0]
        put_code = work_summary.get("put-code")
        if not put_code:
            continue
        try:
            work_details = http_get_json(f"{API_BASE}/{orcid_id}/work/{put_code}")
        except Exception as exc:
            warnings.append(f"Failed to fetch work {put_code}: {exc}")
            continue
        publication, bibtex, pdf_urls, doi = parse_work(work_details, orcid_id, author_name)
        folder_slug = folder_slug_from_title(publication["title"], publication.get("date"))
        if args.only_slug and folder_slug != args.only_slug:
            continue
        folder = content_root / folder_slug
        if folder.exists() and not args.force:
            skipped += 1
            continue
        folder.mkdir(parents=True, exist_ok=True)

        front_matter = {k: v for k, v in publication.items() if v is not None}
        if front_matter.get("links"):
            front_matter["links"] = [link for link in front_matter["links"] if link]

        index_md = build_front_matter(front_matter) + "\n\n" + (publication.get("abstract") or "")
        (folder / "index.md").write_text(index_md, encoding="utf-8")
        (folder / "cite.bib").write_text(bibtex, encoding="utf-8")

        featured_path = folder / "featured.png"
        pdf_path = folder / PDF_FILE_NAME
        pdf_available = False

        if args.download_pdf:
            if download_pdf_from_sources(pdf_urls, pdf_path, doi=doi):
                print(f"Downloaded PDF for {folder_slug}")
                pdf_available = True
            elif pdf_path.exists():
                print(f"Using existing PDF for {folder_slug}")
                pdf_available = True
            else:
                warnings.append(f"PDF download failed for {folder_slug}")
        elif pdf_path.exists():
            pdf_available = True

        if pdf_available:
            if not generate_featured_from_pdf(pdf_path, featured_path):
                if featured_path.exists():
                    featured_path.unlink()
                if args.featured_from_title_fallback:
                    warnings.append(f"Could not render featured image from PDF for {folder_slug}; using title image")
                    generate_title_screenshot(publication["title"], featured_path)
                else:
                    warnings.append(f"Could not render featured image from PDF for {folder_slug}")
        else:
            if featured_path.exists():
                featured_path.unlink()
            if args.featured_from_title_fallback:
                warnings.append(f"No PDF available for {folder_slug}; skipping featured image because no PDF was downloaded")

        created += 1

    print(f"Imported {created} publications, skipped {skipped} existing entries.")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(" -", warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
