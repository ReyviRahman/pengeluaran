import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request

import config
import telegram
import tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
# Matikan logging httpx agar URL dengan token bot tidak tercetak di log.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler untuk setup webhook saat startup."""
    await telegram.set_webhook()
    yield


app = FastAPI(title="Belajar AI Telegram Bot", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok", "message": "Belajar AI Telegram Bot aktif"}


@app.post("/")
async def root_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    """Fallback endpoint jika webhook terdaftar ke root URL."""
    return await webhook(request, x_telegram_bot_api_secret_token)


@app.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    """Endpoint untuk menerima update dari Telegram."""
    if config.WEBHOOK_SECRET and x_telegram_bot_api_secret_token != config.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    update_id = data.get("update_id")
    message = data.get("message")

    if not message:
        return {"ok": True}

    await telegram.process_update(update_id, message)
    return {"ok": True}


@app.post("/set-webhook")
async def manual_set_webhook():
    """Endpoint manual untuk mendaftarkan ulang webhook."""
    result = await telegram.set_webhook()
    if result is None:
        raise HTTPException(status_code=503, detail="Gagal set webhook")
    return {"ok": True, "result": result}


@app.get("/check-sheet")
async def check_sheet():
    """Cek koneksi ke Google Sheet yang dikonfigurasi.

    Mengembalikan metadata spreadsheet dan header baris pertama worksheet aktif.
    Berguna untuk memastikan credentials dan GOOGLE_SHEET_ID sudah benar.
    """
    if not config.GOOGLE_SHEET_ID:
        raise HTTPException(status_code=400, detail="GOOGLE_SHEET_ID belum diatur di file .env")

    try:
        sheet = tools._get_sheet()
        spreadsheet = sheet.spreadsheet
        worksheets = [ws.title for ws in spreadsheet.worksheets()]
        headers = sheet.row_values(1)
    except FileNotFoundError as exc:
        logger.exception("File credentials tidak ditemukan")
        raise HTTPException(status_code=500, detail=f"File credentials tidak ditemukan: {exc}") from exc
    except Exception as exc:
        logger.exception("Gagal membuka Google Sheet")
        raise HTTPException(status_code=503, detail=f"Gagal membuka Google Sheet: {exc}") from exc

    return {
        "ok": True,
        "sheet_id": config.GOOGLE_SHEET_ID,
        "title": spreadsheet.title,
        "worksheets": worksheets,
        "active_worksheet": sheet.title,
        "headers": headers,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
