"""
app.py
======
Lapisan Controller/Route. Menghubungkan Model (models.py) dan Logika
Algoritma (algorithms.py) ke tampilan (templates/, pakai Bootstrap 5).

Fitur:
- Login & role admin/staf (Flask-Login, rate limit, CSRF, password hash)
- CRUD Produk
- Catat transaksi stok masuk/keluar
- Dashboard: ranking urgensi restock (merge sort custom) + forecast stockout
- Pencarian produk by SKU pakai binary search custom
- Grafik transaksi stok, ekspor laporan, dan email stok kritis
"""

import io
import os
import re
import html
import csv
import logging
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps

from flask import (
    Flask, abort, render_template, redirect, url_for, request, flash, send_file
)
from flask_login import (
    LoginManager, login_user, login_required, logout_user, current_user
)
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from models import db, User, Product, Transaction, Supplier, PurchaseOrder
from algorithms import (
    merge_sort, binary_search_by_sku, calculate_priority_score,
    calculate_avg_daily_out, forecast_stockout_days
)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-ganti-ini')
database_url = os.getenv('DATABASE_URL', 'sqlite:///stokpintar.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Secure cookie dinyalakan otomatis kalau dideploy (bukan di localhost http)
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])

CATEGORIES = ['Elektronik', 'Alat Tulis', 'Makanan & Minuman', 'Peralatan', 'Lainnya']
EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MAX_DB_INTEGER = 2_147_483_647
logger = logging.getLogger(__name__)


def utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return view(*args, **kwargs)
    return wrapped_view


def safe_spreadsheet_text(value):
    text_value = str(value or '')
    if text_value.startswith(('=', '+', '-', '@', '\t', '\r')):
        return "'" + text_value
    return text_value


def send_critical_stock_alert(product):
    smtp_host = os.getenv('SMTP_HOST')
    sender = os.getenv('SMTP_FROM') or os.getenv('SMTP_USER')
    admins = User.query.filter_by(role='admin').all()
    recipients = [user.email for user in admins]

    if not smtp_host or not sender or not recipients:
        return False, 'Konfigurasi SMTP belum lengkap atau email admin belum tersedia.'

    username = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASSWORD')
    use_ssl = os.getenv('SMTP_USE_SSL', 'false').lower() == 'true'
    use_tls = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'

    try:
        port = int(os.getenv('SMTP_PORT', '587'))
        message = EmailMessage()
        message['Subject'] = f'[StokPintar] Stok kritis: {product.name}'
        message['From'] = sender
        message['To'] = ', '.join(recipients)
        message.set_content(
            f'Produk {product.name} (SKU {product.sku}) mencapai batas stok kritis.\n'
            f'Stok saat ini: {product.stock}\n'
            f'Batas minimum: {product.min_stock}\n'
        )

        if use_ssl:
            with smtplib.SMTP_SSL(
                smtp_host, port, timeout=10, context=ssl.create_default_context()
            ) as smtp:
                if username:
                    smtp.login(username, password or '')
                smtp.send_message(message)
        else:
            with smtplib.SMTP(smtp_host, port, timeout=10) as smtp:
                if use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                if username:
                    smtp.login(username, password or '')
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError):
        logger.exception('Gagal mengirim notifikasi stok kritis.')
        return False, 'Email notifikasi gagal dikirim. Periksa konfigurasi SMTP.'

    return True, None


def notify_if_stock_became_critical(product, previous_stock):
    if previous_stock > product.min_stock and product.stock <= product.min_stock:
        return send_critical_stock_alert(product)
    return None


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


