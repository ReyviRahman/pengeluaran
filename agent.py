import logging

from google import genai

import config

logger = logging.getLogger(__name__)


def get_client():
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY belum diatur di file .env")
    return genai.Client(api_key=config.GEMINI_API_KEY)


def generate_response(prompt: str) -> str:
    """Mengirim prompt ke Gemini dan mengembalikan jawabannya."""
    try:
        client = get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[prompt],
        )
        return response.text or "Maaf, saya tidak bisa membalas saat ini."
    except Exception as exc:
        logger.error("Gagal menghasilkan respons dari Gemini: %s", exc)
        return "Maaf, terjadi kesalahan saat memproses pesan kamu."
