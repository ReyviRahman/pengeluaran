import json
import logging
import traceback

from google import genai
from google.genai import types

import config
import memory
import tools

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5


def _build_fallback_reply(function_response_parts: list[types.Part]) -> str:
    """Buat balasan sederhana dari hasil function response jika Gemini gagal generate final text."""
    lines = []
    for part in function_response_parts:
        fr = part.function_response
        if not fr:
            continue

        name = fr.name
        response = fr.response

        if not isinstance(response, dict):
            lines.append(f"Hasil {name}: {response}")
            continue

        status = response.get("status", "unknown")
        message = response.get("message", "")

        if status != "success":
            lines.append(f"Maaf, {message or 'terjadi kesalahan saat membaca data.'}")
            continue

        # Balasan untuk pengeluaran hari ini / tanggal tertentu.
        summary = response.get("summary", {})
        data = response.get("data", [])

        if isinstance(data, list) and data:
            total = summary.get("total_pengeluaran", 0)
            lines.append(f"{message or 'Berikut detailnya:'}")
            for item in data:
                if isinstance(item, dict):
                    tgl = item.get('Tgl', '')
                    ket = item.get('Keterangan', '')
                    pengeluaran = item.get('Pengeluaran', '')
                    lines.append(f"- {tgl}: {ket} ({pengeluaran})")
            if total:
                lines.append(f"Total pengeluaran: Rp {total:,}".replace(",", "."))
        elif isinstance(data, dict) and data:
            lines.append(f"{message or 'Berikut detailnya:'}")
            for key, value in data.items():
                lines.append(f"- {key}: {value}")
        else:
            lines.append(message or "Data berhasil dibaca.")

    return "\n".join(lines) if lines else "Maaf, saya tidak bisa membalas saat ini."


def _sanitize_history(history: list[types.Content]) -> list[types.Content]:
    """Validasi dan perbaiki urutan peran dalam riwayat untuk Gemini function calling.

    Aturan yang dijaga:
    - Peran user dan model harus selalu bergantian.
    - model:function_call harus diikuti user:function_response.
    - user:function_response harus didahului model:function_call.
    - Ronde function calling yang tidak lengkap di akhir history dihapus.
    - Pesan user biasa yang berurutan digabungkan.
    """

    def _is_function_call(content: types.Content) -> bool:
        return content.role == "model" and any(
            part.function_call for part in content.parts
        )

    def _is_function_response(content: types.Content) -> bool:
        return content.role == "user" and any(
            part.function_response for part in content.parts
        )

    sanitized: list[types.Content] = []

    for content in history:
        if _is_function_call(content):
            # function_call hanya valid jika didahului oleh user turn.
            if sanitized and sanitized[-1].role != "user":
                continue
            sanitized.append(content)
        elif _is_function_response(content):
            # function_response hanya valid jika didahului model:function_call.
            if not sanitized or sanitized[-1].role != "model" or not _is_function_call(
                sanitized[-1]
            ):
                continue
            sanitized.append(content)
        else:
            # Pesan user/model biasa.
            if not sanitized:
                if content.role == "user":
                    sanitized.append(content)
                continue

            if content.role == "user":
                if sanitized[-1].role == "model":
                    # Jika model sebelumnya adalah function_call, pesan user biasa
                    # tidak bisa langsung mengikutinya; hapus function_call-nya.
                    if _is_function_call(sanitized[-1]):
                        sanitized.pop()
                    sanitized.append(content)
                else:
                    # Dua user turn berurutan. Jika sebelumnya function_response,
                    # ronde function calling belum selesai (tidak ada balasan model).
                    # Hapus ronde tersebut lalu simpan pesan user terbaru.
                    if _is_function_response(sanitized[-1]):
                        while sanitized and sanitized[-1].role == "user":
                            sanitized.pop()
                        if sanitized and _is_function_call(sanitized[-1]):
                            sanitized.pop()
                    sanitized.append(content)
            elif content.role == "model":
                if sanitized[-1].role == "user":
                    sanitized.append(content)
                else:
                    # Dua model turn berurutan: pertahankan yang terbaru.
                    sanitized.pop()
                    sanitized.append(content)

    # Hapus ronde function calling yang tidak lengkap di akhir history.
    while sanitized:
        last = sanitized[-1]
        if _is_function_call(last):
            sanitized.pop()
        elif _is_function_response(last):
            sanitized.pop()
            if sanitized and _is_function_call(sanitized[-1]):
                sanitized.pop()
        else:
            break

    # Gabungkan user turn biasa yang berurutan.
    merged: list[types.Content] = []
    for content in sanitized:
        if content.role == "user" and not _is_function_response(content):
            if (
                merged
                and merged[-1].role == "user"
                and not _is_function_response(merged[-1])
            ):
                merged_parts = list(merged[-1].parts) + list(content.parts)
                merged[-1] = types.Content(role="user", parts=merged_parts)
                continue
        merged.append(content)

    return merged


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


