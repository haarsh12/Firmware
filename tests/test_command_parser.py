from app.command_parser import ParsedRelayCommand, parse_media_command, parse_relay_commands


def test_parses_english_light_and_fan_commands() -> None:
    assert parse_relay_commands("Please turn on the light and fan band karo") == [
        ParsedRelayCommand("light", True),
        ParsedRelayCommand("fan", False),
    ]


def test_parses_devanagari_command_without_llm() -> None:
    assert parse_relay_commands("लाइट बंद करो और पंखा चालू करो") == [
        ParsedRelayCommand("light", False),
        ParsedRelayCommand("fan", True),
    ]


def test_status_question_does_not_toggle_a_relay() -> None:
    assert parse_relay_commands("Kya light on hai?") == []


def test_play_song_command_extracts_title() -> None:
    command = parse_media_command("Play song Chamak Challo on YouTube")
    assert command is not None
    assert command.action == "play"
    assert command.query.casefold() == "chamak challo"


def test_hindi_play_song_command_extracts_title() -> None:
    command = parse_media_command("चमक चल्लो गाना चलाओ")
    assert command is not None
    assert command.action == "play"
    assert command.query == "चमक चल्लो"


def test_open_youtube_without_a_title() -> None:
    command = parse_media_command("YouTube kholo")
    assert command is not None
    assert command.action == "open"
