import logging
import os
import traceback
from datetime import datetime
from typing import Any
import re

import gspread
from gspread.exceptions import APIError, WorksheetNotFound

import config

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

logger = logging.getLogger(__name__)

# Header sheet: Tgl | Keterangan | Pengeluaran | Saldo Awal | Total Pengeluaran | Saldo Akhir
HEADER = ["Tgl", "Keterangan", "Pengeluaran", "Saldo Awal", "Total Pengeluaran", "Saldo Akhir"]


def _format_error(exc: Exception, context: str) -> dict[str, Any]:
    """Membuat error response dengan pesan yang jelas dan traceback untuk log."""
    error_type = type(exc).__name__
    error_message = str(exc) or "Tidak ada pesan error"

    # Jika exception ini dibungkus (raise PermissionError from exc), ambil pesan dari cause.
    cause = getattr(exc, "__cause__", None)
    cause_message = str(cause) if cause else ""

    tb = traceback.format_exc()
    logger.exception("%s: [%s] %s", context, error_type, error_message)

    user_message = f"[{error_type}] {error_message}"
    if cause_message and cause_message not in error_message:
        user_message += f" (caused by: {cause_message})"

    # Berikan hint spesifik untuk masalah umum.
    if isinstance(exc, FileNotFoundError):
        user_message += (
            f". Pastikan file credentials ada di path: {config.GOOGLE_SHEETS_CREDENTIALS_PATH}"
        )
    elif isinstance(exc, PermissionError):
        user_message += (
            ". Kemungkinan penyebab: (1) file credentials.json tidak bisa dibaca, "
            "(2) Google Sheet belum di-share ke email service account, "
            "atau (3) Google Sheets API belum di-enable."
        )
    elif isinstance(exc, APIError):
        if "404" in error_message:
            user_message += (
                f". Spreadsheet ID '{config.SPREADSHEET_ID}' mungkin salah atau sheet belum di-share "
                f"ke email service account."
            )
        elif "403" in error_message:
            user_message += (
                ". Akses ditolak. Pastikan Google Sheet sudah di-share ke email service account "
                "yang ada di file credentials.json."
            )
    elif isinstance(exc, WorksheetNotFound):
        user_message += f". Worksheet yang dicari: '{config.SHEET_NAME}'"
    elif isinstance(exc, ValueError) and "SPREADSHEET_ID" in error_message:
        user_message += ". Isi SPREADSHEET_ID di file .env"

    return {"status": "error", "data": [], "message": user_message, "traceback": tb}


def _get_sheets_client() -> gspread.Client:
    """Membuat client gspread menggunakan service account."""
    logger.info("Menggunakan credentials: %s", config.GOOGLE_SHEETS_CREDENTIALS_PATH)

    if not os.path.exists(config.GOOGLE_SHEETS_CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"File credentials tidak ditemukan: {config.GOOGLE_SHEETS_CREDENTIALS_PATH}"
        )

    try:
        return gspread.service_account(filename=config.GOOGLE_SHEETS_CREDENTIALS_PATH)
    except Exception as exc:
        logger.exception("Gagal membuat Google Sheets client")
        raise


def _get_worksheet() -> gspread.Worksheet:
    """Membuka worksheet yang dikonfigurasi di .env."""
    if not config.SPREADSHEET_ID:
        raise ValueError("SPREADSHEET_ID belum diatur di .env")

    logger.info("Membuka spreadsheet: %s, worksheet: %s", config.SPREADSHEET_ID, config.SHEET_NAME)

    client = _get_sheets_client()

    try:
        spreadsheet = client.open_by_key(config.SPREADSHEET_ID)
    except APIError as exc:
        status = getattr(exc.response, "status_code", None)
        if status == 403:
            raise PermissionError(
                "Google Sheet belum di-share ke email service account atau "
                "Google Sheets API belum di-enable."
            ) from exc
        if status == 404:
            raise PermissionError(
                f"Spreadsheet ID '{config.SPREADSHEET_ID}' tidak ditemukan."
            ) from exc
        raise

    try:
        return spreadsheet.worksheet(config.SHEET_NAME)
    except WorksheetNotFound:
        raise WorksheetNotFound(f"Sheet '{config.SHEET_NAME}' tidak ditemukan")


