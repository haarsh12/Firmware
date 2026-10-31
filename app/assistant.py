"""Smart-home prompt construction and safe response fallback."""

from __future__ import annotations

from app.command_parser import ParsedRelayCommand


def build_prompt(
    user_text: str,
    sensors: dict[str, int | float],
    relays: dict[str, bool],
    commands: list[ParsedRelayCommand],
    history: list[tuple[str, str]] | None = None,
) -> str:
    command_summary = ", ".join(
        f"{command.device} {'on' if command.state else 'off'}" for command in commands
    ) or "none"
    recent_dialogue = "\n".join(
        f"User: {previous_user}\nAssistant: {previous_reply}"
        for previous_user, previous_reply in (history or [])[-6:]
    ) or "No earlier conversation in this connection."
    return f"""You are a helpful, natural smart-home voice assistant.
Rules:
- Reply in the user's language. Hindi/English/Hinglish are all allowed.
- Answer the user's actual question directly, in one short, complete answer.
- Do not start an answer and leave it incomplete. Avoid headings, markdown, or filler.
- If the question is genuinely ambiguous, ask one clear short follow-up question.
- Be honest: only these already parsed commands will be sent to the relay board: {command_summary}.
- Do not invent sensor values or claim an action succeeded if the relay board is unavailable.

Current relay states: light={'on' if relays['light'] else 'off'}, fan={'on' if relays['fan'] else 'off'}.
Current sensors: temperature={sensors['temperature']} C, humidity={sensors['humidity']} %, gas={sensors['mqAnalog']}, light_level={sensors['ldr']}.
Recent conversation:
{recent_dialogue}
User said: {user_text}
"""


def limit_reply(text: str, max_words: int) -> str:
    compact = " ".join(text.split())
    words = compact.split(" ")
    if not compact or len(words) < 2:
        return "Mujhe theek se jawab nahi mila. Dobara poochhiye."
    if len(words) <= max_words:
        return compact

    # Preserve a complete short sentence when possible instead of cutting a
    # response at arbitrary word, which previously produced replies like
    # "Namaste! Main".
    shortened = " ".join(words[:max_words]).rstrip(" ,;:-")
    last_stop = max(shortened.rfind("."), shortened.rfind("!"), shortened.rfind("?"))
    if last_stop >= max(10, len(shortened) // 2):
        return shortened[: last_stop + 1]
    return f"{shortened}."


def fallback_reply(commands: list[ParsedRelayCommand]) -> str:
    if not commands:
        return "Main abhi aapka sawaal samajh nahi paaya. Kripya dobara boliye."
    labels = " aur ".join(f"{item.device} {'on' if item.state else 'off'}" for item in commands)
    return f"Theek hai, {labels} kar raha hun."
