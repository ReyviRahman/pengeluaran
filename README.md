# Belajar AI Telegram Bot

Project ini menerima pesan masuk dari Telegram Bot menggunakan webhook, lalu membalasnya menggunakan OpenAI (ChatGPT). 

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
   OPENAI_API_KEY=api_key_dari_openai
   OPENAI_MODEL=gpt-4o-mini
   GOOGLE_SHEET_ID=id_dari_google_sheet
   ```

   - `TELEGRAM_BOT_TOKEN`: token yang diberikan BotFather.
   - `WEBHOOK_URL`: URL publik aplikasi ini. **Jangan tambahkan `/webhook`** di akhir, karena kode akan menambahkannya otomatis.
   - `WEBHOOK_SECRET`: string acak untuk memvalidasi request dari Telegram (opsional tapi direkomendasikan).
   - `OPENAI_API_KEY`: API key dari [OpenAI Platform](https://platform.openai.com/api-keys).
   - `OPENAI_MODEL`: model OpenAI yang digunakan, default `gpt-4o-mini`.
   - `GOOGLE_SHEET_ID`: ID spreadsheet Google Sheets yang berisi data pengeluaran.

## Konfigurasi Google Sheets

1. Pastikan file `credentials.json` untuk service account sudah berada di root proyek. File ini sudah di-ignore Git, jangan di-commit.

2. Buka file `credentials.json` dan catat nilai `client_email`.

3. Di Google Sheets, bagikan spreadsheet ke email service account tersebut dengan peran **Editor**. Bot perlu izin menulis untuk mencatat pengeluaran baru.

4. Pastikan spreadsheet memiliki kolom berikut di baris pertama:

   | Tgl | Keterangan | Pengeluaran |
   |-----|------------|-------------|

   Kolom `Tgl` bisa menggunakan format `YYYY-MM-DD`, `DD/MM/YYYY`, atau format Indonesia seperti `29 Juni 2026`.

## Fitur Chat

Bot ini bisa membaca dan menulis data pengeluaran melalui chat Telegram.

### Mencatat pengeluaran baru

Kirim pesan seperti:

- `es krim 8k` → mencatat pengeluaran "es krim" sebesar 8000 untuk hari ini.
- `bensin 50k` → mencatat "bensin" sebesar 50000 untuk hari ini.
- `es krim 10k 30 juni` → mencatat "es krim" sebesar 10000 untuk tanggal 30 Juni tahun berjalan.

Bot akan menyimpan data ke kolom `Tgl`, `Keterangan`, dan `Pengeluaran` di Google Sheets.

### Menanyakan pengeluaran

- `pengeluaran hari ini berapa?`
- `total pengeluaran minggu ini`
- `daftar pengeluaran untuk makanan`

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