# =====================================================================
# AUTH
# =====================================================================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Email atau password salah.', 'danger')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def register():
    """Registrasi publik hanya untuk akun admin pertama."""
    if User.query.count() > 0:
        flash('Registrasi ditutup. Hubungi admin yang sudah terdaftar.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        if not name or not email or not password:
            flash('Semua kolom wajib diisi.', 'danger')
            return redirect(url_for('register'))
        if not EMAIL_PATTERN.match(email):
            flash('Format email tidak valid.', 'danger')
            return redirect(url_for('register'))
        if len(password) < 8:
            flash('Password minimal 8 karakter.', 'danger')
            return redirect(url_for('register'))

        user = User(name=name, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash('Akun admin berhasil dibuat, silakan login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# =====================================================================
# DASHBOARD (pakai algoritma merge sort + forecast)
# =====================================================================
@app.route('/dashboard')
@login_required
def dashboard():
    products = Product.query.all()

    enriched = []
    for p in products:
        avg_out = calculate_avg_daily_out(p.transactions)
        score = calculate_priority_score(p, avg_out)
        days_left = forecast_stockout_days(p.stock, avg_out)
        enriched.append({
            'product': p,
            'avg_out': avg_out,
            'score': score,
            'days_left': days_left,
        })

    # Urutkan dari paling urgent (skor tertinggi) pakai merge sort custom
    ranked = merge_sort(enriched, key=lambda x: x['score'], reverse=True)

    total_products = len(products)
    total_stock_value = sum(p.price * p.stock for p in products)
    critical_count = sum(1 for p in products if p.stock <= p.min_stock)
    first_day = utc_now_naive().date() - timedelta(days=13)
    transactions = Transaction.query.filter(
        Transaction.created_at >= datetime.combine(first_day, datetime.min.time())
    ).all()
    daily_totals = {}
    for transaction in transactions:
        day = transaction.created_at.date()
        totals = daily_totals.setdefault(day, {'in': 0, 'out': 0})
        if transaction.type in totals:
            totals[transaction.type] += transaction.quantity
    chart_labels = [
        (first_day + timedelta(days=offset)).strftime('%d %b')
        for offset in range(14)
    ]
    chart_in = [
        daily_totals.get(first_day + timedelta(days=offset), {}).get('in', 0)
        for offset in range(14)
    ]
    chart_out = [
        daily_totals.get(first_day + timedelta(days=offset), {}).get('out', 0)
        for offset in range(14)
    ]

    return render_template(
        'dashboard.html',
        ranked=ranked[:10],
        total_products=total_products,
        total_stock_value=total_stock_value,
        critical_count=critical_count,
        chart_labels=chart_labels,
        chart_in=chart_in,
        chart_out=chart_out,
    )


@app.route('/restock')
@login_required
def restock():
    products = Product.query.filter(
        Product.stock <= Product.min_stock
    ).order_by(Product.stock.asc(), Product.name.asc()).all()
    rows = [
        {
            'product': product,
            'suggested_quantity': max(0, product.min_stock - product.stock),
        }
        for product in products
    ]
    return render_template('restock.html', rows=rows)


@app.route('/restock.csv')
@login_required
def export_restock_csv():
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow([
        'SKU', 'Nama Produk', 'Kategori', 'Stok Saat Ini',
        'Stok Minimum', 'Jumlah untuk mencapai stok minimum',
    ])
    products = Product.query.filter(
        Product.stock <= Product.min_stock
    ).order_by(Product.stock.asc(), Product.name.asc()).all()
    for product in products:
        writer.writerow([
            safe_spreadsheet_text(product.sku),
            safe_spreadsheet_text(product.name),
            safe_spreadsheet_text(product.category),
            product.stock,
            product.min_stock,
            max(0, product.min_stock - product.stock),
        ])

    return app.response_class(
        '\ufeff' + output.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename=daftar-restock.csv'},
    )


@app.route('/stocktake', methods=['GET', 'POST'])
@login_required
def stocktake():
    if request.method == 'POST':
        product_id = request.form.get('product_id', type=int)
        product = (
            Product.query.filter_by(id=product_id).with_for_update().first()
            if product_id else None
        )
        reason = (request.form.get('reason') or '').strip()
        try:
            counted_stock = int(request.form.get('counted_stock') or -1)
        except ValueError:
            counted_stock = -1

        if product is None:
            flash('Pilih produk yang valid.', 'danger')
        elif counted_stock < 0:
            flash('Hasil stok opname harus berupa angka nol atau lebih.', 'danger')
        elif counted_stock > MAX_DB_INTEGER:
            flash('Hasil stok opname melebihi batas maksimum sistem.', 'danger')
        elif not reason:
            flash('Alasan penyesuaian wajib diisi.', 'danger')
        elif len(reason) > 160:
            flash('Alasan maksimal 160 karakter.', 'danger')
        else:
            previous_stock = product.stock
            difference = counted_stock - previous_stock
            product.stock = counted_stock
            db.session.add(Transaction(
                product_id=product.id,
                type='adjustment',
                quantity=difference,
                note=f'Stok opname: {reason}',
                user_id=current_user.id,
            ))
            db.session.commit()
            notification = notify_if_stock_became_critical(product, previous_stock)
            success_message = (
                f'Stok opname {product.name} tersimpan. '
                f'Selisih stok: {difference:+d}.'
            )
            if notification is None or notification[0]:
                flash(success_message, 'success')
            else:
                flash(
                    success_message + ' Namun email peringatan gagal dikirim.',
                    'warning',
                )
            return redirect(url_for('product_detail', product_id=product.id))

    products = Product.query.order_by(Product.name.asc()).all()
    return render_template('stocktake.html', products=products)


@app.route('/suppliers', methods=['GET', 'POST'])
@login_required
@admin_required
def suppliers():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        contact_name = (request.form.get('contact_name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        phone = (request.form.get('phone') or '').strip()
        address = (request.form.get('address') or '').strip()

        if not name:
            flash('Nama supplier wajib diisi.', 'danger')
        elif Supplier.query.filter_by(name=name).first():
            flash('Nama supplier tersebut sudah terdaftar.', 'danger')
        elif email and not EMAIL_PATTERN.match(email):
            flash('Format email supplier tidak valid.', 'danger')
        elif (
            len(name) > 150 or len(contact_name) > 100 or len(email) > 150
            or len(phone) > 40 or len(address) > 250
        ):
            flash('Ada data supplier yang melebihi panjang maksimum.', 'danger')
        else:
            db.session.add(Supplier(
                name=name,
                contact_name=contact_name or None,
                email=email or None,
                phone=phone or None,
                address=address or None,
            ))
            db.session.commit()
            flash('Supplier berhasil ditambahkan.', 'success')
            return redirect(url_for('suppliers'))

    supplier_list = Supplier.query.order_by(Supplier.name.asc()).all()
    return render_template('suppliers.html', suppliers=supplier_list)


@app.route('/purchase-orders', methods=['GET', 'POST'])
@login_required
def purchase_orders():
    if request.method == 'POST':
        if current_user.role != 'admin':
            abort(403)
        supplier = db.session.get(Supplier, request.form.get('supplier_id', type=int))
        product = db.session.get(Product, request.form.get('product_id', type=int))
        note = (request.form.get('note') or '').strip()
        status = request.form.get('status', 'draft')
        try:
            quantity = int(request.form.get('quantity') or 0)
        except ValueError:
            quantity = 0

        if supplier is None or product is None:
            flash('Pilih supplier dan produk yang valid.', 'danger')
        elif quantity <= 0 or quantity > MAX_DB_INTEGER:
            flash('Jumlah pesanan harus antara 1 dan batas maksimum sistem.', 'danger')
        elif len(note) > 200:
            flash('Catatan maksimal 200 karakter.', 'danger')
        elif status not in ('draft', 'ordered'):
            flash('Status awal pesanan tidak valid.', 'danger')
        else:
            order = PurchaseOrder(
                supplier_id=supplier.id,
                product_id=product.id,
                quantity=quantity,
                status=status,
                note=note or None,
                created_by_id=current_user.id,
            )
            db.session.add(order)
            db.session.commit()
            flash('Pesanan pembelian berhasil dibuat.', 'success')
            return redirect(url_for('purchase_orders'))

    orders = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()
    return render_template(
        'purchase_orders.html',
        orders=orders,
        suppliers=Supplier.query.order_by(Supplier.name.asc()).all(),
        products=Product.query.order_by(Product.name.asc()).all(),
    )


@app.route('/purchase-orders/<int:order_id>/status', methods=['POST'])
@login_required
def purchase_order_status(order_id):
    order = PurchaseOrder.query.filter_by(id=order_id).with_for_update().first_or_404()
    next_status = request.form.get('status')
    transitions = {
        'draft': {'ordered', 'cancelled'},
        'ordered': {'received', 'cancelled'},
    }

    if next_status not in transitions.get(order.status, set()):
        abort(400, description='Perubahan status pesanan tidak valid.')
    if next_status != 'received' and current_user.role != 'admin':
        abort(403)

    if next_status == 'received':
        product = Product.query.filter_by(
            id=order.product_id
        ).with_for_update().one()
        if product.stock > MAX_DB_INTEGER - order.quantity:
            flash('Stok akan melebihi batas maksimum sistem.', 'danger')
            return redirect(url_for('purchase_orders'))
        product.stock += order.quantity
        order.received_by_id = current_user.id
        order.received_at = utc_now_naive()
        db.session.add(Transaction(
            product_id=order.product_id,
            type='in',
            quantity=order.quantity,
            note=f'Penerimaan pesanan #{order.id}',
            user_id=current_user.id,
        ))
        order.status = next_status
        db.session.commit()
        flash('Pesanan diterima dan stok berhasil diperbarui.', 'success')
    else:
        order.status = next_status
        db.session.commit()
        flash('Status pesanan berhasil diperbarui.', 'success')

    return redirect(url_for('purchase_orders'))


# =====================================================================
# PRODUK (CRUD)
# =====================================================================
@app.route('/products')
@login_required
def products():
    query = (request.args.get('q') or '').strip()
    all_products = Product.query.order_by(Product.sku.asc()).all()

    if query:
        # Kalau query persis match format SKU, pakai binary search (O(log n)).
        # Kalau bukan, fallback pencarian nama (linear, karena memang
        # harus cek substring di semua produk).
        exact = binary_search_by_sku(all_products, query.upper())
        if exact:
            result = [exact]
        else:
            result = [p for p in all_products if query.lower() in p.name.lower()]
    else:
        result = all_products

    return render_template('products.html', products=result, query=query)


@app.route('/products/new', methods=['GET', 'POST'])
@login_required
@admin_required
def product_new():
    if request.method == 'POST':
        sku = (request.form.get('sku') or '').strip().upper()
        name = (request.form.get('name') or '').strip()
        category = request.form.get('category')
        price = request.form.get('price') or 0
        stock = request.form.get('stock') or 0
        min_stock = request.form.get('min_stock') or 5

        if not sku or not name:
            flash('SKU dan nama produk wajib diisi.', 'danger')
            return redirect(url_for('product_new'))

        if Product.query.filter_by(sku=sku).first():
            flash('SKU sudah dipakai produk lain.', 'danger')
            return redirect(url_for('product_new'))

        try:
            price = float(price)
            stock = int(stock)
            min_stock = int(min_stock)
        except ValueError:
            flash('Harga/stok harus berupa angka.', 'danger')
            return redirect(url_for('product_new'))

        product = Product(
            sku=sku, name=name, category=category,
            price=price, stock=stock, min_stock=min_stock
        )
        db.session.add(product)
        db.session.commit()
        flash('Produk berhasil ditambahkan.', 'success')
        return redirect(url_for('products'))

    return render_template('product_form.html', product=None, categories=CATEGORIES)


@app.route('/products/<int:product_id>')
@login_required
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    avg_out = calculate_avg_daily_out(product.transactions)
    days_left = forecast_stockout_days(product.stock, avg_out)
    history = sorted(product.transactions, key=lambda t: t.created_at, reverse=True)
    return render_template(
        'product_detail.html', product=product,
        avg_out=avg_out, days_left=days_left, history=history
    )


@app.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':
        product.name = (request.form.get('name') or '').strip()
        product.category = request.form.get('category')
        try:
            product.price = float(request.form.get('price') or 0)
            product.min_stock = int(request.form.get('min_stock') or 5)
        except ValueError:
            flash('Harga/stok minimum harus berupa angka.', 'danger')
            return redirect(url_for('product_edit', product_id=product.id))

        db.session.commit()
        flash('Produk berhasil diperbarui.', 'success')
        return redirect(url_for('product_detail', product_id=product.id))

    return render_template('product_form.html', product=product, categories=CATEGORIES)


@app.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
@admin_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Produk berhasil dihapus.', 'success')
    return redirect(url_for('products'))


# =====================================================================
# TRANSAKSI STOK
# =====================================================================
@app.route('/products/<int:product_id>/transaction', methods=['POST'])
@login_required
def transaction_new(product_id):
    product = Product.query.filter_by(id=product_id).with_for_update().first_or_404()
    previous_stock = product.stock
    t_type = request.form.get('type')
    note = (request.form.get('note') or '').strip()

    try:
        quantity = int(request.form.get('quantity') or 0)
    except ValueError:
        quantity = 0

    if quantity <= 0 or quantity > MAX_DB_INTEGER or t_type not in ('in', 'out'):
        flash('Jumlah tidak valid.', 'danger')
        return redirect(url_for('product_detail', product_id=product.id))

    if t_type == 'in' and product.stock > MAX_DB_INTEGER - quantity:
        flash('Stok akan melebihi batas maksimum sistem.', 'danger')
        return redirect(url_for('product_detail', product_id=product.id))
    if t_type == 'out' and quantity > product.stock:
        flash('Stok tidak cukup untuk transaksi keluar ini.', 'danger')
        return redirect(url_for('product_detail', product_id=product.id))
    if len(note) > 200:
        flash('Catatan maksimal 200 karakter.', 'danger')
        return redirect(url_for('product_detail', product_id=product.id))

    product.stock += quantity if t_type == 'in' else -quantity
    db.session.add(Transaction(
        product_id=product.id,
        type=t_type,
        quantity=quantity,
        note=note or None,
        user_id=current_user.id,
    ))
    db.session.commit()
    notification = notify_if_stock_became_critical(product, previous_stock)
    if notification is not None:
        sent, error = notification
        flash(
            'Transaksi berhasil dicatat.' if sent else
            'Transaksi berhasil dicatat, tetapi ' + error,
            'success' if sent else 'warning',
        )
    else:
        flash('Transaksi berhasil dicatat.', 'success')
    return redirect(url_for('product_detail', product_id=product.id))


# =====================================================================
# MANAJEMEN AKUN
# =====================================================================
@app.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def users():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        if not name or not email or not password:
            flash('Semua kolom wajib diisi.', 'danger')
        elif not EMAIL_PATTERN.match(email):
            flash('Format email tidak valid.', 'danger')
        elif len(password) < 8:
            flash('Password minimal 8 karakter.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Email sudah terdaftar.', 'danger')
        else:
            db.session.add(User(
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
                role='staff',
            ))
            db.session.commit()
            flash('Akun staf berhasil dibuat.', 'success')
            return redirect(url_for('users'))

    staff_users = User.query.order_by(User.name.asc()).all()
    return render_template('users.html', users=staff_users)


# =====================================================================
# EKSPOR LAPORAN
# =====================================================================
@app.route('/reports.xlsx')
@login_required
def export_excel():
    workbook = Workbook()
    inventory = workbook.active
    inventory.title = 'Inventaris'
    inventory.append([
        'SKU', 'Nama Produk', 'Kategori', 'Harga (Rp)', 'Stok',
        'Stok Minimum', 'Status', 'Nilai Stok (Rp)',
    ])
    products = Product.query.order_by(Product.sku.asc()).all()
    for product in products:
        inventory.append([
            safe_spreadsheet_text(product.sku),
            safe_spreadsheet_text(product.name),
            safe_spreadsheet_text(product.category),
            product.price,
            product.stock,
            product.min_stock,
            'Kritis' if product.stock <= product.min_stock else 'Aman',
            product.price * product.stock,
        ])

    transactions_sheet = workbook.create_sheet('Transaksi')
    transactions_sheet.append([
        'Tanggal', 'SKU', 'Nama Produk', 'Jenis', 'Jumlah', 'Dicatat oleh', 'Catatan',
    ])
    transaction_rows = (
        db.session.query(Transaction, Product)
        .join(Product, Transaction.product_id == Product.id)
        .order_by(Transaction.created_at.desc())
        .all()
    )
    for transaction, product in transaction_rows:
        transactions_sheet.append([
            transaction.created_at.strftime('%Y-%m-%d %H:%M'),
            safe_spreadsheet_text(product.sku),
            safe_spreadsheet_text(product.name),
            (
                'Masuk' if transaction.type == 'in' else
                'Keluar' if transaction.type == 'out' else 'Stok opname'
            ),
            transaction.quantity,
            safe_spreadsheet_text(transaction.user.name if transaction.user else ''),
            safe_spreadsheet_text(transaction.note),
        ])

    for sheet in workbook.worksheets:
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='243B53')
        for column in sheet.columns:
            width = max(
                len(str(cell.value or '')) for cell in column
            )
            sheet.column_dimensions[column[0].column_letter].width = min(width + 2, 40)

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='laporan-stokpintar.xlsx',
    )


@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')


@app.route('/reports.pdf')
@login_required
def export_pdf():
    products = Product.query.order_by(Product.sku.asc()).all()
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=landscape(A4),
        rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle', parent=styles['Title'], alignment=TA_CENTER
    )
    rows = [[
        'SKU', 'Nama Produk', 'Kategori', 'Harga (Rp)', 'Stok',
        'Min.', 'Status', 'Nilai Stok (Rp)',
    ]]
    for product in products:
        rows.append([
            product.sku,
            Paragraph(html.escape(product.name), styles['BodyText']),
            html.escape(product.category),
            f'{product.price:,.0f}',
            str(product.stock),
            str(product.min_stock),
            'Kritis' if product.stock <= product.min_stock else 'Aman',
            f'{product.price * product.stock:,.0f}',
        ])

    table = Table(
        rows,
        repeatRows=1,
        colWidths=[25 * mm, 48 * mm, 35 * mm, 28 * mm, 15 * mm, 15 * mm, 20 * mm, 34 * mm],
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#243b53')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#d9e2ec')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [
            colors.white, colors.HexColor('#f0f4f8'),
        ]),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    document.build([
        Paragraph('Laporan Inventaris StokPintar', title_style),
        Paragraph(
            f'Dibuat pada {utc_now_naive().strftime("%d %B %Y %H:%M")} UTC',
            styles['Normal'],
        ),
        Spacer(1, 8 * mm),
        table,
    ])
    output.seek(0)
    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='laporan-stokpintar.pdf',
    )


with app.app_context():
    db.create_all()
    user_columns = {
        column['name'] for column in inspect(db.engine).get_columns('user')
    }
    if 'role' not in user_columns:
        db.session.execute(text(
            'ALTER TABLE "user" ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT \'admin\''
        ))
        db.session.commit()
    transaction_columns = {
        column['name'] for column in inspect(db.engine).get_columns('transaction')
    }
    if 'user_id' not in transaction_columns:
        db.session.execute(text(
            'ALTER TABLE "transaction" ADD COLUMN user_id INTEGER REFERENCES "user"(id)'
        ))
        db.session.commit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