def _get_sheet_values() -> list[list[str]]:
    """Membaca seluruh data sheet mulai dari A2."""
    worksheet = _get_worksheet()
    values = worksheet.get_values("A2:F")
    logger.info("Berhasil membaca %s baris data", len(values))
    return values


def check_sheet_connection() -> dict[str, Any]:
    """Endpoint diagnosis untuk memeriksa koneksi ke Google Sheet."""
    try:
        values = _get_sheet_values()
        return {
            "status": "success",
            "message": f"Koneksi berhasil. Sheet memiliki {len(values)} baris data.",
            "credentials_path": config.GOOGLE_SHEETS_CREDENTIALS_PATH,
            "spreadsheet_id": config.SPREADSHEET_ID,
            "sheet_name": config.SHEET_NAME,
            "rows": len(values),
        }
    except Exception as exc:
        error_response = _format_error(exc, "Gagal terhubung ke Google Sheet")
        return {
            "status": error_response["status"],
            "message": error_response["message"],
            "credentials_path": config.GOOGLE_SHEETS_CREDENTIALS_PATH,
            "spreadsheet_id": config.SPREADSHEET_ID,
            "sheet_name": config.SHEET_NAME,
        }


def get_cell_e2() -> dict[str, Any]:
    """Baca nilai cell E2 dari Google Sheet yang dikonfigurasi."""
    try:
        worksheet = _get_worksheet()
        value = worksheet.acell("E2").value
        return {
            "status": "success",
            "cell": "E2",
            "value": value,
            "spreadsheet_id": config.SPREADSHEET_ID,
            "sheet_name": config.SHEET_NAME,
        }
    except Exception as exc:
        return _format_error(exc, "Gagal membaca cell E2")


def get_cell_f2() -> dict[str, Any]:
    """Baca nilai cell F2 (saldo akhir) dari Google Sheet yang dikonfigurasi."""
    try:
        worksheet = _get_worksheet()
        value = worksheet.acell("F2").value
        return {
            "status": "success",
            "cell": "F2",
            "value": value,
            "spreadsheet_id": config.SPREADSHEET_ID,
            "sheet_name": config.SHEET_NAME,
        }
    except Exception as exc:
        return _format_error(exc, "Gagal membaca cell F2")


def get_total_pengeluaran() -> dict[str, Any]:
    """Baca total pengeluaran dari cell E2 Google Sheet."""
    try:
        worksheet = _get_worksheet()
        value = worksheet.acell("E2").value
        return {
            "status": "success",
            "total_pengeluaran": value,
            "message": f"Total pengeluaran saat ini adalah {value}",
        }
    except Exception as exc:
        return _format_error(exc, "Gagal membaca total pengeluaran")


def get_saldo_akhir() -> dict[str, Any]:
    """Baca saldo akhir dari cell F2 Google Sheet."""
    try:
        worksheet = _get_worksheet()
        value = worksheet.acell("F2").value
        return {
            "status": "success",
            "saldo_akhir": value,
            "message": f"Saldo akhir kamu saat ini adalah {value}",
        }
    except Exception as exc:
        return _format_error(exc, "Gagal membaca saldo akhir")


# Mapping nama bulan Indonesia ke bahasa Inggris untuk parsing tanggal.
_BULAN_ID_TO_EN = {
    "januari": "January",
    "februari": "February",
    "maret": "March",
    "april": "April",
    "mei": "May",
    "juni": "June",
    "juli": "July",
    "agustus": "August",
    "september": "September",
    "oktober": "October",
    "november": "November",
    "desember": "December",
}

def _parse_amount(value: str) -> int:
    """Parse nominal dari string, mendukung format Indonesia dan singkatan.

    Contoh:
    - 50000, Rp 50.000, 50,000 -> 50000
    - 10rb, 1rb, 15k, 2k -> 15000, 1000, 15000, 2000
    - 1jt, 2.5jt -> 1000000, 2500000
    """
    if not value:
        return 0

    value = str(value).lower().strip()
    value = value.replace("rp", "")
    value = value.replace(" ", "")

    multiplier = 1
    if value.endswith("rb"):
        multiplier = 1000
        value = value[:-2]
    elif value.endswith("k"):
        multiplier = 1000
        value = value[:-1]
    elif value.endswith("jt"):
        multiplier = 1_000_000
        value = value[:-2]

    value = value.replace(".", "")
    value = value.replace(",", "")
    value = value.strip()

    try:
        return int(float(value) * multiplier)
    except ValueError:
        return 0


