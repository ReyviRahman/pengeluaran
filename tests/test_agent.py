import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import agent


def _make_text_response(text: str):
    """Buat mock response OpenAI yang hanya mengandung teks."""
    message = SimpleNamespace(content=text, role="assistant", tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    return SimpleNamespace(choices=[choice])


def test_run_agent_returns_text():
    """Prompt sederhana harus dijawab dengan teks dari OpenAI."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_text_response(
        "Halo! Ada yang bisa saya bantu?"
    )

    with patch("agent.get_client", return_value=mock_client):
        reply, _ = agent.run_agent([], "halo")

    assert reply == "Halo! Ada yang bisa saya bantu?"
    mock_client.chat.completions.create.assert_called_once()


def test_run_agent_returns_fallback_on_empty_text():
    """Jika OpenAI mengembalikan teks kosong, fungsi harus mengembalikan fallback."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _make_text_response("")

    with patch("agent.get_client", return_value=mock_client):
        reply, _ = agent.run_agent([], "halo")

    assert reply == agent.FALLBACK_MESSAGE


def test_run_agent_executes_tool_call():
    """Jika OpenAI memanggil tool, hasil tool dikirim kembali dan balasan final direturn."""
    tool_call = SimpleNamespace(
        id="call_123",
        function=SimpleNamespace(
            name="add_expense",
            arguments=json.dumps({"keterangan": "es krim", "jumlah": 8000}),
        ),
        type="function",
    )
    tool_message = SimpleNamespace(
        content=None,
        role="assistant",
        tool_calls=[tool_call],
    )
    tool_choice = SimpleNamespace(message=tool_message, finish_reason="tool_calls")

    final_message = SimpleNamespace(
        content="Pengeluaran es krim 8k sudah dicatat.",
        role="assistant",
        tool_calls=None,
    )
    final_choice = SimpleNamespace(message=final_message, finish_reason="stop")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        SimpleNamespace(choices=[tool_choice]),
        SimpleNamespace(choices=[final_choice]),
    ]

    with patch("agent.get_client", return_value=mock_client):
        reply, _ = agent.run_agent([], "es krim 8k")

    assert reply == "Pengeluaran es krim 8k sudah dicatat."
    assert mock_client.chat.completions.create.call_count == 2
