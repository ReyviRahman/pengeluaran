# Panduan Menjalankan Project dengan Docker

Project ini sudah disiapkan untuk berjalan menggunakan Docker dan Docker Compose, lengkap dengan database PostgreSQL.

---

## 1. Persiapan Pertama Kali

Pastikan hal-hal berikut sudah siap:

- Docker Desktop atau Docker Engine + Docker Compose sudah terinstall.
- File `.env` sudah dibuat dan diisi dari `.env.example`.
- File `credentials.json` (service account Google Cloud) berada di root project.

Lalu jalankan:

```bash
docker compose up -d
```

Perintah ini akan:

- Mengunduh image PostgreSQL.
- Build image aplikasi dari `Dockerfile`.
- Membuat dan menjalankan container `belajar-ai-db` dan `belajar-ai-app`.
- Menjalankan keduanya di background (`-d` = detached).

Cek apakah semua berjalan:

```bash
docker compose ps
curl http://localhost:8000/
```

---

## 2. Apakah Setiap Kali Running Harus `docker compose up -d`?

**Tidak harus.** Perintah `docker compose up -d` hanya perlu dijalankan:

- Saat pertama kali setup.
- Setelah semua container dihentikan dengan `docker compose down`.
- Setelah komputer direstart dan container belum berjalan.

Jika container masih berjalan dan kamu hanya ingin melihat log:

```bash
docker compose logs -f app
```

Jika ingin me-restart tanpa mengubah apa pun:

```bash
docker compose restart
```

---

## 3. Jika Ada Perubahan Kode

Docker **tidak otomatis** melihat perubahan file di laptopmu. Kamu punya dua pilihan:

### Pilihan A: Rebuild Ulang (Paling Aman)

```bash
docker compose up -d --build
```

Perintah ini akan build image baru dari kode terbaru, lalu menjalankan ulang container.

### Pilihan B: Mount Kode sebagai Volume (Lebih Cepat saat Development)

Jika kamu sering mengubah kode, tambahkan volume di `docker-compose.yaml` agar file di laptop langsung terlihat di container:

```yaml
services:
  app:
    # ... bagian lain tetap
    volumes:
      - ./credentials.json:/app/credentials.json:ro
      - .:/app  # tambahkan ini
```

Kemudian jalankan:

```bash
docker compose up -d --build
```

Dengan cara ini, setiap kali mengedit kode di laptop, container langsung menggunakan versi terbaru. Kamu hanya perlu restart container:

```bash
docker compose restart app
```

> Catatan: mode volume ini cocok untuk development. Untuk production, sebaiknya kode di-copy ke dalam image.

---

## 4. Jika Ada Perubahan `Dockerfile` atau `docker-compose.yaml`

Kamu **harus rebuild** image agar perubahan diterapkan:

```bash
docker compose up -d --build
```

Atau jika ingin benar-benar bersih dari image lama:

```bash
docker compose down
docker compose up -d --build
```

Contoh kasus yang wajib rebuild:

- Mengubah isi `Dockerfile`.
- Menambah atau mengubah dependency di `pyproject.toml` atau `requirements.txt`.
- Mengubah `CMD` atau `EXPOSE` di `Dockerfile`.
- Mengubah environment variable di `docker-compose.yaml` yang bukan berasal dari `.env`.

---

## 5. Perintah yang Sering Digunakan

| Perintah | Fungsi |
|---|---|
| `docker compose up -d` | Jalankan container di background. |
| `docker compose up -d --build` | Build ulang image, lalu jalankan container. |
| `docker compose down` | Hentikan dan hapus container. |
| `docker compose down -v` | Hentikan, hapus container, dan hapus data PostgreSQL. |
| `docker compose restart` | Restart container yang sedang berjalan. |
| `docker compose restart app` | Restart hanya service `app`. |
| `docker compose logs -f app` | Lihat log aplikasi secara realtime. |
| `docker compose ps` | Cek status container. |
| `docker compose exec app bash` | Masuk ke dalam container `app`. |

