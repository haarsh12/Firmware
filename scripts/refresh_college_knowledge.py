"""Fetch official SVPCET pages and refresh the local SQLite knowledge base.

Run manually whenever the college site changes. The normal backend never
scrapes the web; it only queries the persisted local SQLite collection.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import time
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.google_cloud import GoogleCloudService  # noqa: E402
from app.knowledge_base import CollegeKnowledgeBase, KnowledgeDocument, curated_documents  # noqa: E402


LOGGER = logging.getLogger("refresh_college_knowledge")
HOST = "www.stvincentngp.edu.in"
SEED_URLS = (
    "https://www.stvincentngp.edu.in/",
    "https://www.stvincentngp.edu.in/pages/director-desk",
    "https://www.stvincentngp.edu.in/pages/principals-desk",
    "https://www.stvincentngp.edu.in/faculties/view/22",
    "https://www.stvincentngp.edu.in/faculties/list/2",
)
# The seeds cover college identity, E&TC faculty, and the professor profile.
# Crawl only a few linked official pages per refresh to keep embedding cost and
# refresh time predictable; add verified URLs to SEED_URLS when needed.
MAX_PAGES = 12


def allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != HOST:
        return False
    return not parsed.path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".zip", ".doc", ".docx"))


class _PageParser(HTMLParser):
    """Small standard-library parser; no runtime scraping dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.text_parts.append(data)


def extract_page(url: str, html: str) -> tuple[str, str, list[str]]:
    parser = _PageParser()
    parser.feed(html)
    title = " ".join(" ".join(parser.title_parts).split()) or url
    text = " ".join(" ".join(parser.text_parts).split())
    links: list[str] = []
    for href in parser.links:
        target, _ = urldefrag(urljoin(url, href))
        if allowed_url(target):
            links.append(target)
    return title, text, links


def crawl_official_pages() -> list[KnowledgeDocument]:
    queue: deque[str] = deque(SEED_URLS)
    seen: set[str] = set()
    documents: list[KnowledgeDocument] = []
    headers = {"User-Agent": "SVPCET-ETC-Project-Knowledge-Refresh/1.0 (educational project)"}
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        while queue and len(documents) < MAX_PAGES:
            url = queue.popleft()
            if url in seen or not allowed_url(url):
                continue
            seen.add(url)
            try:
                response = client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                LOGGER.warning("Skipping %s: %s", url, exc)
                continue
            if "text/html" not in response.headers.get("content-type", ""):
                continue
            title, text, links = extract_page(str(response.url), response.text)
            if len(text) >= 150:
                source_id = "svpcet-" + hashlib.sha256(str(response.url).encode()).hexdigest()[:16]
                documents.append(KnowledgeDocument(source_id, title, text, str(response.url), "official_website"))
                LOGGER.info("Fetched %s", response.url)
            for link in links:
                if link not in seen and len(queue) < MAX_PAGES * 3:
                    queue.append(link)
            time.sleep(0.25)
    return documents


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    cloud = GoogleCloudService(settings)
    configured, detail = cloud.validate_configuration()
    if not configured:
        raise SystemExit(f"Google Cloud credentials are not ready: {detail}")
    documents = [*curated_documents(ROOT), *crawl_official_pages()]
    count = CollegeKnowledgeBase(settings, cloud).replace_documents(documents)
    print(f"Knowledge base refreshed: {count} chunks from {len(documents)} sources.")


if __name__ == "__main__":
    main()
