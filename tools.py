import logging
from datetime import datetime
from typing import Optional
import os
import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

BULAN_ID = {
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}


def _get_sheet():
    """Ambil worksheet dari Google Sheet yang dikonfigurasi.

    Jika GOOGLE_SHEET_NAME diatur, gunakan worksheet dengan nama tersebut.
    Jika tidak, gunakan worksheet pertama (sheet1).
    """
    credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "/app/credentials.json")

    creds = Credentials.from_service_account_file(
        credentials_path,
        scopes=SCOPES,
    )

    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)
    if config.GOOGLE_SHEET_NAME:
        return spreadsheet.worksheet(config.GOOGLE_SHEET_NAME)
    return spreadsheet.sheet1


def _find_column(headers: list[str], *candidates: str) -> str | None:
    """Cari nama kolom secara case-insensitive dan tolerant whitespace."""
    normalized = {h.strip().lower(): h for h in headers}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in normalized:
            return normalized[key]
    return None


def _parse_date_flexible(value: str) -> str:
    """Coba parse tanggal ke YYYY-MM-DD dari beberapa format umum Indonesia."""
    if not value:
        return ""

    s = str(value).strip()

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue

    # Coba format "29 Juni 2026"
    parts = s.split()
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = BULAN_ID.get(parts[1].lower())
            year = int(parts[2])
            if month:
                return datetime(year, month, day).date().isoformat()
        except (ValueError, TypeError):
            pass

    return s


