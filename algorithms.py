"""
algorithms.py
=================
Modul ini sengaja dipisah dari route/controller (app.py) supaya logika
algoritma murni (tanpa dependensi Flask/DB) bisa dijelaskan & diuji sendiri
saat wawancara. Semua fungsi di sini ditulis manual (bukan cuma panggil
sorted()/bisect bawaan Python) supaya kelihatan pemahaman algoritmanya,
bukan cuma pemahaman library.

Algoritma yang dipakai di project StokPintar:
1. merge_sort        -> O(n log n), dipakai buat ranking produk paling
                         urgent untuk di-restock (dashboard).
2. binary_search      -> O(log n), dipakai buat pencarian produk cepat
                         berdasarkan SKU setelah data diurutkan.
3. calculate_priority_score -> menghitung skor urgensi restock tiap produk.
4. forecast_stockout_days   -> prediksi berapa hari lagi stok habis,
                         pakai moving average dari transaksi keluar.
"""

from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# 1. MERGE SORT
# ---------------------------------------------------------------------------
def merge_sort(items, key, reverse=False):
    """
    Mengurutkan list `items` berdasarkan fungsi `key(item) -> angka`.
    Implementasi manual merge sort, kompleksitas O(n log n).

    `reverse=True` artinya urut dari besar ke kecil (dipakai untuk
    menaruh produk paling urgent di atas).
    """
    if len(items) <= 1:
        return items[:]

    mid = len(items) // 2
    left = merge_sort(items[:mid], key, reverse)
    right = merge_sort(items[mid:], key, reverse)
    return _merge(left, right, key, reverse)


def _merge(left, right, key, reverse):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        left_val = key(left[i])
        right_val = key(right[j])
        take_left = left_val >= right_val if reverse else left_val <= right_val
        if take_left:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result


# ---------------------------------------------------------------------------
# 2. BINARY SEARCH
# ---------------------------------------------------------------------------
def binary_search_by_sku(sorted_products, sku):
    """
    Mencari produk berdasarkan SKU di dalam list yang SUDAH terurut
    berdasarkan SKU (ascending). Kompleksitas O(log n).

    Mengembalikan objek produk kalau ketemu, atau None kalau tidak ada.
    """
    low = 0
    high = len(sorted_products) - 1

    while low <= high:
        mid = (low + high) // 2
        mid_sku = sorted_products[mid].sku

        if mid_sku == sku:
            return sorted_products[mid]
        elif mid_sku < sku:
            low = mid + 1
        else:
            high = mid - 1

    return None


# ---------------------------------------------------------------------------
# 3. SKOR PRIORITAS RESTOCK
# ---------------------------------------------------------------------------
def calculate_priority_score(product, avg_daily_out):
    """
    Semakin TINGGI skor, semakin URGENT produk itu harus di-restock.

    Logika:
    - Kalau stok sudah di bawah/nol -> skor otomatis sangat tinggi (999+).
    - Kalau tidak, skor dihitung dari seberapa dekat stok sekarang
      ke batas minimum, dibagi rata-rata penjualan harian (kalau produk
      itu laku cepat, dia lebih urgent walau stoknya masih di atas minimum).
    """
    if product.stock <= 0:
        return 999 + (product.min_stock - product.stock)

    if product.stock <= product.min_stock:
        base_score = (product.min_stock - product.stock + 1) * 10
    else:
        base_score = max(0, product.min_stock - (product.stock - product.min_stock))

    velocity_factor = avg_daily_out if avg_daily_out > 0 else 0.1
    return round(base_score * velocity_factor, 2)


# ---------------------------------------------------------------------------
# 4. FORECAST HARI SAMPAI STOK HABIS (Moving Average)
# ---------------------------------------------------------------------------
def calculate_avg_daily_out(transactions, window_days=14):
    """
    Menghitung rata-rata jumlah barang KELUAR per hari dalam
    `window_days` terakhir, dari list transaksi (sudah difilter utk 1 produk).
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=window_days)
    recent_out = [
        t.quantity for t in transactions
        if t.type == 'out' and t.created_at >= cutoff
    ]
    if not recent_out:
        return 0.0
    return round(sum(recent_out) / window_days, 2)


def forecast_stockout_days(current_stock, avg_daily_out):
    """
    Prediksi berapa hari lagi stok akan habis, berdasarkan rata-rata
    keluar harian. Mengembalikan None kalau tidak bisa diprediksi
    (penjualan 0, jadi dianggap aman/stabil).
    """
    if avg_daily_out <= 0:
        return None
    return round(current_stock / avg_daily_out, 1)
