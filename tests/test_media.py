from unittest.mock import patch

from app.config import Settings
from app.media import DesktopMediaService


def test_play_opens_a_direct_youtube_watch_url() -> None:
    service = DesktopMediaService(Settings(desktop_media_enabled=True))
    with patch.object(service, "_find_video_id", return_value="abcDEF_1234"), patch(
        "app.media.webbrowser.open", return_value=True
    ) as open_browser:
        launch = service.play("Chamak Challo")

    assert launch.direct_video is True
    assert launch.url == "https://www.youtube.com/watch?v=abcDEF_1234&autoplay=1"
    open_browser.assert_called_once_with(launch.url, new=2)


def test_open_youtube_opens_the_home_page() -> None:
    service = DesktopMediaService(Settings(desktop_media_enabled=True))
    with patch("app.media.webbrowser.open", return_value=True) as open_browser:
        launch = service.open_youtube()

    assert launch.url == "https://www.youtube.com/"
    open_browser.assert_called_once_with("https://www.youtube.com/", new=2)
