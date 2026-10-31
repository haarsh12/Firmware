"""Smart-home prompt construction and safe response fallback."""

from __future__ import annotations

from app.command_parser import ParsedRelayCommand


def build_prompt(
    user_text: str,
    sensors: dict[str, int | float],
    relays: dict[str, bool],
    commands: list[ParsedRelayCommand],
) -> str:
    command_summary = ", ".join(
        f"{command.device} {'on' if command.state else 'off'}" for command in commands
    ) or "none"
    return f"""You are a concise home-automation voice assistant.
Rules:
- Reply only in clear Roman Hindi/Hinglish, never Devanagari.
- Use at most 15 words.
- Be honest: only these already parsed commands will be sent to the relay board: {command_summary}.
- Do not invent sensor values or claim an action succeeded if the relay board is unavailable.

Current relay states: light={'on' if relays['light'] else 'off'}, fan={'on' if relays['fan'] else 'off'}.
Current sensors: temperature={sensors['temperature']} C, humidity={sensors['humidity']} %, gas={sensors['mqAnalog']}, light_level={sensors['ldr']}.
User said: {user_text}
"""


def limit_reply(text: str, max_words: int) -> str:
    compact = " ".join(text.split())
    words = compact.split(" ")
    return " ".join(words[:max_words]) if compact else "Samajh nahi aaya, phir se boliye."


def fallback_reply(commands: list[ParsedRelayCommand]) -> str:
    if not commands:
        return "Samajh nahi aaya, phir se boliye."
    labels = " aur ".join(f"{item.device} {'on' if item.state else 'off'}" for item in commands)
    return f"Theek hai, {labels} kar raha hun."
