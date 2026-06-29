import logging
from datetime import datetime
from typing import Optional

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
    """Ambil worksheet pertama dari Google Sheet yang dikonfigurasi."""
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(config.GOOGLE_SHEET_ID).sheet1


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
            "Gunakan tool ini setiap kali user bertanya tentang pengeluaran, "
            "misalnya: pengeluaran hari ini, total pengeluaran, daftar pengeluaran, "
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
]


TOOL_FUNCTIONS = {
    "add_expense": add_expense,
    "get_expenses": get_expenses,
    "get_balance": get_balance,
}
