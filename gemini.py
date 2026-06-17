import json
import logging

from google import genai
from google.genai import types

import config
import tools

logger = logging.getLogger(__name__)


def get_client():
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY belum diatur di file .env")
    return genai.Client(api_key=config.GEMINI_API_KEY)


def _build_gemini_tools() -> list[types.Tool]:
    """Mengubah TOOL_DECLARATIONS (dict) menjadi types.Tool untuk google-genai SDK."""
    declarations = []
    for decl in tools.TOOL_DECLARATIONS:
        parameters = decl.get("parameters", {"type": "object", "properties": {}})
        declarations.append(
            types.FunctionDeclaration(
                name=decl["name"],
                description=decl["description"],
                parameters=types.Schema(
                    type=parameters.get("type", "object"),
                    properties={
                        k: types.Schema(type=v.get("type", "string"), description=v.get("description", ""))
                        for k, v in parameters.get("properties", {}).items()
                    },
                    required=parameters.get("required", []),
                ),
            )
        )
    return [types.Tool(function_declarations=declarations)]


async def generate_response(prompt: str) -> str:
    """Mengirim prompt ke Gemini dan mengembalikan jawabannya.

    Jika Gemini memanggil salah satu tool, fungsi tersebut dieksekusi dan
    hasilnya dikirim kembali ke Gemini untuk menghasilkan respons akhir.
    """
    try:
        client = get_client()
        gemini_tools = _build_gemini_tools()

        system_instruction = (
            "Kamu adalah asisten keuangan pribadi. "
            "Setiap kali user bertanya tentang pengeluaran, saldo, atau data keuangan, "
            "kamu WAJIB memanggil tool yang tersedia untuk membaca data dari Google Sheet. "
            "Jangan pernah mengarang atau menebak jawaban. "
            "Jika user bertanya tentang tanggal hari ini, panggil get_current_date. "
            "Jika user bertanya 'pengeluaran hari ini', panggil get_expenses_today. "
            "Jika user bertanya pengeluaran tanggal tertentu dengan tahun lengkap, panggil get_expenses_by_date. "
            "Jika user bertanya pengeluaran tanggal tanpa tahun (misalnya '16 Juni' atau 'tanggal 16/06'), "
            "panggil get_expenses_by_day_month dengan day dan month sebagai integer. "
            "Jangan pernah menebak tahun sendiri."
        )

        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=gemini_tools,
                system_instruction=system_instruction,
            ),
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Cek apakah Gemini meminta pemanggilan fungsi.
        function_calls = [part.function_call for part in parts if part.function_call]

        if not function_calls:
            return response.text or "Maaf, saya tidak bisa membalas saat ini."

        # Proses setiap function call.
        function_response_parts = []
        for function_call in function_calls:
            function_name = function_call.name
            args = dict(function_call.args) if function_call.args else {}

            logger.info("Gemini memanggil fungsi: %s dengan args: %s", function_name, args)

            func = tools.TOOL_FUNCTIONS.get(function_name)
            if func is None:
                result = {"status": "error", "message": f"Fungsi '{function_name}' tidak dikenal"}
            else:
                result = func(**args)

            function_response_parts.append(
                types.Part.from_function_response(
                    name=function_name,
                    response=result,
                )
            )

        # Kirim hasil fungsi kembali ke Gemini untuk respons akhir.
        final_response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[
                types.Content(role="user", parts=[types.Part.from_text(text=prompt)]),
                candidate.content,
                types.Content(role="user", parts=function_response_parts),
            ],
        )

        return final_response.text or "Maaf, saya tidak bisa membalas saat ini."
    except Exception as exc:
        logger.error("Gagal menghasilkan respons dari Gemini: %s", exc)
        return "Maaf, terjadi kesalahan saat memproses pesan kamu."