def _parse_date(date_str: str) -> str:
    """Normalisasi format tanggal menjadi YYYY-MM-DD.

    Mendukung:
    - 16/06/2026
    - 16-06-2026
    - 2026-06-16
    - 16 Jun 2026
    - 16 Juni 2026
    - Selasa, 16 Juni 2026
    """
    if not date_str:
        return ""

    date_str = str(date_str).strip().lower()

    # Hapus nama hari Indonesia di depan tanggal
    # Contoh: "Selasa, 16 Juni 2026" -> "16 Juni 2026"
    date_str = re.sub(
        r"^(senin|selasa|rabu|kamis|jumat|jum'at|sabtu|minggu)\s*,?\s*",
        "",
        date_str,
    )

    # Konversi nama bulan Indonesia ke Inggris agar strptime bisa parse
    for id_month, en_month in _BULAN_ID_TO_EN.items():
        if id_month in date_str:
            date_str = date_str.replace(id_month, en_month)
            break

    date_str = date_str.title()

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d/%m/%y",
        "%d-%m-%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Fallback untuk tanggal tanpa tahun, gunakan tahun saat ini.
    yearless_formats = [
        "%d %b",
        "%d %B",
        "%d/%m",
        "%d-%m",
    ]
    for fmt in yearless_formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            now = datetime.now()
            return parsed.replace(year=now.year).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return date_str


def _row_to_dict(row: list[str]) -> dict[str, Any]:
    """Mengubah satu baris sheet menjadi dictionary berdasarkan header."""
    return {
        "Tgl": row[0] if len(row) > 0 else "",
        "Keterangan": row[1] if len(row) > 1 else "",
        "Pengeluaran": row[2] if len(row) > 2 else "",
        "Saldo Awal": row[3] if len(row) > 3 else "",
        "Total Pengeluaran": row[4] if len(row) > 4 else "",
        "Saldo Akhir": row[5] if len(row) > 5 else "",
    }


def _find_matching_rows(
    values: list[list[str]],
    date_str: str | None,
    description: str | None,
) -> list[tuple[int, list[str]]]:
    """Cari baris yang cocok dengan tanggal dan/atau keterangan.

    Mengembalikan list tuple (sheet_row_index, row_values).
    sheet_row_index adalah nomor baris di Google Sheet (header di baris 1).
    """
    matches: list[tuple[int, list[str]]] = []

    normalized_date = _parse_date(date_str) if date_str else ""
    normalized_desc = description.lower().strip() if description else ""

    for idx, row in enumerate(values, start=2):  # data mulai baris 2
        if not row:
            continue

        raw_date = row[0] if len(row) > 0 else ""
        raw_desc = row[1] if len(row) > 1 else ""

        date_match = False
        if normalized_date:
            parsed_row_date = _parse_date(raw_date)
            date_match = parsed_row_date == normalized_date
        else:
            date_match = True  # tidak difilter tanggal

        desc_match = False
        if normalized_desc:
            desc_match = normalized_desc in raw_desc.lower()
        else:
            desc_match = True  # tidak difilter keterangan

        if date_match and desc_match:
            matches.append((idx, row))

    return matches


def get_all_expenses() -> dict[str, Any]:
    """Baca semua data pengeluaran dari sheet."""
    try:
        values = _get_sheet_values()
        if not values:
            return {"status": "success", "data": [], "message": "Sheet masih kosong"}

        return {
            "status": "success",
            "data": [_row_to_dict(row) for row in values],
            "message": f"Berhasil membaca {len(values)} baris data",
        }
    except Exception as exc:
        return _format_error(exc, "Gagal membaca semua pengeluaran")


def get_recent_expenses(limit: int = 10) -> dict[str, Any]:
    """Ambil N baris pengeluaran terbaru (baris paling bawah)."""
    try:
        values = _get_sheet_values()
        if not values:
            return {"status": "success", "data": [], "message": "Sheet masih kosong"}

        recent = values[-limit:]
        return {
            "status": "success",
            "data": [_row_to_dict(row) for row in recent],
            "message": f"Menampilkan {len(recent)} pengeluaran terbaru",
        }
    except Exception as exc:
        return _format_error(exc, "Gagal membaca pengeluaran terbaru")


