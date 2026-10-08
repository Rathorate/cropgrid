import asyncio
import unittest
import httpx
from app.main import app

class CropGridApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transport = httpx.ASGITransport(app=app)

    def request(self, method, path, **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=self.transport, base_url="http://testserver") as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(send())

    def test_health_reports_development_mode(self):
        response = self.request("GET", "/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "development-mvp")

    def test_inventory_query_and_validation(self):
        rows = self.request("GET", "/api/v1/inventories", params={"crop": "Ginger"})
        self.assertEqual(rows.status_code, 200)
        self.assertTrue(any(row["crop_name"] == "Ginger" for row in rows.json()))
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
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            response = self.request("POST", "/api/v1/ai/parse-audio", files={"file": ("note.wav", b"audio", "audio/wav")})
            self.assertEqual(response.status_code, 503)
        finally:
            if old_key is not None:
                os.environ["OPENAI_API_KEY"] = old_key

if __name__ == "__main__":
    unittest.main()
