"""Deterministic relay-command parsing independent of an LLM response."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedRelayCommand:
    device: str
    state: bool


@dataclass(frozen=True, slots=True)
class ParsedMediaCommand:
    """An explicit request to control YouTube on the trusted backend laptop."""

    action: str
    query: str = ""


_DEVICES = {
    "light": ("light", "batti", "bulb", "lamp", "roshni"),
    "fan": ("fan", "pankha"),
}
_ON_WORDS = ("on", "chalu", "chalao", "chala", "jalao", "jala", "start")
_OFF_WORDS = ("off", "band", "bujhao", "bujha", "stop")
_ACTION_WORDS = ("turn", "switch", "karo", "kar do", "kar", "please", "do")
_STATUS_MARKERS = ("is ", "kya ", "hai", "status", "whether", "check")


def _normalise(text: str) -> str:
    """Normalise common Hindi device/action words to Latin tokens."""

    replacements = {
        "लाइट": " light ", "बत्ती": " light ", "बल्ब": " bulb ", "रोशनी": " roshni ",
        "पंखा": " fan ", "चालू": " on ", "ऑन": " on ", "बंद": " off ",
        "ऑफ": " off ", "जलाओ": " jalao ", "जला": " jala ", "बुझाओ": " bujhao ",
        "बुझा": " bujha ", "करो": " karo ", "कर दो": " kar do ",
    }
    normalised = text.casefold()
    for source, target in replacements.items():
        normalised = normalised.replace(source, target)
    return re.sub(r"\s+", " ", normalised).strip()


def _positions(text: str, words: tuple[str, ...]) -> list[int]:
    positions: list[int] = []
    for word in words:
        positions.extend(match.start() for match in re.finditer(rf"\b{re.escape(word)}\b", text))
    return sorted(positions)


def _looks_like_status_question(text: str) -> bool:
    return any(marker in text for marker in _STATUS_MARKERS)


def parse_relay_commands(text: str) -> list[ParsedRelayCommand]:
    """Return explicit light/fan commands in their spoken order.

    A model never decides device control.  This parser intentionally ignores
    vague status questions such as "is the light on" unless an action verb is
    present, avoiding an accidental relay toggle.
    """

    normalised = _normalise(text)
    action_positions = _positions(normalised, _ACTION_WORDS)
    status_question = _looks_like_status_question(normalised) and not action_positions
    commands_with_positions: list[tuple[int, ParsedRelayCommand]] = []

    for device, aliases in _DEVICES.items():
        device_positions = _positions(normalised, aliases)
        if not device_positions:
            continue

        on_positions = _positions(normalised, _ON_WORDS)
        off_positions = _positions(normalised, _OFF_WORDS)
        candidate_positions = [(position, True) for position in on_positions] + [
            (position, False) for position in off_positions
        ]
        if not candidate_positions or status_question:
            continue

        # A command word must be close to the device name, or the phrase must
        # include an unambiguous action verb ("turn on the fan").
        closest: tuple[int, int, bool] | None = None
        for state_position, state in candidate_positions:
            for device_position in device_positions:
                distance = abs(state_position - device_position)
                if distance <= 24 or action_positions:
                    rank = (distance, state_position, state)
                    if closest is None or rank < closest:
                        closest = rank
        if closest is not None:
            commands_with_positions.append(
                (min(device_positions, key=lambda value: abs(value - closest[1])), ParsedRelayCommand(device, closest[2]))
            )

    return [command for _, command in sorted(commands_with_positions, key=lambda item: item[0])]


def parse_media_command(text: str) -> ParsedMediaCommand | None:
    """Recognise only clear YouTube play/open requests.

    This deliberately requires an action and YouTube/song/video cue. It avoids
    launching a browser for ordinary conversation that merely mentions music.
    """

    normalised = text.casefold()
    replacements = {
        "यूट्यूब": " youtube ",
        "यू ट्यूब": " youtube ",
        "गाना": " song ",
        "सॉन्ग": " song ",
        "वीडियो": " video ",
        "चलाओ": " play ",
        "बजाओ": " play ",
        "खोलो": " open ",
        "खोल": " open ",
        "लगाओ": " play ",
    }
    for source, target in replacements.items():
        normalised = normalised.replace(source, target)
    normalised = re.sub(r"\s+", " ", normalised).strip()

    has_youtube = "youtube" in normalised
    has_play = bool(re.search(r"\b(play|chalao|bajao|lagao)\b", normalised))
    has_open = bool(re.search(r"\b(open|kholo)\b", normalised))
    has_media = bool(re.search(r"\b(song|music|video)\b", normalised))
    if has_open and has_youtube and not has_play and not has_media:
        return ParsedMediaCommand("open")
    if not has_play or not (has_youtube or has_media):
        return None

    query = normalised
    query = re.sub(r"\b(open|youtube|on|in|par|pe|play|song|music|video|please|karo|kar do)\b", " ", query)
    query = re.sub(r"\s+", " ", query).strip(" .,!?:;'-")
    # English commands often put the requested title after "play song". The
    # original transcript retains its casing and is better for YouTube search.
    original = " ".join(text.split()).strip()
    title = re.sub(
        r"(?i)\b(open\s+)?youtube(\s+and)?\s+(play\s+)?|\b(play|open)\s+(a\s+)?(song|music|video)\b|\b(play|open|chalao|bajao|lagao)\b|यूट्यूब|यू ट्यूब|गाना|सॉन्ग|वीडियो|चलाओ|बजाओ|खोलो|लगाओ",
        " ",
        original,
    )
    title = re.sub(r"(?i)\b(on|in|par|pe)\s+youtube\b|\byoutube\b", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" .,!?:;'-")
    return ParsedMediaCommand("play", title or query)