def get_expenses_by_date(date_str: str) -> dict[str, Any]:
    """Cari pengeluaran berdasarkan tanggal."""
    try:
        values = _get_sheet_values()
        if not values:
            return {"status": "success", "data": [], "message": "Sheet masih kosong"}

        normalized_target = _parse_date(date_str)
        results = []

        logger.info("Target tanggal: raw=%r parsed=%r", date_str, normalized_target)

        for row in values:
            if not row:
                continue

            raw_date = row[0] if len(row) > 0 else ""
            parsed_date = _parse_date(raw_date)

            logger.info(
                "DEBUG TGL: raw=%r | parsed=%r | target=%r",
                raw_date,
                parsed_date,
                normalized_target,
            )

            if parsed_date == normalized_target:
                results.append(_row_to_dict(row))

        logger.info(
            "Hasil pencarian tanggal %r: %s data",
            normalized_target,
            len(results),
        )

        total_pengeluaran = sum(
            _parse_amount(item.get("Pengeluaran", ""))
            for item in results
        )

        return {
            "status": "success",
            "data": results,
            "summary": {
                "tanggal": normalized_target,
                "jumlah_data": len(results),
                "total_pengeluaran": total_pengeluaran,
            },
            "message": f"Ditemukan {len(results)} pengeluaran pada tanggal {date_str}",
        }
    except Exception as exc:
        return _format_error(exc, "Gagal mencari pengeluaran by date")


def get_expenses_today() -> dict[str, Any]:
    """Cari pengeluaran untuk tanggal hari ini."""
    today = datetime.now().strftime("%Y-%m-%d")
    return get_expenses_by_date(today)


def get_expenses_by_day_month(day: int, month: int) -> dict[str, Any]:
    """Cari pengeluaran berdasarkan hari dan bulan, menggunakan tahun saat ini.

    Berguna ketika user menyebut tanggal tanpa tahun, misalnya '16 Juni'.
    """
    year = datetime.now().year
    date_str = f"{day:02d}/{month:02d}/{year}"
    return get_expenses_by_date(date_str)


def get_current_date() -> dict[str, Any]:
    """Mengembalikan tanggal dan hari sekarang berdasarkan server."""
    try:
        now = datetime.now()
        return {
            "status": "success",
            "data": {
                "date": now.strftime("%Y-%m-%d"),
                "day": HARI[now.weekday()],
                "time": now.strftime("%H:%M:%S"),
                "timezone": "server local time",
            },
            "message": "Tanggal sekarang",
        }
    except Exception as exc:
        return _format_error(exc, "Gagal mendapatkan tanggal sekarang")


def get_expense_summary() -> dict[str, Any]:
    """Ambil ringkasan keuangan: tanggal terakhir dari baris terakhir,
    total pengeluaran dari cell E2, dan saldo akhir dari cell F2.
    """
    try:
        values = _get_sheet_values()
        if not values:
            return {"status": "success", "data": {}, "message": "Sheet masih kosong"}

        last_row = values[-1]
        summary = _row_to_dict(last_row)

        total_result = get_total_pengeluaran()
        saldo_result = get_saldo_akhir()

        total_pengeluaran = (
            total_result.get("total_pengeluaran", "")
            if total_result.get("status") == "success"
            else ""
        )
        saldo_akhir = (
            saldo_result.get("saldo_akhir", "")
            if saldo_result.get("status") == "success"
            else ""
        )

        return {
            "status": "success",
            "data": {
                "total_pengeluaran": total_pengeluaran,
                "saldo_akhir": saldo_akhir,
                "tanggal_terakhir": summary.get("Tgl", ""),
            },
            "message": "Ringkasan keuangan dari data terakhir",
        }
    except Exception as exc:
        return _format_error(exc, "Gagal membaca ringkasan")


