import asyncio
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("[ERROR] TELEGRAM_BOT_TOKEN tidak ditemukan di .env")
    exit(1)

print(f"Token yang terbaca: {TOKEN[:20]}...")


async def check_token():
    url = f"https://api.telegram.org/bot{TOKEN}/getMe"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            data = response.json()

        if data.get("ok"):
            result = data["result"]
            print("[OK] Token valid")
            print(f"   Bot ID: {result['id']}")
            print(f"   Nama: {result['first_name']}")
            print(f"   Username: @{result['username']}")
        else:
            print(f"[ERROR] Token tidak valid: {data}")
    except httpx.TimeoutException:
        print("[ERROR] Timeout saat menghubungi Telegram API")
    except Exception as exc:
        print(f"[ERROR] {exc}")


if __name__ == "__main__":
    asyncio.run(check_token())
