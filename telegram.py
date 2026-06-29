import logging
from datetime import datetime, timezone

import httpx

import agent
import config

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
    """Mengirim status typing/typing indicator ke Telegram."""
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


async def process_update(update_id: int, message: dict) -> None:
    """Mencatat pesan dan mengirim balasan melalui Gemini."""
    log_message(update_id, message)

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if not chat_id or not text:
        return

    await send_chat_action(chat_id, "typing")
    reply, _ = agent.run_agent([], text)
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
