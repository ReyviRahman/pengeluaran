# Belajar AI Telegram Bot

Project ini menerima pesan masuk dari Telegram Bot menggunakan webhook, lalu mencatat pesan ke log.

## Persiapan

1. Copy file `.env.example` menjadi `.env`:

   ```bash
   cp .env.example .env
   ```

2. Isi file `.env` dengan nilai yang sesuai:

   ```env
   TELEGRAM_BOT_TOKEN=token_dari_botfather
   WEBHOOK_URL=https://domain-anda.com
   WEBHOOK_SECRET=secret_acak_untuk_webhook
   ```

   - `TELEGRAM_BOT_TOKEN`: token yang diberikan BotFather.
   - `WEBHOOK_URL`: URL publik aplikasi ini (tanpa `/webhook`).
   - `WEBHOOK_SECRET`: string acak untuk memvalidasi request dari Telegram.

## Menjalankan Aplikasi

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Pada saat startup, aplikasi akan otomatis mendaftarkan webhook ke Telegram.

## Endpoint

- `GET /` — health check.
- `POST /webhook` — menerima update dari Telegram.

## Uji Coba

Kirim pesan ke bot Telegram kamu, lalu periksa log console. Pesan yang masuk akan tercatat dengan informasi:

- `update_id`
- `chat_id`
- `user_id`
- `username`
- `text`
- timestamp

## Catatan Keamanan

- Jangan commit file `.env` ke repository.
- `WEBHOOK_SECRET` bersifat opsional tapi sangat direkomendasikan untuk mencegah request palsu ke endpoint webhook.
