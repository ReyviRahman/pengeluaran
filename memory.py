import json
import logging
from typing import Any

from google.genai import types
from sqlmodel import select, delete

import database
from models import ConversationMessage

logger = logging.getLogger(__name__)


def _serialize_parts(parts: list[types.Part]) -> tuple[str, str]:
    """Ubah list Gemini Part menjadi (message_type, json_content)."""
    if any(part.function_call for part in parts):
        data = {
            "function_calls": [
                {
                    "name": part.function_call.name,
                    "args": dict(part.function_call.args) if part.function_call.args else {},
                }
                for part in parts
                if part.function_call
            ]
        }
        return "function_call", json.dumps(data, ensure_ascii=False)

    if any(part.function_response for part in parts):
        data = {
            "function_responses": [
                {
                    "name": part.function_response.name,
                    "response": part.function_response.response,
                }
                for part in parts
                if part.function_response
            ]
        }
        return "function_response", json.dumps(data, ensure_ascii=False)

    texts = [part.text for part in parts if part.text]
    return "text", json.dumps({"text": " ".join(texts)}, ensure_ascii=False)


def _row_to_content(row: ConversationMessage) -> types.Content:
    """Rekonstruksi Gemini Content dari satu baris database."""
    role = "user" if row.role == "tool" else row.role
    parts: list[types.Part] = []

    try:
        data = json.loads(row.content)
    except json.JSONDecodeError:
        data = {}

    if row.message_type == "text":
        parts.append(types.Part.from_text(text=data.get("text", "")))
    elif row.message_type == "function_call":
        for fc in data.get("function_calls", []):
            parts.append(
                types.Part.from_function_call(
                    name=fc.get("name", ""),
                    args=fc.get("args", {}),
                )
            )
    elif row.message_type == "function_response":
        for fr in data.get("function_responses", []):
            parts.append(
                types.Part.from_function_response(
                    name=fr.get("name", ""),
                    response=fr.get("response", {}),
                )
            )

    return types.Content(role=role, parts=parts)


async def add_message(
    chat_id: int,
    role: str,
    text: str | None = None,
    parts: list[types.Part] | None = None,
) -> None:
    """Simpan satu pesan ke memory.

    Parameters
    ----------
    chat_id: ID chat Telegram.
    role: 'user', 'model', atau 'tool'.
    text: Konten teks (untuk pesan biasa).
    parts: List Gemini Part (untuk function call/response).
    """
    try:
        if parts:
            message_type, content = _serialize_parts(parts)
        else:
            message_type = "text"
            content = json.dumps({"text": text or ""}, ensure_ascii=False)

        message = ConversationMessage(
            chat_id=chat_id,
            role=role,
            message_type=message_type,
            content=content,
        )

        async with database.AsyncSessionLocal() as session:
            session.add(message)
            await session.commit()
    except Exception:
        logger.exception("Gagal menyimpan pesan ke memory (chat_id=%s)", chat_id)


async def get_history(chat_id: int, limit: int = 20) -> list[types.Content]:
    """Ambil riwayat percakapan terakhir untuk chat_id tertentu."""
    try:
        async with database.AsyncSessionLocal() as session:
            result = await session.execute(
                select(ConversationMessage)
                .where(ConversationMessage.chat_id == chat_id)
                .order_by(ConversationMessage.created_at.desc())
                .limit(limit)
            )
            rows = list(reversed(result.scalars().all()))
            return [_row_to_content(row) for row in rows]
    except Exception:
        logger.exception("Gagal membaca memory (chat_id=%s)", chat_id)
        return []


async def clear_history(chat_id: int) -> None:
    """Hapus semua riwayat percakapan untuk chat_id tertentu."""
    try:
        async with database.AsyncSessionLocal() as session:
            await session.execute(
                delete(ConversationMessage).where(
                    ConversationMessage.chat_id == chat_id
                )
            )
            await session.commit()
    except Exception:
        logger.exception("Gagal menghapus memory (chat_id=%s)", chat_id)
