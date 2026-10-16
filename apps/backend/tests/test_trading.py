import asyncio
import io
import os
import unittest
import uuid
from unittest.mock import patch
import httpx
from PIL import Image
from app.main import app
from app.database import SessionLocal
from app.models import Fulfillment, PaymentTransaction

class TradingTests(unittest.TestCase):
    def setUp(self):
        self.cookies = httpx.Cookies()

    def request(self, method, path, **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", cookies=self.cookies) as client:
                response = await client.request(method, path, **kwargs)
                self.cookies.update(client.cookies)
                return response
        return asyncio.run(send())

    def account(self, role):
        self.cookies.clear()
        response = self.request("POST", "/api/v1/auth/register", json={"full_name": "Trading Test", "email": f"{uuid.uuid4().hex}@example.com", "password": "testing-password-123", "role": role})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json(), httpx.Cookies(self.cookies)

    def listing(self):
        user, cookies = self.account("SELLER")
        response = self.request("POST", "/api/v1/inventories", json={"crop_name": "Yam", "quantity_tons": 3, "location_state": "Ibadan", "asking_price_per_ton_ngn": 100000})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json(), user, cookies

    def test_media_validation_owner_access_persistence_and_range(self):
        listing, seller, seller_cookies = self.listing()
        path = f"/api/v1/inventories/{listing['id']}/media"
        image = io.BytesIO()
        Image.new("RGB", (20, 20), "green").save(image, "PNG")
        upload = {"file": ("crop.png", image.getvalue(), "image/png")}
        created = self.request("POST", path, files=upload)
        self.assertEqual(created.status_code, 201, created.text)
        url = created.json()["url"]
        repeated = self.request("POST", path, files=upload)
        self.assertEqual(repeated.json()["id"], created.json()["id"])
        self.cookies.clear()
        downloaded = self.request("GET", url)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.headers["content-type"], "image/jpeg")
        partial = self.request("GET", url, headers={"Range": "bytes=0-9", "Origin": "http://localhost:3000"})
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.headers["access-control-allow-origin"], "http://localhost:3000")
        self.assertEqual(len(partial.content), 10)
        self.assertEqual(self.request("GET", url, headers={"Range": "bytes=999999-"}).status_code, 416)
        self.account("SELLER")
        self.assertEqual(self.request("POST", path, files=upload).status_code, 403)
        self.cookies = seller_cookies
        self.assertEqual(self.request("POST", path, files={"file": ("fake.png", b"<script>evil</script>", "image/png")}).status_code, 415)
        self.assertEqual(self.request("POST", path, files={"file": ("fake.mp4", b"not a video", "video/mp4")}).status_code, 415)
        listings = self.request("GET", "/api/v1/inventories", params={"crop": "Yam"}).json()
        self.assertEqual(next(row for row in listings if row["id"] == listing["id"])["media"][0]["url"], url)
        # Real MP4/WebM clips require browser playback acceptance; no synthetic clip is claimed playable.

    def test_chat_is_private_and_duplicate_start_is_idempotent(self):
        listing, seller, seller_cookies = self.listing()
        buyer, buyer_cookies = self.account("BUYER")
        response = self.request("POST", "/api/v1/conversations", json={"inventory_id": listing["id"]})
        self.assertEqual(response.status_code, 201, response.text)
        thread = response.json()["id"]
        repeated = self.request("POST", "/api/v1/conversations", json={"inventory_id": listing["id"]})
        self.assertEqual(repeated.json()["id"], thread)
        path = f"/api/v1/conversations/{thread}/messages"
        sent = self.request("POST", path, json={"body": "Can I inspect the yam before shipment?"})
        self.assertEqual(sent.status_code, 201, sent.text)
        self.assertEqual(self.request("POST", path, json={"body": "   "}).status_code, 422)
        self.cookies = seller_cookies
        self.assertEqual(self.request("GET", path).json()[0]["body"], "Can I inspect the yam before shipment?")
        self.assertEqual(self.request("GET", path, params={"after_id": sent.json()["id"]}).json(), [])
        self.account("BUYER")
        self.assertEqual(self.request("GET", path).status_code, 404)
        self.assertEqual(self.request("POST", path, json={"body": "Not my conversation"}).status_code, 404)
        self.assertFalse(any(row["id"] == thread for row in self.request("GET", "/api/v1/conversations").json()))

    def test_delivery_requires_payment_correct_participants_and_ordered_transitions(self):
        listing, seller, seller_cookies = self.listing()
        buyer, buyer_cookies = self.account("BUYER")
        reference = "CG-" + uuid.uuid4().hex
        with SessionLocal() as db:
            payment = PaymentTransaction(inventory_id=listing["id"], buyer_user_id=buyer["id"], buyer_name=buyer["full_name"], buyer_email=buyer["email"], quantity_tons=1, currency="NGN", amount_subunit=10000000, status="PENDING", reference=reference)
            db.add(payment); db.commit(); payment_id = payment.id
        path = f"/api/v1/orders/{reference}/delivery"
        self.assertEqual(self.request("POST", path, json={"action": "CONFIRM_RECEIPT"}).status_code, 409)
        with SessionLocal() as db:
            db.get(PaymentTransaction, payment_id).status = "SUCCESS"; db.commit()
        self.assertEqual(self.request("POST", path, json={"action": "DISPATCH", "details": "Truck 12"}).status_code, 403)
        self.assertEqual(self.request("POST", path, json={"action": "CONFIRM_RECEIPT"}).status_code, 409)
        self.cookies = seller_cookies
        self.assertEqual(self.request("POST", path, json={"action": "DISPATCH", "details": "Truck 12"}).status_code, 200)
        self.assertEqual(self.request("POST", path, json={"action": "CONFIRM_RECEIPT"}).status_code, 403)
        self.cookies = buyer_cookies
        received = self.request("POST", path, json={"action": "CONFIRM_RECEIPT"})
        self.assertEqual(received.status_code, 200, received.text)
        self.assertFalse(received.json()["funds_released"])
        self.assertEqual(self.request("POST", path, json={"action": "CONFIRM_RECEIPT"}).status_code, 409)
        order = next(row for row in self.request("GET", "/api/v1/orders/me").json() if row["reference"] == reference)
        self.assertEqual(order["delivery_status"], "RECEIVED")
        self.assertEqual(order["funds_release_status"], "NOT_ENABLED")
        self.account("BUYER")
        self.assertEqual(self.request("POST", path, json={"action": "DISPUTE", "details": "Unrelated"}).status_code, 404)

    def test_dispute_blocks_receipt_confirmation(self):
        listing, seller, seller_cookies = self.listing()
        buyer, buyer_cookies = self.account("BUYER")
        reference = "CG-" + uuid.uuid4().hex
        with SessionLocal() as db:
            payment = PaymentTransaction(inventory_id=listing["id"], buyer_user_id=buyer["id"], buyer_name=buyer["full_name"], buyer_email=buyer["email"], quantity_tons=1, amount_subunit=10000000, status="SUCCESS", reference=reference)
            db.add(payment); db.flush(); db.add(Fulfillment(payment_id=payment.id, status="DISPATCHED")); db.commit()
        path = f"/api/v1/orders/{reference}/delivery"
        result = self.request("POST", path, json={"action": "DISPUTE", "details": "Wrong produce"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.request("POST", path, json={"action": "CONFIRM_RECEIPT"}).status_code, 409)

    def test_live_payments_are_disabled_until_approved_fund_flow_exists(self):
        self.account("BUYER")
        with patch.dict(os.environ, {"PAYSTACK_SECRET_KEY": "sk_live_do-not-charge"}):
            result = self.request("POST", "/api/v1/payments/initialize", json={"inventory_id": 1, "quantity_tons": 1, "buyer_name": "Tester", "buyer_email": "tester@example.com"})
        self.assertEqual(result.status_code, 503)

    def test_ai_auth_and_quota_errors_are_actionable_without_leaking_secrets(self):
        from openai import AuthenticationError, RateLimitError
        self.account("SELLER")
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        for error, expected in [
            (AuthenticationError("secret-upstream-message", response=httpx.Response(401, request=request), body={}), "credentials"),
            (RateLimitError("secret-upstream-message", response=httpx.Response(429, request=request), body={"code": "insufficient_quota"}), "credit"),
        ]:
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-not-a-real-key"}), patch("openai.OpenAI", side_effect=error):
                response = self.request("POST", "/api/v1/ai/parse-text", json={"text": "yam, Ibadan, 2 tons"})
            self.assertEqual(response.status_code, 503, response.text)
            self.assertIn(expected, response.json()["detail"])
            self.assertNotIn("secret-upstream-message", response.text)