---

## 6. Workflow Harian yang Disarankan

### Tanpa Volume Mount

```bash
# Setelah mengedit kode
docker compose up -d --build

# Lihat log
docker compose logs -f app
```

### Dengan Volume Mount

```bash
# Edit kode di editor
# Lalu restart container saja
docker compose restart app
```

---

## 7. Tips Penting

- Jangan lupa `credentials.json` harus selalu ada di root project, karena `docker-compose.yaml` memasangnya sebagai volume.
- `WEBHOOK_URL` di `.env` harus URL publik yang bisa dijangkau Telegram. Kalau hanya `localhost`, webhook dari Telegram tidak akan sampai.
- Kalau ingin mengganti port aplikasi di laptop (misalnya dari `8000` ke `8080`), ubah bagian `ports` di `docker-compose.yaml`:

  ```yaml
  ports:
    - "8080:8000"
  ```

  Lalu rebuild: `docker compose up -d --build`.
- `DATABASE_URL` di dalam container akan di-override otomatis oleh `docker-compose.yaml` untuk mengarah ke service `db`, jadi kamu tidak perlu mengubahnya di `.env`.

---

## 8. Menghubungkan Database ke pgAdmin4

Database PostgreSQL yang berjalan di Docker sudah di-expose ke port `5432` di laptopmu. Kamu bisa langsung menghubungkannya ke pgAdmin4.

### Jika pgAdmin4 Berjalan di Laptop (Desktop)

1. Buka pgAdmin4.
2. Klik kanan **Servers** → **Register** → **Server...**
3. Di tab **General**, isi **Name**: `belajar-ai`.
4. Di tab **Connection**, isi:
   - **Host name/address**: `localhost`
   - **Port**: `5432`
   - **Maintenance database**: `belajar_ai`
   - **Username**: `belajarai`
   - **Password**: `belajarai`
5. Klik **Save**.

> Catatan: username, password, dan nama database mengikuti nilai default di `docker-compose.yaml` dan `.env.example`. Jika kamu mengubahnya di `.env`, sesuaikan saja.

### Jika pgAdmin4 Juga Berjalan di Docker

Jika pgAdmin4 kamu jalankan lewat Docker container, `localhost` tidak akan berfungsi karena masing-masing container punya network sendiri. Ada dua cara:

#### Cara 1: Gunakan Nama Service `db`

Pastikan pgAdmin4 berada dalam network yang sama dengan project ini. Jika kamu menjalankan pgAdmin4 di file `docker-compose.yaml` yang sama, gunakan:

- **Host name/address**: `db`

#### Cara 2: Gunakan `host.docker.internal`

Jika pgAdmin4 berada di container terpisah tetapi di laptop yang sama, gunakan:

- **Host name/address**: `host.docker.internal`

### Jika Port 5432 Sudah Dipakai PostgreSQL Lain

Jika di laptopmu sudah ada PostgreSQL lain yang menggunakan port `5432`, ubah port mapping di `docker-compose.yaml`, misalnya ke `5433`:

```yaml
ports:
  - "5433:5432"
```

Lalu rebuild:

```bash
docker compose up -d --build
```

Di pgAdmin4, gunakan port `5433` saat menyambungkan.

---

## 9. Troubleshooting Umum

### Container app tidak bisa start

Cek log:

```bash
docker compose logs app
```

Biasanya disebabkan oleh:

- `.env` belum diisi atau ada variabel yang kosong.
- `credentials.json` tidak ditemukan.
- Database belum siap (sudah ditangani oleh `healthcheck` dan `depends_on`).

### Port 8000 sudah digunakan

Ubah port mapping di `docker-compose.yaml`, misalnya:

```yaml
ports:
  - "8080:8000"
```

Lalu rebuild:

```bash
docker compose up -d --build
```

### Ingin reset total (data PostgreSQL ikut hilang)

```bash
docker compose down -v
docker compose up -d --build
```
