"""Safe, local desktop YouTube launcher for explicit user voice commands."""

from __future__ import annotations

import logging
import re
import webbrowser
from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx

from app.config import Settings

LOGGER = logging.getLogger(__name__)


class MediaUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaLaunch:
    query: str
    url: str
    direct_video: bool


class DesktopMediaService:
    """Find a YouTube result and ask Windows' default browser to play it."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def open_youtube(self) -> MediaLaunch:
        self._assert_enabled()
        url = "https://www.youtube.com/"
        if not webbrowser.open(url, new=2):
            raise MediaUnavailableError("Windows could not open the default browser.")
        LOGGER.info("Desktop media: opened YouTube home page")
        return MediaLaunch(query="", url=url, direct_video=False)

    def play(self, query: str) -> MediaLaunch:
        self._assert_enabled()
        clean_query = " ".join(query.split())
        if not clean_query or len(clean_query) > 160:
            raise MediaUnavailableError("Please provide a short song or video name.")
        video_id = self._find_video_id(clean_query)
        if video_id:
            # A direct watch URL is much more reliable than a results page.
            # Autoplay remains subject to the user's normal browser policy.
            url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
            direct = True
        else:
            url = f"https://www.youtube.com/results?search_query={quote_plus(clean_query)}"
            direct = False
        if not webbrowser.open(url, new=2):
            raise MediaUnavailableError("Windows could not open the default browser.")
        LOGGER.info("Desktop media: query=%r direct_video=%s", clean_query, direct)
        return MediaLaunch(query=clean_query, url=url, direct_video=direct)

    def _assert_enabled(self) -> None:
        if not self._settings.desktop_media_enabled:
            raise MediaUnavailableError("Desktop media control is disabled in this backend.")

    def _find_video_id(self, query: str) -> str | None:
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        try:
            response = httpx.get(
                url,
                timeout=self._settings.youtube_search_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            LOGGER.warning("YouTube lookup failed; opening results instead: %s", type(exc).__name__)
            return None
        match = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', response.text)
        return match.group(1) if match else None