def _parse_expense_input(text: str) -> dict[str, Any]:
    """Parse input pengeluaran dari user menjadi tanggal, keterangan, dan nominal.

    Format yang didukung:
    - "makan siang 50000"
    - "16/06/2026 makan siang 50000"
    - "16 Juni Makan Es Krim 20rb"
    """
    words = text.strip().split()
    if len(words) < 2:
        return {"error": "Input harus memiliki keterangan dan nominal."}

    amount = _parse_amount(words[-1])
    if amount <= 0:
        return {"error": "Nominal tidak valid. Pastikan ada nominal di akhir pesan, misalnya 50000 atau 10rb."}

    # Coba parse tanggal di awal kalimat, dari kandidat terpanjang ke terpendek.
    max_date_words = min(4, len(words) - 2)
    date_str = ""
    date_end_index = 0
    for i in range(max_date_words, 0, -1):
        candidate = " ".join(words[:i])
        parsed = _parse_date(candidate)
        if re.match(r"^\d{4}-\d{2}-\d{2}$", parsed):
            date_str = parsed
            date_end_index = i
            break

    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    description = " ".join(words[date_end_index:-1]).strip()
    if not description:
        return {"error": "Keterangan tidak boleh kosong."}

    return {
        "date": date_str,
        "description": description,
        "amount": amount,
    }


def _parse_delete_input(text: str) -> dict[str, Any]:
    """Parse input penghapusan dari user menjadi tanggal, keterangan, dan nominal opsional.

    Format yang didukung:
    - "hapus es krim 5k"
    - "hapus 16 juni es krim 5rb"
    - "batalkan 16/06/2026 makan siang"

    Nominal diakhir tidak wajib; jika ada, akan diabaikan untuk pencarian.
    """
    words = text.strip().split()
    if not words:
        return {"error": "Input tidak boleh kosong."}

    # Abaikan kata kunci perintah di awal kalimat.
    command_words = {"hapus", "delete", "batalkan", "cancel", "hilangkan"}
    while words and words[0].lower().strip(",.!?") in command_words:
        words.pop(0)

    if not words:
        return {"error": "Berikan tanggal atau keterangan pengeluaran yang ingin dihapus."}

    # Nominal di akhir bersifat opsional untuk penghapusan.
    end_index = len(words)
    amount = _parse_amount(words[-1])
    if amount > 0:
        end_index = len(words) - 1

    # Coba parse tanggal di awal kalimat, dari kandidat terpanjang ke terpendek.
    max_date_words = min(4, end_index - 1)
    date_str = ""
    date_end_index = 0
    for i in range(max_date_words, 0, -1):
        candidate = " ".join(words[:i])
        parsed = _parse_date(candidate)
        if re.match(r"^\d{4}-\d{2}-\d{2}$", parsed):
            date_str = parsed
            date_end_index = i
            break

    description = " ".join(words[date_end_index:end_index]).strip()

    if not date_str and not description:
        return {"error": "Berikan tanggal atau keterangan pengeluaran yang ingin dihapus."}

    return {
        "date": date_str,
        "description": description,
        "amount": amount,
    }


def insert_expense(text: str) -> dict[str, Any]:
    """Catat pengeluaran baru ke Google Sheet (hanya kolom A, B, C)."""
    try:
        parsed = _parse_expense_input(text)
        if "error" in parsed:
            return {"status": "error", "message": parsed["error"]}

        worksheet = _get_worksheet()

        amount = parsed["amount"]
        description = parsed["description"]

        date_display = datetime.strptime(
            parsed["date"], "%Y-%m-%d"
        ).strftime("%d/%m/%Y")

        row = [date_display, description, amount]

        worksheet.append_row(row, value_input_option="USER_ENTERED")

        formatted_amount = f"Rp {amount:,}".replace(",", ".")
        return {
            "status": "success",
            "message": f"Berhasil mencatat pengeluaran '{description}' sebesar {formatted_amount} pada {date_display}.",
            "data": {
                "Tgl": date_display,
                "Keterangan": description,
                "Pengeluaran": amount,
            },
        }

    except Exception as exc:
        return _format_error(exc, "Gagal mencatat pengeluaran")


def delete_last_expense() -> dict[str, Any]:
    """Hapus baris pengeluaran paling akhir di Google Sheet."""
    try:
        worksheet = _get_worksheet()
        values = _get_sheet_values()

        if not values:
            return {
                "status": "error",
                "message": "Tidak ada pengeluaran yang bisa dihapus. Sheet masih kosong.",
            }

        last_row_index = len(values) + 1  # header di baris 1
        last_row = values[-1]
        worksheet.delete_rows(last_row_index)

        deleted = _row_to_dict(last_row)
        return {
            "status": "success",
            "message": (
                f"Berhasil menghapus pengeluaran terakhir: "
                f"{deleted.get('Tgl', '')} - {deleted.get('Keterangan', '')} "
                f"({deleted.get('Pengeluaran', '')})"
            ),
            "data": deleted,
        }
    except Exception as exc:
        return _format_error(exc, "Gagal menghapus pengeluaran terakhir")