async def generate_response(prompt: str, chat_id: int) -> str:
    """Mengirim prompt ke Gemini dan mengembalikan jawabannya.

    Riwayat percakapan untuk chat_id dibaca dari memory dan disertakan sebagai
    konteks. Gemini memutuskan sendiri apakah perlu memanggil tool. Jika memanggil
    tool, fungsi tersebut dieksekusi dan hasilnya dikirim kembali ke Gemini untuk
    menghasilkan respons akhir.
    """
    try:
        client = get_client()
        gemini_tools = _build_gemini_tools()

        system_instruction = (
            "Kamu adalah asisten keuangan pribadi yang ramah dan santai. "
            "Jawab pertanyaan umum seperti sapaan, salam, tanya kabar, atau "
            "percakapan santai lainnya secara langsung tanpa memanggil tool. "
            "Gunakan tool yang tersedia HANYA ketika user benar-benar meminta "
            "data keuangan, ingin mencatat pengeluaran, ingin menghapus data, "
            "atau meminta informasi spesifik dari Google Sheet. "
            "Jangan pernah mengarang atau menebak data keuangan; jika butuh data, "
            "panggil tool yang sesuai. "
            "Untuk pertanyaan seperti 'hai', 'halo', 'apa kabar', atau 'kamu siapa', "
            "balaslah secara natural tanpa tool."
        )

        # Simpan pesan user dan ambil riwayat percakapan.
        await memory.add_message(chat_id, "user", text=prompt)
        history = _sanitize_history(await memory.get_history(chat_id))

        function_response_parts: list[types.Part] = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=history,
                config=types.GenerateContentConfig(
                    tools=gemini_tools,
                    system_instruction=system_instruction,
                ),
            )

            # Tangani respons kosong atau tanpa candidates.
            if not response.candidates:
                logger.warning(
                    "Gemini mengembalikan respons tanpa candidates (prompt=%r).",
                    prompt,
                )
                reply = "Baik, kalau ada yang mau dicatat atau dicek, bilang aja ya."
                await memory.add_message(chat_id, "model", text=reply)
                return reply

            candidate = response.candidates[0]
            parts = candidate.content.parts

            # Cek apakah Gemini meminta pemanggilan fungsi.
            function_calls = [part.function_call for part in parts if part.function_call]

            if not function_calls:
                # Tidak ada tool call: ini jawaban final.
                reply = response.text or "Maaf, saya tidak bisa membalas saat ini."
                await memory.add_message(chat_id, "model", text=reply)
                return reply

            # Simpan pemanggilan fungsi dari model ke memory.
            await memory.add_message(chat_id, "model", parts=parts)

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

            # Simpan hasil tool ke memory dan ambil history terbaru.
            await memory.add_message(chat_id, "tool", parts=function_response_parts)
            history = _sanitize_history(await memory.get_history(chat_id))

        # Loop habis tanpa jawaban text -> jangan biarkan user digantung.
        logger.warning(
            "Gemini tidak mengembalikan teks final setelah %s iterasi tool.",
            MAX_TOOL_ITERATIONS,
        )
        reply = _build_fallback_reply(function_response_parts)
        await memory.add_message(chat_id, "model", text=reply)
        return reply

    except Exception as exc:
        logger.error("Gagal menghasilkan respons dari Gemini: %s", exc)
        logger.error("Traceback: %s", traceback.format_exc())
        return "Maaf, terjadi kesalahan saat memproses pesan kamu."
