"""Fetch and extract text from Google Drive file links.

Supports:
- Google Docs  (exported as plain text)
- Google Slides (exported as plain text)
- PDF files    (parsed with pypdf)
- Word docs    (.docx, parsed with python-docx)

Does NOT require authentication — only works with publicly shared files.
"""

import io
import logging
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logger = logging.getLogger(__name__)

# Matches standard Drive file view links
# e.g. https://drive.google.com/file/d/FILE_ID/view
DRIVE_FILE_RE = re.compile(
    r"https://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)"
)

# Matches Google Docs / Sheets / Slides links
# e.g. https://docs.google.com/document/d/DOC_ID/edit
GDOCS_RE = re.compile(
    r"https://docs\.google\.com/(document|spreadsheets|presentation)/d/([a-zA-Z0-9_-]+)"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


def is_drive_url(url: str) -> bool:
    """Return True if this is a Google Drive or Google Docs URL."""
    return bool(DRIVE_FILE_RE.search(url) or GDOCS_RE.search(url))


def _fetch_bytes(url: str) -> bytes | None:
    """Download raw bytes from a URL."""
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=20) as resp:
            return resp.read()
    except HTTPError as e:
        logger.warning("HTTP %s fetching Drive file: %s", e.code, url)
        return None
    except Exception:
        logger.exception("Error fetching Drive URL: %s", url)
        return None


def extract_pdf(data: bytes) -> str | None:
    """Extract text from PDF bytes using pypdf."""
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        result = "\n\n".join(pages)
        return result if len(result) > 100 else None
    except Exception:
        logger.exception("PDF extraction failed")
        return None


def _extract_docx(data: bytes) -> str | None:
    """Extract text from .docx bytes using python-docx."""
    try:
        import docx

        doc = docx.Document(io.BytesIO(data))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        result = "\n\n".join(paragraphs)
        return result if len(result) > 100 else None
    except Exception:
        logger.exception("DOCX extraction failed")
        return None


def fetch_drive_file(url: str) -> str | None:
    """Fetch and extract text from a Google Drive or Google Docs link.

    Returns extracted text, or None if unsupported / inaccessible.
    """
    # --- Google Docs / Slides (native Google formats) ---
    gdocs_match = GDOCS_RE.search(url)
    if gdocs_match:
        doc_type, doc_id = gdocs_match.group(1), gdocs_match.group(2)

        export_urls = {
            "document": f"https://docs.google.com/document/d/{doc_id}/export?format=txt",
            "presentation": f"https://docs.google.com/presentation/d/{doc_id}/export?format=txt",
            "spreadsheets": f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv",
        }
        export_url = export_urls.get(doc_type)
        if not export_url:
            logger.warning("Unsupported Google doc type: %s", doc_type)
            return None

        logger.info("Exporting Google %s as text: %s", doc_type, doc_id)
        data = _fetch_bytes(export_url)
        if not data:
            return None

        text = data.decode("utf-8", errors="replace").strip()
        return text if len(text) > 100 else None

    # --- Google Drive file links ---
    drive_match = DRIVE_FILE_RE.search(url)
    if not drive_match:
        return None

    file_id = drive_match.group(1)
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    logger.info("Downloading Drive file: %s", file_id)
    data = _fetch_bytes(download_url)
    if not data:
        return None

    # Detect file type from first bytes
    if data[:4] == b"%PDF":
        logger.info("Detected PDF, extracting text")
        return extract_pdf(data)

    if data[:2] == b"PK":  # ZIP-based: .docx, .pptx, .xlsx
        logger.info("Detected ZIP-based Office file, trying DOCX extraction")
        return _extract_docx(data)

    # Fallback: try decoding as plain text
    try:
        text = data.decode("utf-8", errors="replace").strip()
        return text if len(text) > 100 else None
    except Exception:
        logger.warning("Could not decode Drive file as text: %s", file_id)
        return None
