import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

import config
import gemini
import tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
# Matikan logging httpx agar URL dengan token bot tidak tercetak di log.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def log_message(update_id: int, message: dict) -> None:
    """Mencatat pesan masuk ke log console."""
    chat = message.get("chat", {})
    sender = message.get("from", {})
    text = message.get("text", "")
    date_ts = message.get("date")

    received_at = datetime.now(timezone.utc).isoformat()
    sent_at = None
    if date_ts:
        sent_at = datetime.fromtimestamp(date_ts, tz=timezone.utc).isoformat()

    log_entry = {
        "update_id": update_id,
        "message_id": message.get("message_id"),
        "chat_id": chat.get("id"),
        "chat_type": chat.get("type"),
        "user_id": sender.get("id"),
        "username": sender.get("username"),
        "first_name": sender.get("first_name"),
        "text": text,
        "sent_at": sent_at,
        "received_at": received_at,
    }

    logger.info("Pesan masuk: %s", log_entry)


async def send_message(chat_id: int, text: str) -> None:
    """Mengirim pesan balasan ke Telegram."""
    url = f"{TELEGRAM_API_BASE}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

        if not result.get("ok"):
            logger.error("Gagal kirim pesan: %s", result)
        else:
            logger.info("Pesan balasan terkirim ke chat %s", chat_id)
    except Exception as exc:
        logger.error("Error saat kirim pesan ke Telegram: %s", exc)


async def send_chat_action(chat_id: int, action: str) -> None:
    """Mengirim aksi chat (misalnya typing) ke Telegram."""
    url = f"{TELEGRAM_API_BASE}/sendChatAction"
    payload = {
        "chat_id": chat_id,
        "action": action,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except Exception as exc:
        logger.error("Error saat kirim chat action ke Telegram: %s", exc)


GREETING_WORDS = {"halo", "hai", "hi", "hello", "pagi", "siang", "sore", "malam", "hey"}
HOW_ARE_YOU_QUESTIONS = {"apa kabar", "gimana kabar", "bagaimana kabar"}


def is_greeting(text: str) -> bool:
    """Deteksi apakah pesan dari user adalah sapaan."""
    normalized = text.lower().strip()
    words = normalized.split()
    if not words:
        return False
    if words[0].strip(",.!?") in GREETING_WORDS:
        return True
    if any(phrase in normalized for phrase in HOW_ARE_YOU_QUESTIONS):
        return True
    return False


def get_simple_reply(text: str) -> str | None:
    """Balasan cepat untuk sapaan dan jawaban santai user."""
    normalized = text.lower().strip(".,!? ")
    words = normalized.split()
    if not words:
        return None

    # Sapaan yang disertai pertanyaan kabar.
    if is_greeting(text) and any(phrase in normalized for phrase in HOW_ARE_YOU_QUESTIONS):
        return "Hai Reyyy, aku baik. Kamu gimana?"

    # Sapaan biasa.
    if is_greeting(text):
        return "Hai Reyyy bagaimana hari mu?"

    # Jawaban santai user atas pertanyaan "bagaimana harimu".
    if len(words) <= 4:
        positive = {"amann", "aman", "baik", "baik-baik", "baik2", "sehat", "alhamdulillah", "syukurlah", "senang", "mantap"}
        neutral = {"lumayan", "biasa", "oke", "ok", "okey"}
        negative = {"capek", "lelah", "ngantuk", "buruk", "sakit", "sedih", "biasa aja"}

        if any(w in positive for w in words):
            return "Syukurlah kalo gitu. Ada yang bisa aku bantu hari ini?"
        if any(w in neutral for w in words):
            return "Oke, semoga harimu makin baik ya. Ada yang mau ditanyain?"
        if any(w in negative for w in words):
            return "Semangat ya Reyyy. Kalau ada yang mau dibantu soal keuangan, bilang aja."

    return None


async def process_update(update_id: int, message: dict) -> None:
    """Mencatat pesan dan mengirim balasan melalui Gemini."""
    log_message(update_id, message)

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return

    await send_chat_action(chat_id, "typing")

    reply = get_simple_reply(text)
    if reply is None:
        reply = await gemini.generate_response(text)

    await send_message(chat_id, reply)


async def set_webhook() -> dict | None:
    """Mendaftarkan webhook ke Telegram."""
    url = f"{TELEGRAM_API_BASE}/setWebhook"

    webhook_url = f"{config.WEBHOOK_URL.rstrip('/')}/webhook"

    payload = {
        "url": webhook_url,
    }

    if config.WEBHOOK_SECRET:
        payload["secret_token"] = config.WEBHOOK_SECRET

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

        if not result.get("ok"):
            logger.error("Gagal set webhook: %s", result)
            return None

        logger.info("Webhook berhasil didaftarkan: %s", result.get("result", True))
        return result
    except httpx.TimeoutException:
        logger.error("Timeout saat menghubungi Telegram API. Cek koneksi internet atau firewall.")
        return None
    except httpx.HTTPStatusError as exc:
        logger.error("HTTP error saat set webhook: %s - %s", exc.response.status_code, exc.response.text)
        return None
    except Exception as exc:
        logger.error("Unexpected error saat set webhook: %s", exc)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler untuk setup webhook saat startup."""
    await set_webhook()
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

    await process_update(update_id, message)
    return {"ok": True}


@app.post("/set-webhook")
async def manual_set_webhook():
    """Endpoint manual untuk mendaftarkan ulang webhook."""
    result = await set_webhook()
    if result is None:
        raise HTTPException(status_code=503, detail="Gagal set webhook")
    return {"ok": True, "result": result}


@app.get("/check-sheet")
async def check_sheet():
    """Endpoint diagnosis untuk memeriksa koneksi ke Google Sheet."""
    return tools.check_sheet_connection()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
