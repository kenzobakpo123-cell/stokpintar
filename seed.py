"""
seed.py
-------
Jalankan sekali: `python seed.py`
Membuat 1 akun admin demo + beberapa produk & riwayat transaksi palsu,
supaya dashboard langsung kelihatan "hidup" waktu di-demo/screenshot
buat portofolio (nggak perlu input manual satu-satu).
"""

import random
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app import app
from models import db, User, Product, Transaction

ADMIN_EMAIL = "admin@stokpintar.com"
ADMIN_PASSWORD = "admin12345"

PRODUCTS = [
    ("ELK-001", "Mouse Wireless Logitech", "Elektronik", 150000, 40, 10),
    ("ELK-002", "Keyboard Mekanik RGB", "Elektronik", 450000, 8, 10),
    ("ELK-003", "Kabel HDMI 2m", "Elektronik", 45000, 60, 15),
    ("ATK-001", "Pulpen Gel Hitam (lusin)", "Alat Tulis", 24000, 5, 20),
    ("ATK-002", "Buku Tulis 58 Lembar", "Alat Tulis", 6000, 120, 30),
    ("MKN-001", "Kopi Sachet (box isi 20)", "Makanan & Minuman", 32000, 3, 15),
    ("MKN-002", "Air Mineral 600ml (dus)", "Makanan & Minuman", 55000, 25, 10),
    ("PRL-001", "Stapler Besar", "Peralatan", 38000, 12, 5),
    ("PRL-002", "Gunting Kertas", "Peralatan", 15000, 2, 8),
    ("LN-001", "Hand Sanitizer 500ml", "Lainnya", 28000, 18, 10),
]


def run():
    with app.app_context():
        db.create_all()

        if User.query.filter_by(email=ADMIN_EMAIL).first():
            print("Data demo sudah ada, seed dilewati.")
            return

        admin = User(
            name="Admin Demo",
            email=ADMIN_EMAIL,
            password_hash=generate_password_hash(ADMIN_PASSWORD),
        )
        db.session.add(admin)

        for sku, name, category, price, stock, min_stock in PRODUCTS:
            product = Product(
                sku=sku, name=name, category=category,
                price=price, stock=stock, min_stock=min_stock,
            )
            db.session.add(product)
            db.session.flush()  # biar product.id kebentuk

            # Bikin riwayat transaksi 'keluar' acak 14 hari terakhir,
            # supaya algoritma forecast punya data buat dihitung.
            for day_ago in range(14):
                if random.random() < 0.5:
                    continue
                qty = random.randint(1, max(1, stock // 10) or 1)
                db.session.add(Transaction(
                    product_id=product.id,
                    type='out',
                    quantity=qty,
                    note='Penjualan harian',
                    created_at=(
                        datetime.now(timezone.utc).replace(tzinfo=None)
                        - timedelta(days=day_ago)
                    ),
                ))

        db.session.commit()
        print("Seed berhasil!")
        print(f"Login demo -> email: {ADMIN_EMAIL} | password: {ADMIN_PASSWORD}")


if __name__ == "__main__":
    run()
