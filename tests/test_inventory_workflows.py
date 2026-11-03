import os
import unittest
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'test-secret-key'

from werkzeug.security import generate_password_hash

from app import app
from models import db, Product, PurchaseOrder, Supplier, Transaction, User


class InventoryWorkflowTests(unittest.TestCase):
    next_test_ip = 1

    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
        )
        with app.app_context():
            db.drop_all()
            db.create_all()
            self.admin = User(
                name='Admin Test',
                email='admin@test.local',
                password_hash=generate_password_hash('password123'),
                role='admin',
            )
            self.staff = User(
                name='Staf Test',
                email='staff@test.local',
                password_hash=generate_password_hash('password123'),
                role='staff',
            )
            self.product = Product(
                sku='TEST-001',
                name='Produk Test',
                category='Lainnya',
                price=1000,
                stock=12,
                min_stock=5,
            )
            self.supplier = Supplier(name='Supplier Test')
            db.session.add_all([self.admin, self.staff, self.product, self.supplier])
            db.session.commit()
            self.product_id = self.product.id
            self.supplier_id = self.supplier.id
            self.admin_id = self.admin.id
            self.staff_id = self.staff.id
        self.client = app.test_client()
        self.client.environ_base['REMOTE_ADDR'] = (
            f'192.0.2.{self.next_test_ip}'
        )
        type(self).next_test_ip += 1

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def login_as(self, email):
        response = self.client.post('/login', data={
            'email': email,
            'password': 'password123',
        })
        self.assertEqual(response.status_code, 302)

    def test_stock_transaction_records_the_authenticated_user(self):
        self.login_as('staff@test.local')

        response = self.client.post(
            f'/products/{self.product_id}/transaction',
            data={'type': 'out', 'quantity': '3', 'note': 'Penjualan'},
        )

        self.assertEqual(response.status_code, 302)
        with app.app_context():
            product = db.session.get(Product, self.product_id)
            transaction = Transaction.query.one()
            self.assertEqual(product.stock, 9)
            self.assertEqual(transaction.user_id, self.staff_id)
            self.assertEqual(transaction.type, 'out')

    def test_stocktake_adjusts_stock_and_records_reason_and_actor(self):
        self.login_as('staff@test.local')

        response = self.client.post('/stocktake', data={
            'product_id': str(self.product_id),
            'counted_stock': '8',
            'reason': 'Hitung fisik rak A',
        })

        self.assertEqual(response.status_code, 302)
        with app.app_context():
            product = db.session.get(Product, self.product_id)
            transaction = Transaction.query.one()
            self.assertEqual(product.stock, 8)
            self.assertEqual(transaction.type, 'adjustment')
            self.assertEqual(transaction.quantity, -4)
            self.assertEqual(transaction.user_id, self.staff_id)
            self.assertIn('Hitung fisik rak A', transaction.note)

    def test_stocktake_rejects_negative_count_without_changing_stock(self):
        self.login_as('staff@test.local')

        response = self.client.post('/stocktake', data={
            'product_id': str(self.product_id),
            'counted_stock': '-1',
            'reason': 'Hitung ulang',
        })

        self.assertEqual(response.status_code, 200)
        with app.app_context():
            self.assertEqual(db.session.get(Product, self.product_id).stock, 12)
            self.assertEqual(Transaction.query.count(), 0)

    @patch('app.send_critical_stock_alert', return_value=(True, None))
    def test_stocktake_notifies_when_stock_becomes_critical(self, send_alert):
        self.login_as('staff@test.local')

        response = self.client.post('/stocktake', data={
            'product_id': str(self.product_id),
            'counted_stock': '5',
            'reason': 'Hitung fisik rak A',
        })

        self.assertEqual(response.status_code, 302)
        send_alert.assert_called_once()

    def test_receiving_order_rejects_stock_overflow(self):
        with app.app_context():
            product = db.session.get(Product, self.product_id)
            product.stock = 2_147_483_647
            order = PurchaseOrder(
                supplier_id=self.supplier_id,
                product_id=self.product_id,
                quantity=1,
                status='ordered',
                created_by_id=self.admin_id,
            )
            db.session.add(order)
            db.session.commit()
            order_id = order.id

        self.login_as('staff@test.local')
        response = self.client.post(
            f'/purchase-orders/{order_id}/status',
            data={'status': 'received'},
        )

        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(
                db.session.get(Product, self.product_id).stock,
                2_147_483_647,
            )
            self.assertEqual(
                db.session.get(PurchaseOrder, order_id).status,
                'ordered',
            )
            self.assertEqual(Transaction.query.count(), 0)

    def test_supplier_and_order_creation_are_admin_only(self):
        self.login_as('staff@test.local')
        self.assertEqual(self.client.get('/suppliers').status_code, 403)
        self.assertEqual(self.client.post('/purchase-orders').status_code, 403)

        self.client.get('/logout')
        self.login_as('admin@test.local')
        response = self.client.post('/purchase-orders', data={
            'supplier_id': str(self.supplier_id),
            'product_id': str(self.product_id),
            'quantity': '6',
            'status': 'draft',
            'note': 'Restock rutin',
        })

        self.assertEqual(response.status_code, 302)
        with app.app_context():
            order = PurchaseOrder.query.one()
            self.assertEqual(order.status, 'draft')
            self.assertEqual(order.created_by_id, self.admin_id)
            self.assertEqual(db.session.get(Product, self.product_id).stock, 12)

    def test_receiving_order_updates_stock_once_and_audits_receiver(self):
        with app.app_context():
            order = PurchaseOrder(
                supplier_id=self.supplier_id,
                product_id=self.product_id,
                quantity=7,
                status='ordered',
                created_by_id=self.admin_id,
            )
            db.session.add(order)
            db.session.commit()
            order_id = order.id

        self.login_as('staff@test.local')
        response = self.client.post(
            f'/purchase-orders/{order_id}/status',
            data={'status': 'received'},
        )
        self.assertEqual(response.status_code, 302)

        with app.app_context():
            order = db.session.get(PurchaseOrder, order_id)
            self.assertEqual(order.status, 'received')
            self.assertEqual(order.received_by_id, self.staff_id)
            self.assertIsNotNone(order.received_at)
            self.assertEqual(db.session.get(Product, self.product_id).stock, 19)
            transaction = Transaction.query.one()
            self.assertEqual(transaction.type, 'in')
            self.assertEqual(transaction.quantity, 7)
            self.assertEqual(transaction.user_id, self.staff_id)

        duplicate = self.client.post(
            f'/purchase-orders/{order_id}/status',
            data={'status': 'received'},
        )
        self.assertEqual(duplicate.status_code, 400)
        with app.app_context():
            self.assertEqual(db.session.get(Product, self.product_id).stock, 19)
            self.assertEqual(Transaction.query.count(), 1)

    def test_staff_cannot_cancel_or_advance_draft_order(self):
        with app.app_context():
            order = PurchaseOrder(
                supplier_id=self.supplier_id,
                product_id=self.product_id,
                quantity=4,
                status='draft',
                created_by_id=self.admin_id,
            )
            db.session.add(order)
            db.session.commit()
            order_id = order.id

        self.login_as('staff@test.local')
        response = self.client.post(
            f'/purchase-orders/{order_id}/status',
            data={'status': 'ordered'},
        )
        self.assertEqual(response.status_code, 403)
        with app.app_context():
            self.assertEqual(db.session.get(PurchaseOrder, order_id).status, 'draft')
            self.assertEqual(db.session.get(Product, self.product_id).stock, 12)


if __name__ == '__main__':
    unittest.main()
