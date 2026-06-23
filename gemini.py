import json
import logging
import traceback

from google import genai
from google.genai import types

import config
import memory
import tools

logger = logging.getLogger(__name__)


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
    konteks. Jika Gemini memanggil salah satu tool, fungsi tersebut dieksekusi
    dan hasilnya dikirim kembali ke Gemini untuk menghasilkan respons akhir.
    """
    try:
        client = get_client()
        gemini_tools = _build_gemini_tools()

        system_instruction = (
            "Kamu adalah asisten keuangan pribadi. "
            "Setiap kali user bertanya tentang pengeluaran, saldo, atau data keuangan, "
            "kamu WAJIB memanggil tool yang tersedia untuk membaca data dari Google Sheet. "
            "Jangan pernah mengarang atau menebak jawaban. "
            "Jika user ingin mencatat pengeluaran baru, misalnya 'makan siang 50rb', "
            "'bayar parkir 10k', '16 Juni Makan Es Krim 20rb', atau 'beli pulsa 50.000', "
            "panggil insert_expense dengan seluruh pesan user sebagai parameter text. "
            "Jangan pernah memanggil insert_expense jika user tidak menyebutkan keterangan atau nominal. "
            "Jika user ingin menghapus pengeluaran terakhir, misalnya 'hapus pengeluaran terakhir', "
            "'batalkan input terakhir', atau 'salah input, hapus yang terakhir', panggil delete_last_expense. "
            "Jika user ingin menghapus pengeluaran tertentu, "
            "misalnya 'hapus pengeluaran makan siang tadi', 'hapus data tanggal 16/06/2026', "
            "'hapus 16 juni es krim 5rb', atau 'hapus es krim 5k', "
            "panggil delete_expense dengan seluruh pesan user sebagai parameter text. "
            "Tool tersebut akan mengekstrak tanggal, keterangan, dan nominal sendiri. "
            "Jika user bertanya tentang total pengeluaran, "
            "misalnya 'total pengeluaran berapa' atau 'berapa total pengeluaran ku', "
            "panggil get_total_pengeluaran. "
            "Jika user bertanya tentang saldo akhir, "
            "misalnya 'berapa saldo akhir ku' atau 'sisa saldo berapa', "
            "panggil get_saldo_akhir. "
            "Jika user bertanya ringkasan keuangan secara keseluruhan, "
            "misalnya 'ringkasan keuangan', panggil get_expense_summary. "
            "Jika user bertanya tentang tanggal hari ini, panggil get_current_date. "
            "Jika user bertanya 'pengeluaran hari ini', panggil get_expenses_today. "
            "Jika user bertanya pengeluaran tanggal tertentu dengan tahun lengkap, panggil get_expenses_by_date. "
            "Jika user bertanya pengeluaran tanggal tanpa tahun (misalnya '16 Juni' atau 'tanggal 16/06'), "
            "panggil get_expenses_by_day_month dengan day dan month sebagai integer. "
            "Jangan pernah menebak tahun sendiri."
        )

        # Simpan pesan user dan ambil riwayat percakapan.
        await memory.add_message(chat_id, "user", text=prompt)
        history = await memory.get_history(chat_id)

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
                "Gemini mengembalikan respons awal tanpa candidates (prompt=%r).",
                prompt,
            )
            reply = (
                "Baik, Reyyy. Kalau ada yang mau dicatat atau dicek, bilang aja ya."
            )
            await memory.add_message(chat_id, "model", text=reply)
            return reply

        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Cek apakah Gemini meminta pemanggilan fungsi.
        function_calls = [part.function_call for part in parts if part.function_call]

        if not function_calls:
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
        history = await memory.get_history(chat_id)

        # Kirim hasil fungsi kembali ke Gemini untuk respons akhir.
        try:
            final_response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=history,
                config=types.GenerateContentConfig(
                    tools=gemini_tools,
                    system_instruction=system_instruction,
                ),
            )

            if final_response.candidates and final_response.text:
                reply = final_response.text
            else:
                logger.warning(
                    "Gemini tidak mengembalikan teks final, fallback ke hasil tool."
                )
                reply = _build_fallback_reply(function_response_parts)
        except Exception as final_exc:
            logger.error(
                "Gagal generate final response dari Gemini: %s", final_exc
            )
            logger.error("Traceback: %s", traceback.format_exc())
            reply = _build_fallback_reply(function_response_parts)

        await memory.add_message(chat_id, "model", text=reply)
        return reply
    except Exception as exc:
        logger.error("Gagal menghasilkan respons dari Gemini: %s", exc)
        logger.error("Traceback: %s", traceback.format_exc())
        return "Maaf, terjadi kesalahan saat memproses pesan kamu."
