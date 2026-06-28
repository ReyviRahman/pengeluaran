from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import agent


def _make_text_response(text: str):
    """Buat mock response Gemini yang hanya mengandung teks."""
    part = SimpleNamespace(text=text)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(candidates=[candidate], text=text, function_calls=[])


def test_run_agent_returns_text():
    """Prompt sederhana harus dijawab dengan teks dari Gemini."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_text_response(
        "Halo! Ada yang bisa saya bantu?"
    )

    with patch("agent.get_client", return_value=mock_client):
        reply, _ = agent.run_agent([], "halo")

    assert reply == "Halo! Ada yang bisa saya bantu?"
    mock_client.models.generate_content.assert_called_once()


def test_run_agent_returns_fallback_on_empty_text():
    """Jika Gemini mengembalikan teks kosong, fungsi harus mengembalikan fallback."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_text_response("")

    with patch("agent.get_client", return_value=mock_client):
        reply, _ = agent.run_agent([], "halo")

    assert reply == agent.FALLBACK_MESSAGE
