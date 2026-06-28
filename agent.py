import logging
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

import config
from tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS

logger = logging.getLogger(__name__)

# Client disimpan sebagai singleton. google-genai SDK memiliki underlying httpx
# session yang akan ditutup saat Client di-garbage-collect; membuat client baru
# tiap request sering menyebabkan error "Cannot send a request, as the client
# has been closed" (googleapis/python-genai#1763).
_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY belum diatur di file .env")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client

THINKING_LEVEL = "minimal"  # minimal = cepat & murah

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
        "Agustus", "September", "Oktober", "November", "Desember"]
MAX_TOOL_ITERATIONS = 5
FALLBACK_MESSAGE = ("Mohon maaf kak, Telegram kami sedang ada sedikit kendala🙏")

def render_system_prompt() -> str:
    """Baca prompts/system.md dan isi template variables.
    """
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

GENERATE_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
    thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL),
    temperature=0.7,
)

def run_agent(history: list, user_message: str,
            images: list[tuple[bytes, str]] | None = None) -> tuple[str, list]:
    """Jalankan satu giliran percakapan.

    Args:
        history: list of types.Content dari giliran-giliran sebelumnya
        user_message: pesan user terbaru (sudah digabung buffer kalau dari WA)
        images: daftar (bytes, mime) gambar dari customer untuk dibaca Gemini

    Returns:
        (jawaban_text, history_baru) -- history_baru sudah termasuk giliran ini,
        siap disimpan oleh memory.py.
    """
    # Konteks waktu di-inject sebagai konteks pesan, BUKAN ke system prompt,
    # supaya system prompt tetap statis (cache-friendly).
    now = datetime.now()
    date_ctx = (f"Hari ini {HARI[now.weekday()]}, {now.day} {BULAN[now.month - 1]} {now.year} "
                f"({now:%Y-%m-%d}), pukul {now:%H:%M}")

    if not user_message:
        user_message = "(customer mengirim gambar tanpa teks)"

    parts = [types.Part(text=f"[Konteks: {date_ctx}]\n{user_message}")]
    for img_bytes, mime in (images or []):
        parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))

    contents = list(history)
    contents.append(types.Content(role="user", parts=parts))

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = get_client().models.generate_content(
                model=config.GEMINI_MODEL,
                contents=contents,
                config=GENERATE_CONFIG,
            )

            candidate = response.candidates[0]
            contents.append(candidate.content)  # simpan giliran model (text/function call)

            function_calls = response.function_calls or []
            if not function_calls:
                # Tidak ada tool call -> ini jawaban final
                return (response.text or FALLBACK_MESSAGE), contents

            # Eksekusi SEMUA function call di giliran ini, balikan hasilnya
            result_parts = []
            for fc in function_calls:
                print(f"  [tool] {fc.name}({dict(fc.args)})")  # log untuk demo workshop
                func = TOOL_FUNCTIONS.get(fc.name)
                if func is None:
                    result = {"error": f"Tool '{fc.name}' tidak dikenal."}
                else:
                    try:
                        result = func(**dict(fc.args))
                    except Exception as e:  # tool gagal != agent mati
                        result = {"error": f"Tool gagal: {e}"}
                result_parts.append(types.Part.from_function_response(
                    name=fc.name, response={"result": result},
                ))
            contents.append(types.Content(role="user", parts=result_parts))

        # Loop habis tanpa jawaban text -> jangan biarkan customer digantung
        return FALLBACK_MESSAGE, contents

    except Exception:
        logger.exception("Gagal memanggil Gemini API")
        return FALLBACK_MESSAGE, contents