def _normalize_pengeluaran(value) -> float:
    """Konversi nilai pengeluaran ke float, toleran terhadap prefix mata uang dan pemisah ribuan."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    s = str(value).strip()
    # Hapus semua karakter kecuali digit, titik, dan koma.
    cleaned = "".join(ch for ch in s if ch.isdigit() or ch in ",.")
    if not cleaned:
        logger.warning("Gagal parse nilai pengeluaran: %r", value)
        return 0.0

    # Asumsi format Indonesia: titik = pemisah ribuan, koma = desimal.
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        logger.warning("Gagal parse nilai pengeluaran: %r", value)
        return 0.0


def get_expenses(filter_date: Optional[str] = None, keyword: Optional[str] = None) -> dict:
    """Baca data pengeluaran dari Google Sheets.

    Spreadsheet diharapkan memiliki kolom: Tgl, Keterangan, Pengeluaran.
    Parameter opsional:
      - filter_date: filter tanggal (YYYY-MM-DD atau format umum Indonesia).
      - keyword: filter case-insensitive di kolom Keterangan.
    """
    if not config.GOOGLE_SHEET_ID:
        return {"error": "GOOGLE_SHEET_ID belum diatur di file .env"}

    try:
        sheet = _get_sheet()
        records = sheet.get_all_records()
    except Exception as exc:
        logger.exception("Gagal membaca Google Sheets")
        return {"error": f"Gagal membaca spreadsheet: {exc}"}

    if not records:
        return {"count": 0, "items": [], "total": 0.0}

    headers = list(records[0].keys())
    logger.debug("Header spreadsheet: %s", headers)

    col_tgl = _find_column(headers, "Tgl", "Tanggal", "Date", "Tgl.")
    col_keterangan = _find_column(headers, "Keterangan", "Ket", "Deskripsi", "Detail")
    col_pengeluaran = _find_column(headers, "Pengeluaran", "Jumlah", "Nominal", "Harga", "Total", "Biaya")

    if not col_pengeluaran:
        logger.error("Kolom Pengeluaran tidak ditemukan. Header: %s", headers)
        return {"error": f"Kolom Pengeluaran tidak ditemukan. Header terbaca: {headers}"}

    logger.info("Mapping kolom: Tgl=%s, Keterangan=%s, Pengeluaran=%s", col_tgl, col_keterangan, col_pengeluaran)

    results = []
    total = 0.0
    keyword_lower = keyword.lower().strip() if keyword else None
    normalized_filter = _parse_date_flexible(filter_date) if filter_date else None

    for row in records:
        tgl = str(row.get(col_tgl, "")).strip() if col_tgl else ""
        keterangan = str(row.get(col_keterangan, "")).strip() if col_keterangan else ""
        pengeluaran = _normalize_pengeluaran(row.get(col_pengeluaran))

        if normalized_filter and _parse_date_flexible(tgl) != normalized_filter:
            continue

        if keyword_lower and keyword_lower not in keterangan.lower():
            continue

        results.append({
            "Tgl": tgl,
            "Keterangan": keterangan,
            "Pengeluaran": pengeluaran,
        })
        total += pengeluaran

    return {
        "count": len(results),
        "items": results,
        "total": total,
    }


def add_expense(keterangan: str, jumlah: float, tanggal: Optional[str] = None) -> dict:
    """Tambahkan satu baris pengeluaran ke Google Sheets.

    Args:
        keterangan: nama atau keterangan pengeluaran.
        jumlah: nominal pengeluaran dalam bentuk angka (contoh: 8000).
        tanggal: tanggal dalam format YYYY-MM-DD. Jika kosong, gunakan tanggal hari ini.
    """
    if not config.GOOGLE_SHEET_ID:
        return {"error": "GOOGLE_SHEET_ID belum diatur di file .env"}

    if not keterangan or not str(keterangan).strip():
        return {"error": "Keterangan pengeluaran tidak boleh kosong"}

    try:
        jumlah = float(jumlah)
        if jumlah <= 0:
            return {"error": "Jumlah pengeluaran harus lebih besar dari 0"}
    except (ValueError, TypeError):
        return {"error": f"Jumlah pengeluaran tidak valid: {jumlah!r}"}

    if not tanggal:
        tanggal = datetime.now().date().isoformat()

    try:
        sheet = _get_sheet()
        headers = sheet.row_values(1)
    except Exception as exc:
        logger.exception("Gagal membuka Google Sheets")
        return {"error": f"Gagal membuka spreadsheet: {exc}"}

    col_tgl = _find_column(headers, "Tgl", "Tanggal", "Date", "Tgl.")
    col_keterangan = _find_column(headers, "Keterangan", "Ket", "Deskripsi", "Detail")
    col_pengeluaran = _find_column(headers, "Pengeluaran", "Jumlah", "Nominal", "Harga", "Total", "Biaya")

    if not all([col_tgl, col_keterangan, col_pengeluaran]):
        logger.error("Kolom tidak lengkap. Header: %s", headers)
        return {"error": f"Kolom Tgl/Keterangan/Pengeluaran tidak ditemukan. Header: {headers}"}

    try:
        # Pastikan urutan kolom sesuai header
        row = ["", "", ""]
        for idx, header in enumerate(headers):
            if header.strip().lower() == col_tgl.strip().lower():
                row[idx] = tanggal
            elif header.strip().lower() == col_keterangan.strip().lower():
                row[idx] = str(keterangan).strip()
            elif header.strip().lower() == col_pengeluaran.strip().lower():
                row[idx] = jumlah
        sheet.append_row(row, value_input_option="USER_ENTERED")
    except Exception as exc:
        logger.exception("Gagal menulis ke Google Sheets")
        return {"error": f"Gagal menambahkan pengeluaran: {exc}"}

    return {
        "success": True,
        "message": f"Pengeluaran '{keterangan}' sebesar Rp{jumlah:,.0f} pada {tanggal} berhasil dicatat.",
        "data": {
            "Tgl": tanggal,
            "Keterangan": keterangan,
            "Pengeluaran": jumlah,
        },
    }


def get_balance() -> dict:
    """Baca nilai saldo akhir dari cell F2 di Google Sheets."""
    if not config.GOOGLE_SHEET_ID:
        return {"error": "GOOGLE_SHEET_ID belum diatur di file .env"}

    try:
        sheet = _get_sheet()
        value = sheet.acell("F2").value
    except Exception as exc:
        logger.exception("Gagal membaca saldo akhir dari Google Sheets")
        return {"error": f"Gagal membaca saldo akhir: {exc}"}

    return {
        "saldo_akhir": value,
        "cell": "F2",
    }


def get_total_expenses() -> dict:
    """Baca nilai total pengeluaran dari cell E2 di Google Sheets."""
    if not config.GOOGLE_SHEET_ID:
        return {"error": "GOOGLE_SHEET_ID belum diatur di file .env"}

    try:
        sheet = _get_sheet()
        value = sheet.acell("E2").value
    except Exception as exc:
        logger.exception("Gagal membaca total pengeluaran dari Google Sheets")
        return {"error": f"Gagal membaca total pengeluaran: {exc}"}

    return {
        "total_pengeluaran": value,
        "cell": "E2",
    }


def get_expense_summary() -> dict:
    """Hitung total pengeluaran per tanggal dari Google Sheets.

    Mengembalikan daftar tanggal dengan total pengeluaran, diurutkan dari
    total tertinggi ke terendah. Berguna untuk menjawab pertanyaan seperti
    "pengeluaran paling banyak di tanggal berapa?" atau "paling sedikit".
    """
    if not config.GOOGLE_SHEET_ID:
        return {"error": "GOOGLE_SHEET_ID belum diatur di file .env"}

    try:
        sheet = _get_sheet()
        records = sheet.get_all_records()
    except Exception as exc:
        logger.exception("Gagal membaca Google Sheets")
        return {"error": f"Gagal membaca spreadsheet: {exc}"}

    if not records:
        return {"count": 0, "items": []}

    headers = list(records[0].keys())

    col_tgl = _find_column(headers, "Tgl", "Tanggal", "Date", "Tgl.")
    col_pengeluaran = _find_column(headers, "Pengeluaran", "Jumlah", "Nominal", "Harga", "Total", "Biaya")

    if not col_pengeluaran:
        logger.error("Kolom Pengeluaran tidak ditemukan. Header: %s", headers)
        return {"error": f"Kolom Pengeluaran tidak ditemukan. Header terbaca: {headers}"}

    totals: dict[str, float] = {}
    for row in records:
        tgl_raw = str(row.get(col_tgl, "")).strip() if col_tgl else ""
        tgl = _parse_date_flexible(tgl_raw) or tgl_raw
        pengeluaran = _normalize_pengeluaran(row.get(col_pengeluaran))
        totals[tgl] = totals.get(tgl, 0.0) + pengeluaran

    items = sorted(
        [{"Tgl": tgl, "Total": total} for tgl, total in totals.items()],
        key=lambda x: x["Total"],
        reverse=True,
    )

    return {
        "count": len(items),
        "items": items,
    }


def delete_expense(filter_date: Optional[str] = None, keyword: Optional[str] = None,
                   jumlah: Optional[float] = None) -> dict:
    """Hapus satu baris pengeluaran dari Google Sheets berdasarkan kriteria.

    Hanya menghapus jika ditemukan tepat satu baris yang cocok. Jika tidak ada
    atau ada lebih dari satu cocokan, kembalikan informasi agar user bisa
    memberikan kriteria lebih spesifik.

    Args:
        filter_date: tanggal dalam format YYYY-MM-DD atau format umum Indonesia.
        keyword: kata kunci yang harus ada di kolom Keterangan (case-insensitive).
        jumlah: nominal pengeluaran dalam angka.
    """
    if not config.GOOGLE_SHEET_ID:
        return {"error": "GOOGLE_SHEET_ID belum diatur di file .env"}

    # Normalisasi input kosong menjadi None
    filter_date = filter_date.strip() if filter_date else None
    keyword = keyword.strip().lower() if keyword else None
    jumlah = _normalize_pengeluaran(jumlah) if jumlah is not None else None

    if not filter_date and not keyword and jumlah is None:
        return {"error": "Berikan setidaknya salah satu kriteria: tanggal, keterangan, atau jumlah."}

    try:
        sheet = _get_sheet()
        all_values = sheet.get_all_values()
    except Exception as exc:
        logger.exception("Gagal membaca Google Sheets")
        return {"error": f"Gagal membaca spreadsheet: {exc}"}

    if len(all_values) < 2:
        return {"error": "Spreadsheet kosong, tidak ada data untuk dihapus."}

    headers = all_values[0]

    col_tgl = _find_column(headers, "Tgl", "Tanggal", "Date", "Tgl.")
    col_keterangan = _find_column(headers, "Keterangan", "Ket", "Deskripsi", "Detail")
    col_pengeluaran = _find_column(headers, "Pengeluaran", "Jumlah", "Nominal", "Harga", "Total", "Biaya")

    if not all([col_tgl, col_keterangan, col_pengeluaran]):
        logger.error("Kolom tidak lengkap. Header: %s", headers)
        return {"error": f"Kolom Tgl/Keterangan/Pengeluaran tidak ditemukan. Header: {headers}"}

    idx_tgl = headers.index(col_tgl)
    idx_keterangan = headers.index(col_keterangan)
    idx_pengeluaran = headers.index(col_pengeluaran)

    normalized_filter = _parse_date_flexible(filter_date) if filter_date else None

    matches = []
    for row_idx, row in enumerate(all_values[1:], start=2):
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))

        tgl = str(row[idx_tgl]).strip() if idx_tgl < len(row) else ""
        keterangan = str(row[idx_keterangan]).strip() if idx_keterangan < len(row) else ""
        pengeluaran_raw = row[idx_pengeluaran] if idx_pengeluaran < len(row) else ""
        pengeluaran = _normalize_pengeluaran(pengeluaran_raw)

        if normalized_filter and _parse_date_flexible(tgl) != normalized_filter:
            continue

        if keyword and keyword not in keterangan.lower():
            continue

        if jumlah is not None and abs(pengeluaran - jumlah) > 1e-9:
            continue

        matches.append({
            "row": row_idx,
            "Tgl": tgl,
            "Keterangan": keterangan,
            "Pengeluaran": pengeluaran,
        })

    if not matches:
        return {"error": "Tidak ditemukan data pengeluaran yang cocok dengan kriteria tersebut."}

    if len(matches) > 1:
        return {
            "error": "Ditemukan beberapa data yang cocok. Berikan kriteria lebih spesifik.",
            "matches": matches,
        }

    match = matches[0]
    try:
        sheet.delete_rows(match["row"])
    except Exception as exc:
        logger.exception("Gagal menghapus baris di Google Sheets")
        return {"error": f"Gagal menghapus data: {exc}"}

    return {
        "success": True,
        "message": (
            f"Pengeluaran '{match['Keterangan']}' sebesar Rp{match['Pengeluaran']:,.0f} "
            f"pada {match['Tgl']} berhasil dihapus."
        ),
        "data": {
            "Tgl": match["Tgl"],
            "Keterangan": match["Keterangan"],
            "Pengeluaran": match["Pengeluaran"],
        },
    }


TOOL_DECLARATIONS = [
    {
        "name": "add_expense",
        "description": (
            "Tambahkan pengeluaran baru ke Google Sheets. "
            "Gunakan saat user menyebutkan pembelian atau pengeluaran, contohnya: "
            "'es krim 8k', 'bensin 50k', 'makan siang 25 ribu 30 juni'. "
            "Konversi singkatan seperti 8k menjadi 8000 sebelum memanggil tool. "
            "Jika user menyebut tanggal, konversi ke format YYYY-MM-DD; "
            "jika tidak, gunakan tanggal hari ini dari konteks waktu."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keterangan": {
                    "type": "string",
                    "description": "Nama atau keterangan pengeluaran.",
                },
                "jumlah": {
                    "type": "number",
                    "description": "Nominal pengeluaran dalam angka, contoh 8000.",
                },
                "tanggal": {
                    "type": "string",
                    "description": "Tanggal dalam format YYYY-MM-DD. Opsional, default hari ini.",
                },
            },
            "required": ["keterangan", "jumlah"],
        },
    },
    {
        "name": "get_expenses",
        "description": (
            "Gunakan tool ini setiap kali user bertanya tentang daftar/detail pengeluaran "
            "atau menghitung total pengeluaran untuk periode/kategori tertentu dari baris-baris data, "
            "misalnya: pengeluaran hari ini, daftar pengeluaran, "
            "atau pengeluaran untuk kategori/tanggal tertentu. "
            "Spreadsheet memiliki kolom: Tgl, Keterangan, Pengeluaran. "
            "Parameter filter_date (YYYY-MM-DD) untuk menyaring tanggal. "
            "Parameter keyword untuk menyaring kolom Keterangan secara case-insensitive. "
            "Jangan menebak data; selalu panggil tool ini terlebih dahulu."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filter_date": {
                    "type": "string",
                    "description": "Filter tanggal dalam format YYYY-MM-DD. Opsional.",
                },
                "keyword": {
                    "type": "string",
                    "description": "Filter kata kunci di kolom Keterangan (case-insensitive). Opsional.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_balance",
        "description": (
            "Gunakan tool ini ketika user bertanya tentang saldo akhir, sisa saldo, "
            "atau saldo terakhir. Membaca nilai dari cell F2 di spreadsheet. "
            "Contoh: 'saldo akhir berapa?', 'sisa saldo saya berapa?', 'saldo terakhir'. "
            "Jangan menebak; selalu panggil tool ini untuk pertanyaan tentang saldo."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_total_expenses",
        "description": (
            "Gunakan tool ini ketika user bertanya tentang total pengeluaran secara keseluruhan. "
            "Membaca nilai dari cell E2 di spreadsheet. "
            "Contoh: 'total pengeluaran berapa?', 'total pengeluaran saya berapa?'. "
            "Jangan menebak; selalu panggil tool ini untuk pertanyaan tentang total pengeluaran."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_expense_summary",
        "description": (
            "Gunakan tool ini ketika user bertanya tentang total pengeluaran per tanggal, "
            "pengeluaran paling banyak di tanggal berapa, atau pengeluaran paling sedikit. "
            "Tool ini menghitung total pengeluaran per tanggal dari baris-baris spreadsheet. "
            "Hasil diurutkan dari total tertinggi ke terendah. "
            "Contoh: 'pengeluaran paling banyak di tanggal berapa?', "
            "'tanggal paling sedikit pengeluarannya?', 'total pengeluaran per tanggal'. "
            "Jangan menebak; selalu panggil tool ini untuk pertanyaan agregat per tanggal."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "delete_expense",
        "description": (
            "Gunakan tool ini saat user ingin MENGHAPUS data pengeluaran. "
            "Contoh: 'hapus es krim 8k', 'hapus pengeluaran bensin', "
            "'hapus data tanggal 2026-06-29', 'hapus makan siang 25 ribu'. "
            "Tool ini akan menghapus baris jika hanya ada satu data yang cocok. "
            "Jika ada beberapa data cocok, tool akan mengembalikan daftarnya; "
            "mintalah user memberikan kriteria lebih spesifik (misalnya tambahkan tanggal atau jumlah). "
            "Konversi singkatan seperti 8k → 8000 sebelum memanggil tool. "
            "Jika user menyebut tanggal, konversi ke format YYYY-MM-DD."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filter_date": {
                    "type": "string",
                    "description": "Tanggal pengeluaran dalam format YYYY-MM-DD. Opsional.",
                },
                "keyword": {
                    "type": "string",
                    "description": "Kata kunci di kolom Keterangan (case-insensitive). Opsional.",
                },
                "jumlah": {
                    "type": "number",
                    "description": "Nominal pengeluaran dalam angka, contoh 8000. Opsional.",
                },
            },
            "required": [],
        },
    },
]


TOOL_FUNCTIONS = {
    "add_expense": add_expense,
    "get_expenses": get_expenses,
    "get_balance": get_balance,
    "get_total_expenses": get_total_expenses,
    "get_expense_summary": get_expense_summary,
    "delete_expense": delete_expense,
}
