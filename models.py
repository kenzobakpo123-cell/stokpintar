"""
models.py
=========
Definisi model database (lapisan "Model"). Dipisah dari app.py supaya
struktur project lebih rapi dan mirip pemisahan tanggung jawab ala
MVVM/MVC: Model (models.py) - Logic (algorithms.py) - Controller/View
(app.py + templates/).
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone

db = SQLAlchemy()


def utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(
        db.String(20), nullable=False, default='admin', server_default='admin'
    )


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Float, nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    min_stock = db.Column(db.Integer, nullable=False, default=5)
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    transactions = db.relationship(
        'Transaction', backref='product', lazy=True,
        cascade='all, delete-orphan'
    )


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'in' atau 'out'
    quantity = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(200))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    user = db.relationship('User', backref='transactions')


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    contact_name = db.Column(db.String(100))
    email = db.Column(db.String(150))
    phone = db.Column(db.String(40))
    address = db.Column(db.String(250))
    created_at = db.Column(db.DateTime, default=utc_now_naive)

    purchase_orders = db.relationship('PurchaseOrder', back_populates='supplier')


class PurchaseOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default='draft', server_default='draft'
    )
    note = db.Column(db.String(200))
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    received_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    received_at = db.Column(db.DateTime)

    supplier = db.relationship('Supplier', back_populates='purchase_orders')
    product = db.relationship('Product')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    received_by = db.relationship('User', foreign_keys=[received_by_id])
