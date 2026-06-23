from unittest.mock import MagicMock

import tools


def test_get_cell_e2():
    mock_worksheet = MagicMock()
    mock_worksheet.acell.return_value.value = "150000"

    original_get_worksheet = tools._get_worksheet
    tools._get_worksheet = lambda: mock_worksheet
    try:
        result = tools.get_cell_e2()
    finally:
        tools._get_worksheet = original_get_worksheet

    assert result["status"] == "success"
    assert result["cell"] == "E2"
    assert result["value"] == "150000"


def test_get_cell_f2():
    mock_worksheet = MagicMock()
    mock_worksheet.acell.return_value.value = "Rp1.000.000"

    original_get_worksheet = tools._get_worksheet
    tools._get_worksheet = lambda: mock_worksheet
    try:
        result = tools.get_cell_f2()
    finally:
        tools._get_worksheet = original_get_worksheet

    assert result["status"] == "success"
    assert result["cell"] == "F2"
    assert result["value"] == "Rp1.000.000"


def test_get_total_pengeluaran():
    mock_worksheet = MagicMock()
    mock_worksheet.acell.return_value.value = "Rp3.269.959"

    original_get_worksheet = tools._get_worksheet
    tools._get_worksheet = lambda: mock_worksheet
    try:
        result = tools.get_total_pengeluaran()
    finally:
        tools._get_worksheet = original_get_worksheet

    assert result["status"] == "success"
    assert result["total_pengeluaran"] == "Rp3.269.959"


def test_get_saldo_akhir():
    mock_worksheet = MagicMock()
    mock_worksheet.acell.return_value.value = "Rp730.041"

    original_get_worksheet = tools._get_worksheet
    tools._get_worksheet = lambda: mock_worksheet
    try:
        result = tools.get_saldo_akhir()
    finally:
        tools._get_worksheet = original_get_worksheet

    assert result["status"] == "success"
    assert result["saldo_akhir"] == "Rp730.041"


def test_get_expense_summary():
    original_get_worksheet = tools._get_worksheet
    original_get_sheet_values = tools._get_sheet_values

    mock_worksheet = MagicMock()
    mock_worksheet.acell.side_effect = lambda cell: {
        "E2": MagicMock(value="Rp3.269.959"),
        "F2": MagicMock(value="Rp730.041"),
    }.get(cell)

    tools._get_worksheet = lambda: mock_worksheet
    tools._get_sheet_values = lambda: [
        ["22/06/2026", "Makan Malam", "50000", "", "", ""],
    ]

    try:
        result = tools.get_expense_summary()
    finally:
        tools._get_worksheet = original_get_worksheet
        tools._get_sheet_values = original_get_sheet_values

    assert result["status"] == "success"
    assert result["data"]["total_pengeluaran"] == "Rp3.269.959"
    assert result["data"]["saldo_akhir"] == "Rp730.041"
    assert result["data"]["tanggal_terakhir"] == "22/06/2026"


def test_parse_delete_input_with_date_description_and_amount():
    parsed = tools._parse_delete_input("hapus 16 juni es krim 5rb")
    assert parsed["date"] == "2026-06-16"
    assert parsed["description"] == "es krim"
    assert parsed["amount"] == 5000


def test_parse_delete_input_with_description_and_amount():
    parsed = tools._parse_delete_input("hapus es krim 5k")
    assert parsed["date"] == ""
    assert parsed["description"] == "es krim"
    assert parsed["amount"] == 5000


def test_parse_delete_input_ignores_command_words():
    parsed = tools._parse_delete_input("batalkan 16/06/2026 makan siang")
    assert parsed["date"] == "2026-06-16"
    assert parsed["description"] == "makan siang"


def test_parse_delete_input_no_amount():
    parsed = tools._parse_delete_input("hapus makan siang")
    assert parsed["date"] == ""
    assert parsed["description"] == "makan siang"
    assert parsed["amount"] == 0


def test_find_matching_rows_by_date():
    values = [
        ["16/06/2026", "Makan Siang", "50000", "", "", ""],
        ["17/06/2026", "Parkir", "10000", "", "", ""],
        ["16/06/2026", "Es Krim", "20000", "", "", ""],
    ]

    matches = tools._find_matching_rows(values, "16 Juni 2026", None)
    assert len(matches) == 2
    assert matches[0][0] == 2
    assert matches[1][0] == 4


def test_find_matching_rows_by_description():
    values = [
        ["16/06/2026", "Makan Siang", "50000", "", "", ""],
        ["17/06/2026", "Parkir", "10000", "", "", ""],
        ["16/06/2026", "Es Krim", "20000", "", "", ""],
    ]

    matches = tools._find_matching_rows(values, None, "makan")
    assert len(matches) == 1
    assert matches[0][0] == 2
    assert matches[0][1][1] == "Makan Siang"


def test_find_matching_rows_by_date_and_description():
    values = [
        ["16/06/2026", "Makan Siang", "50000", "", "", ""],
        ["17/06/2026", "Parkir", "10000", "", "", ""],
        ["16/06/2026", "Es Krim", "20000", "", "", ""],
    ]

    matches = tools._find_matching_rows(values, "16/06/2026", "es krim")
    assert len(matches) == 1
    assert matches[0][0] == 4


def test_find_matching_rows_no_match():
    values = [
        ["16/06/2026", "Makan Siang", "50000", "", "", ""],
    ]

    matches = tools._find_matching_rows(values, "01/01/2020", None)
    assert len(matches) == 0


def test_find_matching_rows_ambiguous():
    values = [
        ["16/06/2026", "Makan Siang", "50000", "", "", ""],
        ["16/06/2026", "Makan Malam", "70000", "", "", ""],
    ]

    matches = tools._find_matching_rows(values, "16 Juni 2026", None)
    assert len(matches) == 2
