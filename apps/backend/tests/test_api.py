import asyncio
import unittest
import uuid
import httpx
from app.main import app
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from app.database import SessionLocal
from app.models import Inventory, ListingReport, PaymentTransaction, User
from app.auth import hash_password

class CropGridApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transport = httpx.ASGITransport(app=app)

    def setUp(self):
        self.cookies = httpx.Cookies()

    def request(self, method, path, **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://testserver", cookies=self.cookies) as client:
                response = await client.request(method, path, **kwargs)
                self.cookies.update(client.cookies)
                return response
        return asyncio.run(send())

    def register_test_user(self, role="BUYER"):
        email = f"test-{uuid.uuid4().hex}@example.com"
        response = self.request("POST", "/api/v1/auth/register", json={"full_name":"CropGrid Test User", "email":email, "password":"test-password-123", "role":role})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_buyer_signup_login_and_admin_role_is_not_public(self):
        user = self.register_test_user()
        self.assertEqual(user["role"], "BUYER")
        self.assertEqual(self.request("GET", "/api/v1/auth/me").json()["email"], user["email"])
        self.assertEqual(self.request("POST", "/api/v1/auth/logout").status_code, 204)
        self.assertEqual(self.request("GET", "/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.request("POST", "/api/v1/auth/login", json={"email":user["email"], "password":"wrong-password"}).status_code, 401)
        self.assertEqual(self.request("POST", "/api/v1/auth/login", json={"email":user["email"], "password":"test-password-123"}).status_code, 200)
        denied = self.request("POST", "/api/v1/auth/register", json={"full_name":"Bad Admin", "email":f"admin-{uuid.uuid4().hex}@example.com", "password":"test-password-123", "role":"ADMIN"})
        self.assertEqual(denied.status_code, 422)

    def test_seller_actions_reject_guests_and_buyers(self):
        audio = {"file": ("note.wav", b"mock audio", "audio/wav")}
        self.assertEqual(self.request("POST", "/api/v1/ai/parse-audio", files=audio).status_code, 401)
        self.register_test_user("BUYER")
        self.assertEqual(self.request("POST", "/api/v1/ai/parse-audio", files=audio).status_code, 403)
        listing_payload = {"crop_name":"Yam", "quantity_tons":1, "location_state":"Kano", "asking_price_per_ton_ngn":50000}
        self.assertEqual(self.request("POST", "/api/v1/inventories", json=listing_payload).status_code, 403)

    def test_listing_report_is_admin_reviewed(self):
        self.register_test_user("BUYER")
        listing = self.request("GET", "/api/v1/inventories").json()[0]
        created = self.request("POST", f"/api/v1/inventories/{listing['id']}/reports", json={"reason":"MISLEADING", "details":"Test report"})
        self.assertEqual(created.status_code, 201, created.text)
        report_id = created.json()["id"]
        self.assertEqual(self.request("GET", "/api/v1/admin/reports").status_code, 403)
        admin_email = f"admin-{uuid.uuid4().hex}@example.com"
        with SessionLocal() as db:
            db.add(User(full_name="Test Administrator", email=admin_email, password_hash=hash_password("admin-test-password-123"), role="ADMIN"))
            db.commit()
        self.cookies.clear()
        signed_in = self.request("POST", "/api/v1/auth/login", json={"email":admin_email, "password":"admin-test-password-123"})
        self.assertEqual(signed_in.status_code, 200, signed_in.text)
        rows = self.request("GET", "/api/v1/admin/reports")
        self.assertEqual(rows.status_code, 200, rows.text)
        self.assertTrue(any(row["id"] == report_id for row in rows.json()))
        updated = self.request("PATCH", f"/api/v1/admin/reports/{report_id}", json={"status":"REVIEWING"})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["status"], "REVIEWING")
        with SessionLocal() as db:
            db.delete(db.get(ListingReport, report_id))
            db.commit()

    def test_health_reports_development_mode(self):
        response = self.request("GET", "/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "development-mvp")

    def test_inventory_query_and_validation(self):
        rows = self.request("GET", "/api/v1/inventories", params={"crop": "Ginger"})
        self.assertEqual(rows.status_code, 200)
        self.assertTrue(any(row["crop_name"] == "Ginger" for row in rows.json()))
        self.assertEqual(self.request("POST", "/api/v1/inventories", json={"crop_name":"Yam", "quantity_tons":1, "location_state":"Kano", "asking_price_per_ton_ngn":50}).status_code, 401)
        self.register_test_user("SELLER")
        invalid = self.request("POST", "/api/v1/inventories", json={"crop_name":"X", "quantity_tons":0, "location_state":"Kano", "asking_price_per_ton_ngn":0})
        self.assertEqual(invalid.status_code, 422)

    def test_order_caps_quantity_and_document_is_explicitly_draft(self):
        rows = self.request("GET", "/api/v1/inventories").json()
        listing = next(row for row in rows if row["crop_name"] == "Ginger")
        excessive = self.request("POST", "/api/v1/orders/escrow-initiate", json={"inventory_id":listing["id"],"quantity_tons":listing["quantity_tons"] + 1})
        self.assertEqual(excessive.status_code, 422)
        created = self.request("POST", "/api/v1/orders/escrow-initiate", json={"inventory_id":listing["id"],"quantity_tons":2})
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["demo_only"])
        doc = self.request("GET", f"/api/v1/export/form-nxp/{created.json()['order']['id']}")
        self.assertEqual(doc.status_code, 200)
        self.assertFalse(doc.json()["official_document"])

    def test_audio_parser_requires_provider_configuration(self):
        import os
        self.register_test_user("SELLER")
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            response = self.request("POST", "/api/v1/ai/parse-audio", files={"file": ("note.wav", b"audio", "audio/wav")})
            self.assertEqual(response.status_code, 503)
        finally:
            if old_key is not None:
                os.environ["OPENAI_API_KEY"] = old_key

    def test_audio_parser_returns_reviewable_listing_draft(self):
        import os
        self.register_test_user("SELLER")
        old_key = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "sk-test-mocked"
        fake_client = SimpleNamespace(
            audio=SimpleNamespace(transcriptions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(text="We have 20 tons of ginger in Kaduna."))),
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"crop_name":"Ginger","quantity_tons":20,"location_state":"Kaduna"}'))]))),
        )
        try:
            with patch("openai.OpenAI", return_value=fake_client):
                response = self.request("POST", "/api/v1/ai/parse-audio", files={"file": ("note.wav", b"mock audio bytes", "audio/wav")})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertEqual(result["transcript"], "We have 20 tons of ginger in Kaduna.")
            self.assertEqual(result["draft"]["crop_name"], "Ginger")
            self.assertEqual(result["draft"]["quantity_tons"], 20)
            self.assertTrue(result["requires_human_review"])
        finally:
            if old_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old_key

    def test_payment_is_disabled_without_provider_key(self):
        import os
        self.register_test_user("BUYER")
        old_key = os.environ.pop("PAYSTACK_SECRET_KEY", None)
        try:
            response = self.request("POST", "/api/v1/payments/initialize", json={"inventory_id":1,"quantity_tons":1,"buyer_name":"Test Buyer","buyer_email":"buyer@example.com","currency":"NGN"})
            self.assertEqual(response.status_code, 503)
        finally:
            if old_key is not None:
                os.environ["PAYSTACK_SECRET_KEY"] = old_key

    def test_payment_initialization_uses_server_inventory_price(self):
        import os
        self.register_test_user("BUYER")
        old_key = os.environ.get("PAYSTACK_SECRET_KEY")
        os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test"
        try:
            listings = self.request("GET", "/api/v1/inventories").json()
            listing = next(row for row in listings if row["crop_name"] == "Ginger")
            with patch("app.main.paystack_request", new_callable=AsyncMock) as provider:
                provider.return_value = {"authorization_url":"https://checkout.paystack.com/example"}
                response = self.request("POST", "/api/v1/payments/initialize", json={"inventory_id":listing["id"],"quantity_tons":0.1,"buyer_name":"Test Buyer","buyer_email":"buyer@example.com","currency":"NGN"})
            self.assertEqual(response.status_code, 201, response.text)
            result = response.json()
            self.assertEqual(result["amount"], "185000.00")
            self.assertEqual(result["currency"], "NGN")
            sent = provider.await_args.kwargs["payload"]
            self.assertEqual(sent["amount"], 18_500_000)
            self.assertTrue(result["authorization_url"].startswith("https://checkout.paystack.com/"))
            history = self.request("GET", "/api/v1/orders/me")
            self.assertEqual(history.status_code, 200, history.text)
            self.assertTrue(any(order["reference"] == result["reference"] and order["crop_name"] == "Ginger" for order in history.json()))
            with SessionLocal() as db:
                row = db.query(PaymentTransaction).filter_by(reference=result["reference"]).one()
                db.delete(row)
                db.commit()
        finally:
            if old_key is None:
                os.environ.pop("PAYSTACK_SECRET_KEY", None)
            else:
                os.environ["PAYSTACK_SECRET_KEY"] = old_key

    def test_payment_webhook_rejects_invalid_signature(self):
        import os
        old_key = os.environ.get("PAYSTACK_SECRET_KEY")
        os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test"
        try:
            response = self.request("POST", "/api/v1/payments/webhook", json={"event":"charge.success"}, headers={"x-paystack-signature":"invalid"})
            self.assertEqual(response.status_code, 401)
        finally:
            if old_key is None:
                os.environ.pop("PAYSTACK_SECRET_KEY", None)
            else:
                os.environ["PAYSTACK_SECRET_KEY"] = old_key

    def test_payment_verification_flags_provider_amount_mismatch(self):
        import os
        old_key = os.environ.get("PAYSTACK_SECRET_KEY")
        os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test"
        reference = "CG-test-amount-mismatch"
        try:
            listings = self.request("GET", "/api/v1/inventories").json()
            listing = next(row for row in listings if row["crop_name"] == "Ginger")
            with SessionLocal() as db:
                db.add(PaymentTransaction(inventory_id=listing["id"], buyer_name="Test Buyer", buyer_email="buyer@example.com", quantity_tons=1, currency="NGN", amount_subunit=185_000_000, status="PENDING", reference=reference))
                db.commit()
            with patch("app.main.paystack_request", new_callable=AsyncMock) as provider:
                provider.return_value = {"reference": reference, "status": "success", "currency": "NGN", "amount": 1, "id": 123}
                response = self.request("GET", f"/api/v1/payments/verify/{reference}")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["status"], "PAID_REVIEW")
            with SessionLocal() as db:
                row = db.query(PaymentTransaction).filter_by(reference=reference).one()
                db.delete(row)
                db.commit()
        finally:
            if old_key is None:
                os.environ.pop("PAYSTACK_SECRET_KEY", None)
            else:
                os.environ["PAYSTACK_SECRET_KEY"] = old_key

    def test_verified_payment_reduces_stock_once(self):
        import os
        old_key = os.environ.get("PAYSTACK_SECRET_KEY")
        os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_unit_test"
        reference = "CG-test-success-idempotent"
        listing_id = None
        starting_quantity = None
        try:
            listings = self.request("GET", "/api/v1/inventories").json()
            listing = next(row for row in listings if row["crop_name"] == "Ginger")
            listing_id = listing["id"]
            starting_quantity = listing["quantity_tons"]
            with SessionLocal() as db:
                db.add(PaymentTransaction(inventory_id=listing_id, buyer_name="Test Buyer", buyer_email="buyer@example.com", quantity_tons=0.1, currency="NGN", amount_subunit=18_500_000, status="PENDING", reference=reference))
                db.commit()
            with patch("app.main.paystack_request", new_callable=AsyncMock) as provider:
                provider.return_value = {"reference": reference, "status": "success", "currency": "NGN", "amount": 18_500_000, "id": 456}
                confirmed = self.request("GET", f"/api/v1/payments/verify/{reference}")
                self.assertEqual(confirmed.json()["status"], "SUCCESS")
                repeated = self.request("GET", f"/api/v1/payments/verify/{reference}")
                self.assertEqual(repeated.json()["status"], "SUCCESS")
                provider.assert_awaited_once()
            with SessionLocal() as db:
                inventory = db.get(Inventory, listing_id)
                self.assertAlmostEqual(inventory.quantity_tons, starting_quantity - 0.1)
                inventory.quantity_tons = starting_quantity
                payment = db.query(PaymentTransaction).filter_by(reference=reference).one()
                db.delete(payment)
                db.commit()
        finally:
            if old_key is None:
                os.environ.pop("PAYSTACK_SECRET_KEY", None)
            else:
                os.environ["PAYSTACK_SECRET_KEY"] = old_key

if __name__ == "__main__":
    unittest.main()
