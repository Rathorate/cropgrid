import hashlib
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
from sqlalchemy import delete, select
import test_trading
from app.database import SessionLocal
from app.models import AuthThrottle, PasswordReset, UserSession


@patch.dict(os.environ, {"RESEND_API_KEY":"re_test_private", "PASSWORD_RESET_FROM_EMAIL":"CropGrid <test@example.com>", "APP_PUBLIC_URL":"https://cropgrid-hazel.vercel.app"})
class PasswordRecoveryTests(unittest.TestCase):
    request = test_trading.TradingTests.request
    account = test_trading.TradingTests.account

    def setUp(self):
        test_trading.TradingTests.setUp(self)
        with SessionLocal() as db:
            db.execute(delete(AuthThrottle)); db.commit()

    def forgot(self, email):
        with patch("app.password_recovery.send_email") as mail:
            response = self.request("POST", "/api/v1/auth/forgot-password", json={"email":email})
        return response, mail

    def create_link(self):
        user, cookies = self.account("BUYER")
        response, mail = self.forgot(user["email"])
        self.assertEqual(response.status_code, 202, response.text)
        text = mail.call_args.args[2]
        link = text.splitlines()[1]
        self.assertTrue(link.startswith("https://cropgrid-hazel.vercel.app/account#"))
        token = parse_qs(urlparse(link).fragment)["reset_token"][0]
        return user, cookies, token

    def reset(self, token, **changes):
        payload = {"token":token, "new_password":"new-private-password-123", "confirm_password":"new-private-password-123", **changes}
        with patch("app.password_recovery.send_email"):
            return self.request("POST", "/api/v1/auth/reset-password", json=payload)

    def test_email_is_generic_and_token_only_in_mail_not_api_or_database(self):
        user, _ = self.account("SELLER")
        response, mail = self.forgot(user["email"])
        other, other_mail = self.forgot(f"{uuid.uuid4().hex}@example.com")
        self.assertEqual(response.status_code, other.status_code)
        self.assertEqual(response.json(), other.json())
        other_mail.assert_not_called()
        token = parse_qs(urlparse(mail.call_args.args[2].splitlines()[1]).fragment)["reset_token"][0]
        self.assertNotIn(token, response.text)
        with SessionLocal() as db:
            row = db.scalar(select(PasswordReset).where(PasswordReset.user_id == user["id"]))
            self.assertEqual(row.token_hash, hashlib.sha256(token.encode()).hexdigest())
            self.assertNotEqual(row.token_hash, token)

    def test_reset_is_single_use_and_invalidates_sessions_and_old_password(self):
        user, cookies, token = self.create_link()
        result = self.reset(token)
        self.assertEqual(result.status_code, 200, result.text)
        self.cookies = cookies
        self.assertEqual(self.request("GET", "/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.request("POST", "/api/v1/auth/login", json={"email":user["email"], "password":"testing-password-123"}).status_code, 401)
        self.assertEqual(self.request("POST", "/api/v1/auth/login", json={"email":user["email"], "password":"new-private-password-123"}).status_code, 200)
        self.assertEqual(self.reset(token).status_code, 400)

    def test_expired_token_cannot_change_password(self):
        user, _, token = self.create_link()
        with SessionLocal() as db:
            row = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hashlib.sha256(token.encode()).hexdigest()))
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1); db.commit()
        self.assertEqual(self.reset(token).status_code, 400)
        self.assertEqual(self.request("POST", "/api/v1/auth/login", json={"email":user["email"], "password":"testing-password-123"}).status_code, 200)

    def test_reset_invalidates_other_outstanding_links(self):
        user, _, token = self.create_link()
        response, mail = self.forgot(user["email"])
        second = parse_qs(urlparse(mail.call_args.args[2].splitlines()[1]).fragment)["reset_token"][0]
        self.assertEqual(self.reset(token).status_code, 200)
        self.assertEqual(self.reset(second).status_code, 400)

    def test_invalid_token_weak_password_and_confirmation_are_rejected(self):
        registration = self.request("POST", "/api/v1/auth/register", json={"full_name":"Test Buyer", "email":f"{uuid.uuid4().hex}@example.com", "password":" "*12, "role":"BUYER"})
        self.assertEqual(registration.status_code, 422)
        _, _, token = self.create_link()
        self.assertEqual(self.reset("a"*43).status_code, 400)
        self.assertEqual(self.reset(token, new_password="short", confirm_password="short").status_code, 422)
        self.assertEqual(self.reset(token, confirm_password="different-password").status_code, 422)
        self.assertEqual(self.reset(token, new_password=" "*12, confirm_password=" "*12).status_code, 422)
        self.assertEqual(self.reset(token).status_code, 200)

    def test_forgot_email_has_persistent_limit(self):
        email = f"{uuid.uuid4().hex}@example.com"
        for _ in range(3):
            self.assertEqual(self.forgot(email)[0].status_code, 202)
        result, _ = self.forgot(email)
        self.assertEqual(result.status_code, 429)
        self.assertGreater(int(result.headers["retry-after"]), 0)

    def test_mail_failure_does_not_return_provider_details_or_leave_usable_token(self):
        user, _ = self.account("BUYER")
        with patch("app.password_recovery.send_email", side_effect=RuntimeError("private provider body")):
            response = self.request("POST", "/api/v1/auth/forgot-password", json={"email":user["email"]})
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("private provider body", response.text)
        with SessionLocal() as db:
            self.assertIsNotNone(db.scalar(select(PasswordReset).where(PasswordReset.user_id == user["id"])).used_at)

    def test_unconfigured_email_fails_clearly_for_all_accounts(self):
        with patch.dict(os.environ, {"RESEND_API_KEY":""}):
            response, _ = self.forgot("unknown@example.com")
        self.assertEqual(response.status_code, 503)
        self.assertIn("not configured", response.json()["detail"])

    def test_recovery_rejects_untrusted_origin(self):
        response = self.request("POST", "/api/v1/auth/forgot-password", json={"email":"unknown@example.com"}, headers={"Origin":"https://untrusted.example"})
        self.assertEqual(response.status_code, 403)

    def test_change_requires_login_current_password_and_matching_confirmation(self):
        payload = {"current_password":"testing-password-123", "new_password":"changed-private-password-123", "confirm_password":"changed-private-password-123"}
        self.assertEqual(self.request("POST", "/api/v1/auth/change-password", json=payload).status_code, 401)
        user, cookies = self.account("BUYER")
        wrong = self.request("POST", "/api/v1/auth/change-password", json={**payload,"current_password":"wrong"})
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(self.request("POST", "/api/v1/auth/change-password", json={**payload,"confirm_password":"not-the-same"}).status_code, 422)
        with patch("app.password_recovery.send_email"):
            result = self.request("POST", "/api/v1/auth/change-password", json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.cookies = cookies
        self.assertEqual(self.request("GET", "/api/v1/auth/me").status_code, 401)
        self.assertEqual(self.request("POST", "/api/v1/auth/login", json={"email":user["email"], "password":payload["new_password"]}).status_code, 200)

    def test_api_responses_are_not_cacheable(self):
        result = self.request("GET", "/api/v1/auth/me")
        self.assertEqual(result.headers["cache-control"], "no-store")
