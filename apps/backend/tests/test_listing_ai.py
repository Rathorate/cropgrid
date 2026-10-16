import os
import io
import runpy
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_trading
from app.listing_ai import parse_listing_response, response_format, NoListingFound, ListingResponseError

class ListingAiTests(unittest.TestCase):
    setUp = test_trading.TradingTests.setUp
    request = test_trading.TradingTests.request
    account = test_trading.TradingTests.account

    def test_unknown_fields_stay_blank_and_invalid_numbers_are_not_accepted(self):
        draft = parse_listing_response('{"crop_name":" Yam ","quantity_tons":-2,"moisture_percentage":true}')
        self.assertEqual(draft["crop_name"], "Yam")
        self.assertIsNone(draft["quantity_tons"])
        self.assertIsNone(draft["moisture_percentage"])
        self.assertIsNone(draft["asking_price_per_ton_ngn"])

    def test_legacy_wrapped_listing_is_unwrapped(self):
        draft = parse_listing_response('{"listing":{"crop_name":"Yam","quantity_tons":100,"location_state":"Abuja"}}')
        self.assertEqual(draft["quantity_tons"], 100)
        self.assertEqual(draft["location_state"], "Abuja")

    def test_no_crop_is_an_input_problem_not_a_provider_outage(self):
        with self.assertRaises(NoListingFound):
            parse_listing_response('{"crop_name":null}')
        with self.assertRaises(ListingResponseError):
            parse_listing_response('[]')
        with self.assertRaises(ListingResponseError):
            parse_listing_response('not JSON')

    def test_groq_schema_requires_flat_nullable_fields(self):
        fmt = response_format("openai/gpt-oss-20b")
        self.assertEqual(fmt["type"], "json_schema")
        schema = fmt["json_schema"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]), set(schema["required"]))
        self.assertIn("null", schema["properties"]["crop_name"]["type"])

    def test_audio_without_listing_details_returns_actionable_422(self):
        self.account("SELLER")
        client = SimpleNamespace(
            audio=SimpleNamespace(transcriptions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(text="Hello, this is a recording test."))),
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"crop_name":null}'))]))),
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY":"fake"}), patch("openai.OpenAI", return_value=client):
            result = self.request("POST", "/api/v1/ai/parse-audio", files={"file":("voice.m4a", b"mock recording", "audio/mp4")})
        self.assertEqual(result.status_code, 422, result.text)
        self.assertIn("No crop", result.json()["detail"])

    def test_audio_diagnostic_explains_missing_crop_instead_of_reporting_502(self):
        client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(text="Hello, recording test."))), chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"crop_name":null}'))]))))
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "test.m4a"
            audio.write_bytes(b"mock audio")
            with patch.dict(os.environ, {"OPENAI_API_KEY":"fake"}), patch("openai.OpenAI", return_value=client), patch("sys.argv", ["check_ai.py", "--audio", str(audio), "--show-transcript"]), patch("sys.stdout", output):
                with self.assertRaises(SystemExit) as stopped:
                    runpy.run_path("scripts/check_ai.py", run_name="__main__")
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("Hello, recording test.", output.getvalue())
        self.assertIn("did not produce a crop listing", output.getvalue())
        self.assertNotIn("502", output.getvalue())

    def test_groq_audio_to_draft_uses_same_schema_and_keeps_values(self):
        self.account("SELLER")
        sent = {}
        def extract(**kwargs):
            sent.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"crop_name":"Yam","quantity_tons":100,"location_state":"Abuja","asking_price_per_ton_ngn":500000}'))])
        client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(text="100 tons of yam in Abuja at 500000 naira per ton"))), chat=SimpleNamespace(completions=SimpleNamespace(create=extract)))
        with patch.dict(os.environ, {"OPENAI_API_KEY":"fake","OPENAI_LISTING_MODEL":"openai/gpt-oss-20b"}), patch("openai.OpenAI", return_value=client):
            result = self.request("POST", "/api/v1/ai/parse-audio", files={"file":("voice.m4a", b"mock recording", "audio/mp4")})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["draft"]["quantity_tons"], 100)
        self.assertEqual(sent["response_format"]["type"], "json_schema")
        self.assertEqual(result.json()["draft"]["asking_price_per_ton_ngn"], 500000)
