import os
from unittest.mock import MagicMock, patch

# Pastikan env minimum terpenuhi sebelum main (dan config) di-import.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy-token")
os.environ.setdefault("WEBHOOK_URL", "https://example.com")

from fastapi.testclient import TestClient

import config
import main


def _make_mock_sheet():
    """Buat mock worksheet lengkap untuk /check-sheet."""
    sheet = MagicMock()
    sheet.title = "Sheet1"
    sheet.row_values.return_value = ["Tgl", "Keterangan", "Pengeluaran"]

    spreadsheet = MagicMock()
    spreadsheet.title = "Pengeluaran Saya"
    spreadsheet.worksheets.return_value = [sheet]

    sheet.spreadsheet = spreadsheet
    return sheet


def test_check_sheet_success():
    sheet = _make_mock_sheet()

    with patch("tools._get_sheet", return_value=sheet), patch.object(
        config, "GOOGLE_SHEET_ID", "sheet-id-123"
    ), patch("telegram.set_webhook"):
        with TestClient(main.app) as client:
            response = client.get("/check-sheet")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["sheet_id"] == "sheet-id-123"
    assert data["title"] == "Pengeluaran Saya"
    assert data["active_worksheet"] == "Sheet1"
    assert data["headers"] == ["Tgl", "Keterangan", "Pengeluaran"]
    assert "Sheet1" in data["worksheets"]


def test_check_sheet_missing_sheet_id():
    with patch.object(config, "GOOGLE_SHEET_ID", ""), patch("telegram.set_webhook"):
        with TestClient(main.app) as client:
            response = client.get("/check-sheet")

    assert response.status_code == 400
    assert "GOOGLE_SHEET_ID" in response.json()["detail"]


def test_check_sheet_open_failure():
    with patch("tools._get_sheet", side_effect=Exception("autentikasi gagal")), patch.object(
        config, "GOOGLE_SHEET_ID", "sheet-id-123"
    ), patch("telegram.set_webhook"):
        with TestClient(main.app) as client:
            response = client.get("/check-sheet")

    assert response.status_code == 503
    assert "Gagal membuka Google Sheet" in response.json()["detail"]