def delete_expense(text: str) -> dict[str, Any]:
    """Hapus pengeluaran berdasarkan seluruh pesan user.

    Pesan akan di-parse untuk mengekstrak tanggal, keterangan, dan nominal opsional.
    Hanya menghapus jika ditemukan tepat 1 baris yang cocok.
    Jika 0 atau >1 baris cocok, kembalikan error tanpa menghapus.
    """
    try:
        parsed = _parse_delete_input(text)
        if "error" in parsed:
            return {"status": "error", "message": parsed["error"]}

        worksheet = _get_worksheet()
        values = _get_sheet_values()

        if not values:
            return {
                "status": "error",
                "message": "Tidak ada pengeluaran yang bisa dihapus. Sheet masih kosong.",
            }

        matches = _find_matching_rows(values, parsed.get("date"), parsed.get("description"))

        if len(matches) == 0:
            return {
                "status": "error",
                "message": "Tidak ditemukan pengeluaran yang cocok dengan kriteria tersebut.",
            }

        if len(matches) > 1:
            return {
                "status": "error",
                "message": (
                    f"Ditemukan {len(matches)} pengeluaran yang cocok. "
                    "Mohon perjelas tanggal atau keterangannya agar saya bisa menghapus yang tepat."
                ),
            }

        sheet_row_index, row = matches[0]
        worksheet.delete_rows(sheet_row_index)

        deleted = _row_to_dict(row)
        return {
            "status": "success",
            "message": (
                f"Berhasil menghapus pengeluaran: "
                f"{deleted.get('Tgl', '')} - {deleted.get('Keterangan', '')} "
                f"({deleted.get('Pengeluaran', '')})"
            ),
            "data": deleted,
        }
    except Exception as exc:
        return _format_error(exc, "Gagal menghapus pengeluaran")


# -----------------------------------------------------------------------------
# FUNCTION DECLARATIONS untuk Gemini (mengikuti pola tools-contoh.py)
# -----------------------------------------------------------------------------

