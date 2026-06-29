import base64
import json
import logging
from datetime import datetime
from pathlib import Path

from openai import OpenAI

import config
from tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS

logger = logging.getLogger(__name__)

# Client disimpan sebagai singleton.
_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY belum diatur di file .env")
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
        "Agustus", "September", "Oktober", "November", "Desember"]
MAX_TOOL_ITERATIONS = 5
FALLBACK_MESSAGE = ("Mohon maaf kak, Telegram kami sedang ada sedikit kendala🙏")


def render_system_prompt() -> str:
    """Baca prompts/system.md dan isi template variables."""
    raw = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")

    replacements = {
        "{{currentDateContext}}": (
            "Tanggal dan jam SAAT INI selalu diberikan di awal setiap pesan user "
            "(dalam tanda [Konteks: ...]). Jadikan itu satu-satunya acuan waktu untuk "
            "menghitung 'hari ini', 'besok', 'lusa', dan sebagainya."
        ),
    }
    for key, value in replacements.items():
        raw = raw.replace(key, value)
    return raw


SYSTEM_PROMPT = render_system_prompt()

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["parameters"],
        },
    }
    for tool in TOOL_DECLARATIONS
]


def _build_user_content(user_message: str, images: list[tuple[bytes, str]] | None = None) -> list[dict]:
    """Bangun konten pesan user dalam format OpenAI, termasuk gambar base64."""
    content = [{"type": "text", "text": user_message}]
    for img_bytes, mime in (images or []):
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
    return content


def run_agent(history: list, user_message: str,
            images: list[tuple[bytes, str]] | None = None) -> tuple[str, list]:
    """Jalankan satu giliran percakapan dengan OpenAI.

    Args:
        history: daftar pesan OpenAI dari giliran-giliran sebelumnya (opsional).
        user_message: pesan user terbaru.
        images: daftar (bytes, mime) gambar dari customer.

    Returns:
        (jawaban_text, history_baru)
    """
    now = datetime.now()
    date_ctx = (f"Hari ini {HARI[now.weekday()]}, {now.day} {BULAN[now.month - 1]} {now.year} "
                f"({now:%Y-%m-%d}), pukul {now:%H:%M}")

    if not user_message:
        user_message = "(customer mengirim gambar tanpa teks)"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    if history:
        messages.extend(history)

    messages.append({
        "role": "user",
        "content": _build_user_content(f"[Konteks: {date_ctx}]\n{user_message}", images),
    })

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = get_client().chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
                temperature=0.7,
            )

            choice = response.choices[0]
            message = choice.message
            messages.append(message)

            tool_calls = message.tool_calls
            if not tool_calls:
                return (message.content or FALLBACK_MESSAGE), messages

            tool_messages = []
            for tc in tool_calls:
                print(f"  [tool] {tc.function.name}({tc.function.arguments})")
                func = TOOL_FUNCTIONS.get(tc.function.name)
                if func is None:
                    result = {"error": f"Tool '{tc.function.name}' tidak dikenal."}
                else:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                        result = func(**args)
                    except Exception as e:
                        result = {"error": f"Tool gagal: {e}"}
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"result": result}, ensure_ascii=False),
                })
            messages.extend(tool_messages)

        return FALLBACK_MESSAGE, messages

    except Exception:
        logger.exception("Gagal memanggil OpenAI API")
        return FALLBACK_MESSAGE, messages
