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


def _content(role: str, parts: list):
    return types.Content(role=role, parts=parts)


def test_sanitize_history_keeps_valid_conversation():
    """History yang sudah valid tidak boleh diubah."""
    history = [
        _content("user", [types.Part.from_text(text="halo")]),
        _content("model", [types.Part.from_text(text="Halo juga!")]),
    ]
    sanitized = gemini._sanitize_history(history)
    assert len(sanitized) == 2
    assert sanitized[0].parts[0].text == "halo"
    assert sanitized[1].parts[0].text == "Halo juga!"


def test_sanitize_history_removes_trailing_function_call():
    """Function call tanpa function response di akhir history harus dibuang."""
    history = [
        _content("user", [types.Part.from_text(text="total pengeluaran")]),
        _content(
            "model",
            [types.Part.from_function_call(name="get_total_pengeluaran", args={})],
        ),
    ]
    sanitized = gemini._sanitize_history(history)
    assert len(sanitized) == 1
    assert sanitized[0].role == "user"


def test_sanitize_history_removes_trailing_function_response():
    """Function response tanpa balasan model di akhir harus dibuang bersama function call-nya."""
    history = [
        _content("user", [types.Part.from_text(text="total pengeluaran")]),
        _content(
            "model",
            [types.Part.from_function_call(name="get_total_pengeluaran", args={})],
        ),
        _content(
            "user",
            [
                types.Part.from_function_response(
                    name="get_total_pengeluaran",
                    response={"status": "success", "total_pengeluaran": "100000"},
                )
            ],
        ),
    ]
    sanitized = gemini._sanitize_history(history)
    assert len(sanitized) == 1
    assert sanitized[0].role == "user"


def test_sanitize_history_removes_function_call_before_new_user_text():
    """Jika user mengirim pesan biasa setelah function call, ronde tersebut dibuang dan pesan user digabung."""
    history = [
        _content("user", [types.Part.from_text(text="total pengeluaran")]),
        _content(
            "model",
            [types.Part.from_function_call(name="get_total_pengeluaran", args={})],
        ),
        _content("user", [types.Part.from_text(text="halo")]),
    ]
    sanitized = gemini._sanitize_history(history)
    assert len(sanitized) == 1
    assert sanitized[0].role == "user"
    assert sanitized[0].parts[0].text == "total pengeluaran"
    assert sanitized[0].parts[1].text == "halo"


def test_sanitize_history_keeps_complete_function_round():
    """Ronde function calling yang lengkap (user -> model:function_call -> user:function_response -> model:text) tetap ada."""
    history = [
        _content("user", [types.Part.from_text(text="total pengeluaran")]),
        _content(
            "model",
            [types.Part.from_function_call(name="get_total_pengeluaran", args={})],
        ),
        _content(
            "user",
            [
                types.Part.from_function_response(
                    name="get_total_pengeluaran",
                    response={"status": "success", "total_pengeluaran": "100000"},
                )
            ],
        ),
        _content("model", [types.Part.from_text(text="Totalnya Rp 100.000.")]),
    ]
    sanitized = gemini._sanitize_history(history)
    assert len(sanitized) == 4
    assert sanitized[3].parts[0].text == "Totalnya Rp 100.000."
