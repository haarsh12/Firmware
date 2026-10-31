from app.command_parser import ParsedRelayCommand, parse_relay_commands


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
