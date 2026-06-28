# Belajar AI Telegram Bot

Project ini menerima pesan masuk dari Telegram Bot menggunakan webhook, lalu membalasnya menggunakan Google Gemini. Versi ini adalah versi paling dasar: tidak ada database, tidak ada Google Sheets, dan tidak ada tools. Hanya user dan AI yang saling berinteraksi.

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
   GEMINI_API_KEY=api_key_dari_google_ai_studio
   GEMINI_MODEL=gemini-1.5-flash
   ```

   - `TELEGRAM_BOT_TOKEN`: token yang diberikan BotFather.
   - `WEBHOOK_URL`: URL publik aplikasi ini. **Jangan tambahkan `/webhook`** di akhir, karena kode akan menambahkannya otomatis.
   - `WEBHOOK_SECRET`: string acak untuk memvalidasi request dari Telegram (opsional tapi direkomendasikan).
   - `GEMINI_API_KEY`: API key dari [Google AI Studio](https://aistudio.google.com/app/apikey).
   - `GEMINI_MODEL`: model Gemini yang digunakan, default `gemini-1.5-flash`.

## Menjalankan Aplikasi

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Pada saat startup, aplikasi akan otomatis mendaftarkan webhook ke Telegram.

## Menjalankan dengan Docker

1. Pastikan Docker dan Docker Compose sudah terinstall.

2. Copy `.env.example` ke `.env` dan isi semua nilai yang diperlukan:

   ```bash
   cp .env.example .env
   ```

3. Jalankan stack:

   ```bash
   docker compose up -d
   ```

4. Cek health check:

   ```bash
   curl http://localhost:8000/
   ```

5. Untuk melihat log:

   ```bash
   docker compose logs -f app
   ```

6. Untuk menghentikan:

   ```bash
   docker compose down
   ```

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
