import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from google.genai import types

import gemini


def _make_text_response(text: str):
    """Buat mock response Gemini yang hanya mengandung teks (tanpa function call)."""
    part = types.Part.from_text(text=text)
    content = types.Content(role="model", parts=[part])
    candidate = SimpleNamespace(content=content)
    response = SimpleNamespace(candidates=[candidate], text=text, function_calls=[])
    return response


def _make_function_call_response(function_name: str, args: dict):
    """Buat mock response Gemini yang memanggil satu function."""
    part = types.Part.from_function_call(name=function_name, args=args)
    content = types.Content(role="model", parts=[part])
    candidate = SimpleNamespace(content=content)
    response = SimpleNamespace(
        candidates=[candidate],
        text="",
        function_calls=[part.function_call],
    )
    return response


@pytest.mark.asyncio
async def test_greeting_does_not_trigger_tool():
    """Sapaan sederhana harus dijawab langsung tanpa memanggil tool."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_text_response(
        "Halo! Ada yang bisa saya bantu?"
    )

    with (
        patch("gemini.get_client", return_value=mock_client),
        patch("gemini.memory.add_message", new=AsyncMock()) as mock_add,
        patch("gemini.memory.get_history", return_value=[]) as mock_get_history,
    ):
        reply = await gemini.generate_response("halo", chat_id=12345)

    assert reply == "Halo! Ada yang bisa saya bantu?"
    mock_client.models.generate_content.assert_called_once()
    # Pastikan tidak ada function call yang disimpan.
    saved_model_calls = [
        call for call in mock_add.call_args_list if call.args[1] == "model"
    ]
    assert len(saved_model_calls) == 1
    args, kwargs = saved_model_calls[0]
    assert kwargs.get("text") == "Halo! Ada yang bisa saya bantu?"


@pytest.mark.asyncio
async def test_financial_question_triggers_tool_and_returns_final_text():
    """Pertanyaan keuangan memicu tool, lalu Gemini menghasilkan jawaban akhir."""
    tool_response = _make_function_call_response(
        "get_total_pengeluaran", args={}
    )
    final_response = _make_text_response(
        "Total pengeluaran kamu saat ini adalah Rp 100.000."
    )

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        tool_response,
        final_response,
    ]

    with (
        patch("gemini.get_client", return_value=mock_client),
        patch("gemini.memory.add_message", new=AsyncMock()) as mock_add,
        patch("gemini.memory.get_history", return_value=[]),
        patch("gemini.tools.TOOL_FUNCTIONS", {"get_total_pengeluaran": lambda: {"status": "success", "total_pengeluaran": "100000", "message": "Total pengeluaran saat ini adalah 100000"}}),
    ):
        reply = await gemini.generate_response(
            "total pengeluaran berapa", chat_id=12345
        )

    assert reply == "Total pengeluaran kamu saat ini adalah Rp 100.000."
    assert mock_client.models.generate_content.call_count == 2

    # Pastikan function call dan function response disimpan ke memory.
    saved_model_calls = [
        call for call in mock_add.call_args_list if call.args[1] == "model"
    ]
    saved_tool_calls = [
        call for call in mock_add.call_args_list if call.args[1] == "tool"
    ]
    assert len(saved_model_calls) == 2  # function call + final text
    assert len(saved_tool_calls) == 1
