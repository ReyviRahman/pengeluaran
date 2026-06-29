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