TOOL_DECLARATIONS = [
    {
        "name": "insert_expense",
        "description": (
            "Catat pengeluaran baru ke Google Sheet. "
            "WAJIB dipanggil ketika user ingin menambahkan pengeluaran, misalnya "
            "'makan siang 50rb', 'bayar parkir 10k', '16 Juni Makan Es Krim 20rb', "
            "atau '16/06/2026 beli pulsa 50.000'. "
            "Jangan pernah memanggil tool ini jika user tidak menyebutkan keterangan atau nominal."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Seluruh pesan user yang berisi keterangan dan nominal pengeluaran, contoh: 'makan siang 50rb'",
                }
            },
            "required": ["text"],
        },
    },
    {
        "name": "delete_last_expense",
        "description": (
            "Hapus pengeluaran paling akhir yang tercatat di Google Sheet. "
            "WAJIB dipanggil ketika user ingin membatalkan atau menghapus input terakhir, "
            "misalnya 'hapus pengeluaran terakhir', 'batalkan input terakhir', 'salah input, hapus yang terakhir'. "
            "Jangan panggil tool ini jika user ingin menghapus data lama atau berdasarkan keterangan."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "delete_expense",
        "description": (
            "Hapus pengeluaran tertentu di Google Sheet berdasarkan seluruh pesan user. "
            "WAJIB dipanggil ketika user ingin menghapus pengeluaran spesifik, "
            "misalnya 'hapus pengeluaran makan siang tadi', 'hapus data tanggal 16/06/2026', "
            "'hapus 16 juni es krim 5rb', atau 'hapus es krim 5k'. "
            "Kirim seluruh pesan user sebagai parameter text; tool akan mengekstrak tanggal, "
            "keterangan, dan nominal sendiri. Nominal di akhir tidak wajib. "
            "Tool ini hanya akan menghapus jika ditemukan tepat 1 data yang cocok; "
            "jika tidak ditemukan atau ada banyak yang cocok, bot akan meminta klarifikasi."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Seluruh pesan user yang ingin menghapus pengeluaran, contoh: 'hapus 16 juni es krim 5rb'",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_all_expenses",
        "description": (
            "Baca seluruh data pengeluaran dari Google Sheet. "
            "Gunakan jika user ingin melihat semua riwayat pengeluaran."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_recent_expenses",
        "description": (
            "Ambil N pengeluaran terbaru dari Google Sheet. "
            "Gunakan jika user tanya 'pengeluaran terbaru', 'beberapa hari terakhir', atau '10 pengeluaran terakhir'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Jumlah baris terbaru yang ingin ditampilkan, default 10",
                }
            },
        },
    },
    {
        "name": "get_expenses_by_date",
        "description": (
            "Cari pengeluaran pada tanggal tertentu di Google Sheet. "
            "WAJIB dipanggil setiap kali user menanyakan pengeluaran di tanggal spesifik, "
            "misalnya 'pengeluaran tanggal 16 Juni', '16/06/2026', atau 'berapa pengeluaran kemarin'. "
            "Jangan pernah mengarang jawaban tanpa membaca data sheet terlebih dahulu."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "Tanggal yang dicari dalam format 'YYYY-MM-DD', 'DD/MM/YYYY', atau '16 Juni 2026'",
                }
            },
            "required": ["date_str"],
        },
    },
    {
        "name": "get_expenses_today",
        "description": (
            "Cari pengeluaran untuk hari ini (tanggal saat ini). "
            "Gunakan jika user bertanya 'pengeluaran hari ini', 'hari ini pengeluaran apa', "
            "atau pertanyaan serupa tentang pengeluaran hari ini."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_expenses_by_day_month",
        "description": (
            "Cari pengeluaran berdasarkan hari dan bulan saja, menggunakan tahun saat ini. "
            "WAJIB dipanggil jika user menyebut tanggal tanpa tahun, misalnya "
            "'pengeluaran tanggal 16 Juni', 'tanggal 16/06', atau '16 Juni'. "
            "Jangan pernah menebak tahun sendiri."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "integer",
                    "description": "Tanggal (1-31), contoh: 16",
                },
                "month": {
                    "type": "integer",
                    "description": "Bulan (1-12), contoh: 6 untuk Juni",
                },
            },
            "required": ["day", "month"],
        },
    },
    {
        "name": "get_total_pengeluaran",
        "description": (
            "Ambil total pengeluaran dari cell E2 Google Sheet. "
            "WAJIB dipanggil ketika user bertanya 'total pengeluaran berapa', "
            "'berapa total pengeluaran ku', atau pertanyaan serupa. "
            "Jangan pernah mengarang jawaban tanpa membaca data sheet terlebih dahulu."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_saldo_akhir",
        "description": (
            "Ambil saldo akhir dari cell F2 Google Sheet. "
            "WAJIB dipanggil ketika user bertanya 'saldo akhir berapa', 'sisa saldo ku berapa', "
            "'berapa saldo akhir ku', atau pertanyaan serupa. "
            "Jangan pernah mengarang jawaban tanpa membaca data sheet terlebih dahulu."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_expense_summary",
        "description": (
            "Ambil ringkasan keuangan: total pengeluaran dari cell E2, "
            "saldo akhir dari cell F2, dan tanggal terakhir dari baris terakhir. "
            "Gunakan jika user tanya 'ringkasan keuangan' atau ingin melihat total dan saldo sekaligus."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_current_date",
        "description": (
            "Get the current date and day based on the server time. "
            "Use this when the user asks about today's date, 'tanggal berapa hari ini', "
            "'hari ini tanggal berapa', or any question about current date/time."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]

TOOL_FUNCTIONS = {
    "insert_expense": insert_expense,
    "delete_last_expense": delete_last_expense,
    "delete_expense": delete_expense,
    "get_all_expenses": get_all_expenses,
    "get_recent_expenses": get_recent_expenses,
    "get_expenses_by_date": get_expenses_by_date,
    "get_expenses_by_day_month": get_expenses_by_day_month,
    "get_expenses_today": get_expenses_today,
    "get_total_pengeluaran": get_total_pengeluaran,
    "get_saldo_akhir": get_saldo_akhir,
    "get_expense_summary": get_expense_summary,
    "get_current_date": get_current_date,
}
