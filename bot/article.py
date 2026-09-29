"""Fetch and extract article text from URLs."""

import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import trafilatura

from bot.gdrive import extract_pdf

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# URLs that aren't articles worth summarizing
SKIP_PATTERNS = [
    r"^https?://(www\.)?(youtube\.com|youtu\.be)/",
    r"^https?://(www\.)?twitter\.com/",
    r"^https?://(www\.)?x\.com/",
    r"^https?://(.*\.)?slack\.com/",
    r"^https?://(.*\.)?giphy\.com/",
    r"\.(png|jpg|jpeg|gif|mp4|mp3)(\?.*)?$",
]


def should_skip(url: str) -> bool:
    """Return True if the URL is not an article we should summarize."""
    return any(re.search(p, url, re.IGNORECASE) for p in SKIP_PATTERNS)


def _normalize_url(url: str) -> str:
    """Produce a comparison key so near-identical URLs dedup to one.

    Lowercases the scheme/host, drops a trailing slash on the path, and strips
    common tracking params (utm_*, fbclid, gclid). The returned value is only
    used for equality checks, not for fetching.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return url

    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not (k.lower().startswith("utm_") or k.lower() in ("fbclid", "gclid"))
        ]
    )
    return urlunparse((parsed.scheme.lower(), netloc, path, parsed.params, query, ""))


def _dedup(urls: list[str]) -> list[str]:
    """Drop duplicate URLs, preserving first-seen order."""
    seen = set()
    result = []
    for url in urls:
        key = _normalize_url(url)
        if key not in seen:
            seen.add(key)
            result.append(url)
    return result


def extract_urls(text: str) -> list[str]:
    """Pull URLs out of a Slack message.

    Slack wraps URLs in angle brackets: <https://example.com>
    Sometimes with a label: <https://example.com|example.com>
    """
    # Match Slack-formatted URLs
    slack_urls = re.findall(r"<(https?://[^|>]+)(?:\|[^>]*)?>", text)
    if slack_urls:
        return _dedup([u for u in slack_urls if not should_skip(u)])

    # Fallback: bare URLs
    bare_urls = re.findall(r"https?://\S+", text)
    return _dedup([u for u in bare_urls if not should_skip(u)])


class FetchError(Exception):
    """Raised when a URL can't be turned into text. The message is user-facing."""


def _fetch_bytes(url: str) -> tuple[bytes, str]:
    """Download raw bytes with browser-like headers. Returns (data, charset)."""
    req = Request(url, headers=BROWSER_HEADERS)
    with urlopen(req, timeout=15) as resp:
        return resp.read(), resp.headers.get_content_charset() or "utf-8"


def fetch_article(url: str) -> str:
    """Download and extract the main text content from a URL.

    Handles HTML articles and PDFs. Returns the text, or raises FetchError
    with a user-facing reason.
    """
    # First try trafilatura's built-in fetcher
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception:
        logger.exception("trafilatura fetch failed: %s", url)
        downloaded = None

    # Refetch as raw bytes if trafilatura failed (sites that block bots) or
    # returned a PDF (which it decodes to lossy text)
    if not downloaded or downloaded.startswith("%PDF"):
        logger.info("Fetching raw bytes with browser headers: %s", url)
        try:
            data, charset = _fetch_bytes(url)
        except Exception:
            logger.warning("Fallback fetch also failed: %s", url)
            raise FetchError("the site blocked access or didn't respond")

        if data[:4] == b"%PDF":
            logger.info("Detected PDF, extracting text: %s", url)
            text = extract_pdf(data)
            if not text:
                raise FetchError("it's a PDF but no readable text could be extracted (it may be scanned images)")
            return text
        downloaded = data.decode(charset, errors="replace")

    if not downloaded:
        logger.warning("Failed to download: %s", url)
        raise FetchError("the site blocked access or didn't respond")

    try:
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
    except Exception:
        logger.exception("Error extracting article: %s", url)
        text = None

    if not text or len(text.strip()) < 100:
        logger.warning("Extracted text too short from: %s", url)
        raise FetchError("the page loaded but didn't contain readable article text (it may be paywalled or JavaScript-rendered)")

    return text.strip()
