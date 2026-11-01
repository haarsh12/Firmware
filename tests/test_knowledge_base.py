from app.knowledge_base import chunk_text


def test_chunk_text_keeps_all_content_with_overlap() -> None:
    text = " ".join(f"word{index}" for index in range(500))
    chunks = chunk_text(text, chunk_size=120, overlap=20)
    assert len(chunks) > 2
    assert chunks[0].startswith("word0")
    assert chunks[-1].endswith("word499")


def test_chunk_text_discards_empty_input() -> None:
    assert chunk_text("  \n  ") == []
