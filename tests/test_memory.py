import json
from types import SimpleNamespace

from google.genai import types

import memory


def _make_row(role: str, message_type: str, content: str):
    """Buat objek palsu yang cukup mirip ConversationMessage untuk testing."""
    return SimpleNamespace(role=role, message_type=message_type, content=content)


def test_serialize_and_reconstruct_text():
    parts = [types.Part.from_text(text="Halo, bot!")]
    message_type, content = memory._serialize_parts(parts)

    assert message_type == "text"
    assert json.loads(content) == {"text": "Halo, bot!"}

    row = _make_row("user", message_type, content)
    reconstructed = memory._row_to_content(row)

    assert reconstructed.role == "user"
    assert len(reconstructed.parts) == 1
    assert reconstructed.parts[0].text == "Halo, bot!"


def test_serialize_and_reconstruct_function_call():
    parts = [
        types.Part.from_function_call(
            name="insert_expense",
            args={"text": "makan siang 50rb"},
        )
    ]
    message_type, content = memory._serialize_parts(parts)

    assert message_type == "function_call"
    row = _make_row("model", message_type, content)
    reconstructed = memory._row_to_content(row)

    assert reconstructed.role == "model"
    assert len(reconstructed.parts) == 1
    assert reconstructed.parts[0].function_call.name == "insert_expense"
    assert dict(reconstructed.parts[0].function_call.args) == {
        "text": "makan siang 50rb"
    }


def test_serialize_and_reconstruct_function_response():
    parts = [
        types.Part.from_function_response(
            name="insert_expense",
            response={"status": "success", "message": "Tersimpan"},
        )
    ]
    message_type, content = memory._serialize_parts(parts)

    assert message_type == "function_response"
    row = _make_row("tool", message_type, content)
    reconstructed = memory._row_to_content(row)

    # Function response harus direkonstruksi sebagai role user untuk Gemini.
    assert reconstructed.role == "user"
    assert len(reconstructed.parts) == 1
    assert reconstructed.parts[0].function_response.name == "insert_expense"
    assert reconstructed.parts[0].function_response.response == {
        "status": "success",
        "message": "Tersimpan",
    }


def test_multiple_function_calls_in_one_part():
    parts = [
        types.Part.from_function_call(name="get_current_date", args={}),
        types.Part.from_function_call(
            name="get_expenses_today", args={}
        ),
    ]
    message_type, content = memory._serialize_parts(parts)

    assert message_type == "function_call"
    row = _make_row("model", message_type, content)
    reconstructed = memory._row_to_content(row)

    assert len(reconstructed.parts) == 2
    assert reconstructed.parts[0].function_call.name == "get_current_date"
    assert reconstructed.parts[1].function_call.name == "get_expenses_today"
