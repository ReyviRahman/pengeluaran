# Belajar AI Telegram Bot

Project ini menerima pesan masuk dari Telegram Bot menggunakan webhook, lalu membalasnya menggunakan Google Gemini dengan bantuan function calling untuk membaca Google Sheet.

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
   GOOGLE_SHEETS_CREDENTIALS_PATH=credentials.json
   SPREADSHEET_ID=spreadsheet_id_kamu
   SHEET_NAME=Sheet1
   ```

   - `TELEGRAM_BOT_TOKEN`: token yang diberikan BotFather.
   - `WEBHOOK_URL`: URL publik aplikasi ini. **Jangan tambahkan `/webhook`** di akhir, karena kode akan menambahkannya otomatis.
   - `WEBHOOK_SECRET`: string acak untuk memvalidasi request dari Telegram.
   - `GEMINI_API_KEY`: API key dari [Google AI Studio](https://aistudio.google.com/app/apikey).
   - `GEMINI_MODEL`: model Gemini yang digunakan, default `gemini-1.5-flash`.
   - `GOOGLE_SHEETS_CREDENTIALS_PATH`: path ke file JSON service account Google Cloud.
   - `SPREADSHEET_ID`: ID Google Sheet yang ingin dibaca.
   - `SHEET_NAME`: nama worksheet, default `Sheet1`.

## Setup Google Sheets

1. **Buat service account** di [Google Cloud Console](https://console.cloud.google.com/iam-admin/serviceaccounts).
2. **Download file credentials JSON** dan simpan di project ini, misalnya `credentials.json`.
3. **Enable Google Sheets API** di project Google Cloud kamu.
4. **Share Google Sheet** ke email service account yang ada di `credentials.json` (email biasanya berakhiran `@...gserviceaccount.com`).
5. Isi `.env`:

   ```env
   GOOGLE_SHEETS_CREDENTIALS_PATH=credentials.json
   SPREADSHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
   SHEET_NAME=Sheet1
   ```

### Cek Koneksi Google Sheet

Setelah server berjalan, buka endpoint ini di browser atau curl:

```bash
curl http://localhost:8000/check-sheet
```

Jika berhasil, akan muncul jumlah baris data. Jika gagal, pesan error akan menjelaskan apa yang kurang (file credentials, permission, sheet ID, dll).

## Menjalankan Aplikasi

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Pada saat startup, aplikasi akan otomatis mendaftarkan webhook ke Telegram.

## Menjalankan dengan Docker

Project ini sudah menyertakan `Dockerfile` dan `docker-compose.yml` yang menjalankan aplikasi beserta database PostgreSQL.

1. Pastikan Docker dan Docker Compose sudah terinstall.

2. Copy `.env.example` ke `.env` dan isi semua nilai yang diperlukan (termasuk bagian PostgreSQL):

   ```bash
   cp .env.example .env
   ```

3. Pastikan file `credentials.json` (service account Google Cloud) berada di root project.

4. Jalankan stack:

   ```bash
   docker compose up -d
   ```

5. Cek health check:

   ```bash
   curl http://localhost:8000/
   ```

6. Untuk melihat log:

   ```bash
   docker compose logs -f app
   ```

7. Untuk menghentikan:

   ```bash
   docker compose down
   ```

   Jika ingin menghapus volume database (data akan hilang):

   ```bash
   docker compose down -v
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

## Contoh Pertanyaan ke Bot

Setelah setup Google Sheets selesai, kamu bisa bertanya seperti ini ke bot:

- "Lihat pengeluaran terbaru"
- "10 pengeluaran terakhir saya apa saja?"
- "Total pengeluaran dan saldo akhir saya berapa?"
- "Ringkasan keuangan saya"
- "Ada pengeluaran tanggal 15 Juni 2026 apa saja?"
- "Pengeluaran tanggal 16 Juni"
- "Tanggal berapa hari ini?"
- "Ringkasan keuangan saya"
- "Hapus pengeluaran terakhir"
- "Batalkan input terakhir"
- "Hapus pengeluaran makan siang tadi"
- "Hapus data tanggal 16/06/2026"

## Catatan Keamanan

- Jangan commit file `.env` dan `credentials.json` ke repository.
- `WEBHOOK_SECRET` bersifat opsional tapi sangat direkomendasikan untuk mencegah request palsu ke endpoint webhook.
