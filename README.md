# StokPintar — Sistem Manajemen Inventaris dengan Prediksi Restock

Aplikasi web untuk mencatat stok barang (CRUD produk & transaksi masuk/keluar),
dengan fitur **algoritma custom** untuk merangking produk mana yang paling
urgent untuk di-restock, dan memprediksi berapa hari lagi stok akan habis.

Dibuat pakai **Flask + Bootstrap 5**, cocok dijadikan portofolio untuk
melamar magang yang minta skill: algoritma, Bootstrap, bahasa pemrograman,
dan pemisahan struktur kode yang rapi.

## Fitur Utama

- **Login & registrasi admin** (password di-hash, rate limiting anti brute-force, CSRF protection)
- **CRUD Produk** — tambah, lihat, edit, hapus produk
- **Catat Transaksi Stok** — stok masuk (restock) & stok keluar (terjual/terpakai)
- **Dashboard Rekomendasi Restock** — daftar produk diurutkan otomatis dari
  yang paling urgent, pakai **merge sort** buatan sendiri (bukan `sorted()` bawaan)
- **Pencarian Produk** — pencarian SKU persis pakai **binary search** (O(log n))
  setelah data diurutkan, fallback ke pencarian nama kalau bukan SKU persis
- **Prediksi Stockout** — pakai perhitungan **moving average** dari transaksi
  14 hari terakhir untuk memperkirakan kapan stok akan habis
- **Grafik Tren Transaksi Stok** — perbandingan stok masuk/keluar 14 hari terakhir
- **Daftar Restock** — daftar produk di bawah batas minimum dan jumlah untuk mengisi kembali ke batas minimum, bisa diekspor ke CSV
- **Ekspor Laporan** — inventaris dan riwayat transaksi ke Excel, inventaris ke PDF
- **Multi-user** — admin mengelola produk dan akun staf; staf melihat data dan mencatat transaksi
- **Email Stok Kritis** — admin mendapat email saat transaksi keluar atau stok opname membuat stok mencapai batas minimum
- **Audit Transaksi** — simpan siapa yang mencatat transaksi dan penyesuaian stok
- **Stok Opname** — cocokkan stok fisik dengan sistem dan rekam selisih beserta alasan
- **Supplier & Pesanan Pembelian** — alur draft, dipesan, diterima, atau dibatalkan

## Struktur Kode

```
stokpintar/
├── app.py           # Routes/Controller — menghubungkan semuanya
├── models.py         # Model database (User, Product, Transaction)
├── algorithms.py      # Logika algoritma murni (merge sort, binary search, dst)
├── templates/         # Tampilan (Bootstrap 5)
└── static/css/        # Styling custom di atas Bootstrap
```

Kode sengaja dipisah: **Model** (data), **Algorithms** (logika bisnis),
**Routes + Templates** (controller & view). Ini mirip semangat pemisahan
tanggung jawab di pola **MVVM** yang sering dipakai di aplikasi
desktop/mobile — jadi bisa dijelaskan ke recruiter kalau kamu paham
konsepnya walau project ini bentuknya web.

## Cara Menjalankan di Komputer Sendiri

Jalankan semua perintah berikut dari folder proyek yang berisi `app.py`
dan `requirements.txt`.

1. Buat virtual environment & install dependency:
   ```
   python -m venv venv
   ```
   Aktifkan virtual environment sesuai terminal yang dipakai:
   - PowerShell: `.\venv\Scripts\Activate.ps1`
   - Command Prompt: `venv\Scripts\activate.bat`
   - Mac/Linux: `source venv/bin/activate`

   Lalu install dependency:
   ```
   pip install -r requirements.txt
   ```
2. Copy `.env.example` jadi `.env`, ganti `SECRET_KEY` dengan kode acak
   (bisa generate pakai `python -c "import secrets; print(secrets.token_hex(32))"`).
   Untuk email stok kritis, isi `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
   `SMTP_PASSWORD`, dan `SMTP_FROM`. TLS umumnya memakai port 587
   (`SMTP_USE_TLS=true`, `SMTP_USE_SSL=false`); SSL dapat memakai port 465
   (`SMTP_USE_TLS=false`, `SMTP_USE_SSL=true`). Tanpa konfigurasi SMTP,
   transaksi tetap tersimpan dan aplikasi menampilkan peringatan bahwa email gagal dikirim.
3. Isi data contoh (akun admin demo + produk):
   ```
   python seed.py
   ```
   Login demo: `admin@stokpintar.com` / `admin12345`
   *(ganti password ini kalau mau dipakai beneran, ini cuma buat demo)*
   Admin pertama yang mendaftar menjadi admin. Setelah masuk, admin dapat membuat
   akun staf melalui menu **Pengguna**.
4. Jalankan:
   ```
   python app.py
   ```
5. Buka `http://127.0.0.1:5000` di browser

## Deploy demo gratis: Render + Neon PostgreSQL

1. Buat database PostgreSQL di Neon, lalu salin connection string pooled dari dashboard Neon.
2. Buat repo GitHub private dan push kode aplikasi ke branch `main`.
3. Hubungkan akun GitHub ke Render, pilih **New > Blueprint**, lalu pilih repo ini.
   Render membaca `render.yaml` dan membuat web service gratis.
4. Saat setup service diminta `DATABASE_URL`, isi connection string Neon.
   Jangan masukkan connection string ke file yang di-commit.
5. Setelah deploy selesai, buka URL Render. Akun admin pertama bisa dibuat melalui halaman registrasi.

Paket gratis Render ditujukan untuk demo: web service dapat tidur saat tidak aktif,
dan filesystem-nya sementara. Karena itu database wajib memakai PostgreSQL eksternal,
bukan SQLite di server. Render dan Neon dapat mengubah kuota atau ketentuan paket gratis;
cek dashboard kedua layanan sebelum deploy. Isi `SECRET_KEY` dibuat otomatis oleh konfigurasi
Blueprint. Jika notifikasi email diinginkan, tambahkan variabel SMTP dari `.env.example`
melalui pengaturan Environment Render.

### Menjalankan tes

Jalankan dari folder proyek:

```powershell
python -m unittest discover -s tests -v
```


