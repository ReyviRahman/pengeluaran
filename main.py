import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request

import config
import telegram

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
