"""Provider responses are mocked; signatures and application transitions are real."""
import hashlib
import hmac
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import test_trading
from app.database import SessionLocal
from app.models import Inventory, PaymentTransaction

@patch.dict(os.environ, {"PAYSTACK_SECRET_KEY": "sk_test_acceptance"})
class PaymentAcceptanceTests(unittest.TestCase):
    setUp = test_trading.TradingTests.setUp
    request = test_trading.TradingTests.request
    account = test_trading.TradingTests.account
    listing = test_trading.TradingTests.listing

    def payment(self, created_at=None):
        listing, _, _ = self.listing()
        buyer, _ = self.account("BUYER")
        reference = "CG-" + uuid.uuid4().hex
        with SessionLocal() as db:
            row = PaymentTransaction(inventory_id=listing["id"], buyer_user_id=buyer["id"], buyer_name=buyer["full_name"], buyer_email=buyer["email"], quantity_tons=1, currency="NGN", amount_subunit=10_000_000, status="PENDING", reference=reference)
            if created_at:
                row.created_at = created_at
            db.add(row); db.commit()
        provider = {"id": 987, "reference": reference, "status": "success", "amount": 10_000_000, "currency": "NGN"}
        return listing, reference, provider

    def stock(self, listing):
        with SessionLocal() as db:
            return db.get(Inventory, listing["id"]).quantity_tons

    def test_signed_success_webhook_verifies_and_deducts_stock_once(self):
        listing, reference, data = self.payment()
        raw = json.dumps({"event":"charge.success", "data":{"reference":reference}}).encode()
        signature = hmac.new(b"sk_test_acceptance", raw, hashlib.sha512).hexdigest()
        with patch("app.main.paystack_request", new_callable=AsyncMock, return_value=data) as provider:
            for _ in range(2):
                result = self.request("POST", "/api/v1/payments/webhook", content=raw, headers={"Content-Type":"application/json", "x-paystack-signature":signature})
                self.assertEqual(result.status_code, 200, result.text)
            provider.assert_awaited_once()
        self.assertEqual(self.stock(listing), 2)

    def test_currency_mismatch_requires_review_without_stock_reduction(self):
        listing, reference, data = self.payment()
        data["currency"] = "USD"
        with patch("app.main.paystack_request", new_callable=AsyncMock, return_value=data):
            result = self.request("GET", f"/api/v1/payments/verify/{reference}")
        self.assertEqual(result.json()["status"], "PAID_REVIEW")
        self.assertEqual(self.stock(listing), 3)

    def test_reference_mismatch_requires_review_without_stock_reduction(self):
        listing, reference, data = self.payment()
        data["reference"] = "CG-wrong-reference"
        with patch("app.main.paystack_request", new_callable=AsyncMock, return_value=data):
            result = self.request("GET", f"/api/v1/payments/verify/{reference}")
        self.assertEqual(result.json()["status"], "PAID_REVIEW")
        self.assertEqual(self.stock(listing), 3)

    def test_late_payment_needs_review_even_if_no_checkout_expired_it_yet(self):
        listing, reference, data = self.payment(datetime.now(timezone.utc) - timedelta(minutes=25))
        with patch("app.main.paystack_request", new_callable=AsyncMock, return_value=data):
            result = self.request("GET", f"/api/v1/payments/verify/{reference}")
        self.assertEqual(result.json()["status"], "PAID_REVIEW")
        self.assertEqual(self.stock(listing), 3)

    def test_failed_payment_does_not_deduct_stock(self):
        listing, reference, data = self.payment()
        data["status"] = "failed"
        with patch("app.main.paystack_request", new_callable=AsyncMock, return_value=data):
            result = self.request("GET", f"/api/v1/payments/verify/{reference}")
        self.assertEqual(result.json()["status"], "FAILED")
        self.assertEqual(self.stock(listing), 3)

    def test_pending_reservations_prevent_a_second_excess_checkout(self):
        listing, _, _ = self.listing()
        buyer, _ = self.account("BUYER")
        payload = {"inventory_id":listing["id"], "quantity_tons":2, "buyer_name":buyer["full_name"], "buyer_email":buyer["email"]}
        with patch("app.main.paystack_request", new_callable=AsyncMock, return_value={"authorization_url":"https://checkout.paystack.com/test"}) as provider:
            first = self.request("POST", "/api/v1/payments/initialize", json=payload)
            second = self.request("POST", "/api/v1/payments/initialize", json=payload)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 422, second.text)
        provider.assert_awaited_once()

    def test_expired_reservation_is_reusable(self):
        listing, reference, _ = self.payment(datetime.now(timezone.utc) - timedelta(minutes=25))
        buyer = self.request("GET", "/api/v1/auth/me").json()
        payload = {"inventory_id":listing["id"], "quantity_tons":3, "buyer_name":buyer["full_name"], "buyer_email":buyer["email"]}
        with patch("app.main.paystack_request", new_callable=AsyncMock, return_value={"authorization_url":"https://checkout.paystack.com/test"}):
            result = self.request("POST", "/api/v1/payments/initialize", json=payload)
        self.assertEqual(result.status_code, 201, result.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(PaymentTransaction).filter_by(reference=reference).one().status, "EXPIRED")

    def test_non_paystack_checkout_url_is_rejected(self):
        listing, _, _ = self.listing()
        buyer, _ = self.account("BUYER")
        payload = {"inventory_id":listing["id"], "quantity_tons":1, "buyer_name":buyer["full_name"], "buyer_email":buyer["email"]}
        with patch("app.main.paystack_request", new_callable=AsyncMock, return_value={"authorization_url":"https://untrusted.example/checkout"}):
            result = self.request("POST", "/api/v1/payments/initialize", json=payload)
        self.assertEqual(result.status_code, 502)
        self.assertEqual(self.stock(listing), 3)
