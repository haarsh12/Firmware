from app.assistant import build_prompt, limit_reply
from app.command_parser import ParsedRelayCommand


def test_prompt_includes_recent_dialogue_for_follow_up_questions() -> None:
    prompt = build_prompt(
        "What about that?",
        {"temperature": 25.0, "humidity": 60.0, "mqAnalog": 0, "ldr": 0},
        {"light": False, "fan": False},
        [ParsedRelayCommand("light", True)],
        [("Tell me the temperature", "The temperature is 25 degrees Celsius.")],
    )
    assert "Tell me the temperature" in prompt
    assert "The temperature is 25 degrees Celsius." in prompt
    assert "light on" in prompt


def test_limit_reply_avoids_incomplete_single_word_answer() -> None:
    assert limit_reply("Main", 45) == "Mujhe theek se jawab nahi mila. Dobara poochhiye."
