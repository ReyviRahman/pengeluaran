from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import tools


def _make_sheet(rows: list[dict]):
    """Buat mock worksheet yang mengembalikan records tertentu."""
    sheet = MagicMock()
    sheet.get_all_records.return_value = rows
    return sheet


def test_normalize_pengeluaran_angka_murni():
    assert tools._normalize_pengeluaran(15000) == 15000.0
    assert tools._normalize_pengeluaran(15000.5) == 15000.5
    assert tools._normalize_pengeluaran("15000") == 15000.0


def test_normalize_pengeluaran_format_ribuan_indonesia():
    assert tools._normalize_pengeluaran("15.000") == 15000.0
    assert tools._normalize_pengeluaran("1.500.000") == 1500000.0
    assert tools._normalize_pengeluaran("15.000,50") == 15000.5


def test_normalize_pengeluaran_dengan_prefix_mata_uang():
    assert tools._normalize_pengeluaran("Rp 15.000") == 15000.0
    assert tools._normalize_pengeluaran("Rp15.000") == 15000.0
    assert tools._normalize_pengeluaran("IDR 15.000,50") == 15000.5


def test_normalize_pengeluaran_kosong_atau_teks():
    assert tools._normalize_pengeluaran("") == 0.0
    assert tools._normalize_pengeluaran(None) == 0.0
    assert tools._normalize_pengeluaran("gratis") == 0.0


def test_find_column_case_insensitive():
    headers = ["Tgl", "Keterangan", "Pengeluaran "]
    assert tools._find_column(headers, "pengeluaran") == "Pengeluaran "
    assert tools._find_column(headers, "TGL") == "Tgl"
    assert tools._find_column(headers, "keterangan") == "Keterangan"
    assert tools._find_column(headers, "tidak ada") is None


def test_get_expenses_tanpa_filter():
    rows = [
        {"Tgl": "2026-06-29", "Keterangan": "Nasi Orak Arik", "Pengeluaran": 15000},
        {"Tgl": "2026-06-28", "Keterangan": "Makan Kfc", "Pengeluaran": 50000},
    ]

    with patch("tools._get_sheet", return_value=_make_sheet(rows)):
        result = tools.get_expenses()

    assert result["count"] == 2
    assert result["total"] == 65000.0
    assert result["items"][0]["Pengeluaran"] == 15000.0
    assert result["items"][1]["Pengeluaran"] == 50000.0


def test_get_expenses_filter_tanggal():
    rows = [
        {"Tgl": "2026-06-29", "Keterangan": "Nasi Orak Arik", "Pengeluaran": 15000},
        {"Tgl": "2026-06-28", "Keterangan": "Makan Kfc", "Pengeluaran": 50000},
    ]

    with patch("tools._get_sheet", return_value=_make_sheet(rows)):
        result = tools.get_expenses(filter_date="2026-06-29")

    assert result["count"] == 1
    assert result["total"] == 15000.0
    assert result["items"][0]["Keterangan"] == "Nasi Orak Arik"


def test_get_expenses_filter_keyword():
    rows = [
        {"Tgl": "2026-06-29", "Keterangan": "Nasi Orak Arik", "Pengeluaran": 15000},
        {"Tgl": "2026-06-28", "Keterangan": "Makan Kfc", "Pengeluaran": 50000},
        {"Tgl": "2026-06-28", "Keterangan": "Makan Nasi Goreng", "Pengeluaran": 20000},
    ]

    with patch("tools._get_sheet", return_value=_make_sheet(rows)):
        result = tools.get_expenses(keyword="makan")

    assert result["count"] == 2
    assert result["total"] == 70000.0


def test_get_expenses_header_case_insensitive():
    rows = [
        {"TGL": "2026-06-29", "KETERANGAN": "Nasi Orak Arik", "PENGELUARAN": 15000},
    ]

    with patch("tools._get_sheet", return_value=_make_sheet(rows)):
        result = tools.get_expenses()

    assert result["count"] == 1
    assert result["total"] == 15000.0


def test_get_expenses_kolom_tidak_ditemukan():
    rows = [{"Tgl": "2026-06-29", "Keterangan": "Nasi Orak Arik", "Amount": 15000}]

    with patch("tools._get_sheet", return_value=_make_sheet(rows)):
        result = tools.get_expenses()

    assert "error" in result
    assert "Pengeluaran" in result["error"]


def _make_sheet_with_append(headers: list[str]):
    """Buat mock worksheet dengan row_values dan append_row untuk add_expense."""
    sheet = MagicMock()
    sheet.row_values.return_value = headers
    sheet.append_row = MagicMock()
    return sheet


def test_add_expense_hari_ini():
    sheet = _make_sheet_with_append(["Tgl", "Keterangan", "Pengeluaran"])

    with patch("tools._get_sheet", return_value=sheet):
        result = tools.add_expense(keterangan="es krim", jumlah=8000)

    assert result["success"] is True
    assert "es krim" in result["message"]
    assert "8,000" in result["message"]
    sheet.append_row.assert_called_once()
    appended = sheet.append_row.call_args[0][0]
    assert appended[1] == "es krim"
    assert appended[2] == 8000
    assert sheet.append_row.call_args.kwargs.get("value_input_option") == "USER_ENTERED"


def test_add_expense_dengan_tanggal():
    sheet = _make_sheet_with_append(["Tgl", "Keterangan", "Pengeluaran"])

    with patch("tools._get_sheet", return_value=sheet):
        result = tools.add_expense(keterangan="es krim", jumlah=10000, tanggal="2026-06-30")

    assert result["success"] is True
    appended = sheet.append_row.call_args[0][0]
    assert appended[0] == "2026-06-30"
    assert appended[1] == "es krim"
    assert appended[2] == 10000


def test_add_expense_kolom_tidak_ditemukan():
    sheet = _make_sheet_with_append(["Tgl", "Keterangan", "Amount"])

    with patch("tools._get_sheet", return_value=sheet):
        result = tools.add_expense(keterangan="es krim", jumlah=8000)

    assert "error" in result
    assert "Tgl/Keterangan/Pengeluaran" in result["error"]


def test_add_expense_jumlah_tidak_valid():
    sheet = _make_sheet_with_append(["Tgl", "Keterangan", "Pengeluaran"])

    with patch("tools._get_sheet", return_value=sheet):
        result = tools.add_expense(keterangan="es krim", jumlah="gratis")

    assert "error" in result
    assert "Jumlah" in result["error"]
