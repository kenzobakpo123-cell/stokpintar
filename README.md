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

## Deploy gratis: PythonAnywhere

PythonAnywhere Beginner menyediakan satu web app dengan alamat
`username.pythonanywhere.com`. Username tidak bisa diganti setelah akun dibuat,
jadi coba gunakan `stokpintar` saat mendaftar jika masih tersedia; alternatifnya
`stokpintarapp`. Paket gratis tidak memakai custom domain dan akses internet
keluar dibatasi.

1. Buat akun Beginner di [PythonAnywhere](https://www.pythonanywhere.com/registration/register/beginner/).
2. Buka **Consoles > Bash** dan clone repo:
   ```
   git clone https://github.com/kenzobakpo123-cell/stokpintar.git
   ```
   Jika repo GitHub diatur private, gunakan mekanisme akses GitHub yang tersedia
   di akun hosting atau unggah file proyek tanpa `.env`, `venv`, dan database lokal.
3. Buat virtual environment dan pasang dependency:
   ```
   mkvirtualenv --python=/usr/bin/python3.13 stokpintar-venv
   cd ~/stokpintar
   pip install -r requirements.txt
   ```
4. Di PythonAnywhere, buka **Web > Add a new web app > Manual configuration**
   dan pilih Python 3.13. Di bagian **Virtualenv**, isi
   `/home/USERNAME/.virtualenvs/stokpintar-venv` (ganti `USERNAME` dengan username
   PythonAnywhere).
5. Buat file `~/stokpintar/.env` melalui halaman **Files**. Isi dengan `SECRET_KEY`
   acak dan `DATABASE_URL=sqlite:///stokpintar.db`. Jangan unggah `.env` ke GitHub.
   SQLite disimpan di akun hosting; jangan letakkan database di direktori sementara.
6. Di halaman Web, buka file WSGI lalu ganti bagian Flask dengan:
   ```
   import sys
   path = '/home/USERNAME/stokpintar'
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import app as application
   ```
   Ganti `USERNAME`, lalu tekan **Reload** di halaman Web.
7. Buka `https://USERNAME.pythonanywhere.com` dan daftar sebagai admin pertama.

Gunakan **Python 3.13** untuk virtual environment dan konfigurasi web app.
Pada paket gratis, koneksi SMTP keluar dapat terhalang pembatasan jaringan;
fitur stok tetap berjalan, tetapi notifikasi email mungkin tidak tersedia.
Paket, kuota, dan kebijakan layanan dapat berubah—cek informasi terbaru
PythonAnywhere sebelum deploy.

### Menjalankan tes

Jalankan dari folder proyek:

```powershell
python -m unittest discover -s tests -v
```


