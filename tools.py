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


def _get_sheet_values() -> list[list[str]]:
    """Membaca seluruh data sheet mulai dari A2."""
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
        worksheet = spreadsheet.worksheet(config.SHEET_NAME)
    except WorksheetNotFound:
        raise WorksheetNotFound(f"Sheet '{config.SHEET_NAME}' tidak ditemukan")

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
    if not value:
        return 0

    value = str(value)
    value = value.replace("Rp", "")
    value = value.replace(".", "")
    value = value.replace(",", "")
    value = value.strip()

    try:
        return int(value)
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


def get_expense_summary() -> dict[str, Any]:
    """Ambil ringkasan dari baris terakhir: total pengeluaran dan saldo akhir."""
    try:
        values = _get_sheet_values()
        if not values:
            return {"status": "success", "data": {}, "message": "Sheet masih kosong"}

        last_row = values[-1]
        summary = _row_to_dict(last_row)

        return {
            "status": "success",
            "data": {
                "total_pengeluaran": summary.get("Total Pengeluaran", ""),
                "saldo_akhir": summary.get("Saldo Akhir", ""),
                "tanggal_terakhir": summary.get("Tgl", ""),
            },
            "message": "Ringkasan keuangan dari data terakhir",
        }
    except Exception as exc:
        return _format_error(exc, "Gagal membaca ringkasan")


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


# -----------------------------------------------------------------------------
# FUNCTION DECLARATIONS untuk Gemini (mengikuti pola tools-contoh.py)
# -----------------------------------------------------------------------------

TOOL_DECLARATIONS = [
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
        "name": "get_expense_summary",
        "description": (
            "Ambil ringkasan keuangan: total pengeluaran dan saldo akhir dari baris terakhir. "
            "Gunakan jika user tanya 'total pengeluaran berapa', 'sisa saldo', atau 'saldo akhir'."
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
    "get_all_expenses": get_all_expenses,
    "get_recent_expenses": get_recent_expenses,
    "get_expenses_by_date": get_expenses_by_date,
    "get_expenses_by_day_month": get_expenses_by_day_month,
    "get_expenses_today": get_expenses_today,
    "get_expense_summary": get_expense_summary,
    "get_current_date": get_current_date,
}
