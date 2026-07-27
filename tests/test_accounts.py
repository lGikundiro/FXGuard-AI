import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from pathlib import Path

from fastapi import HTTPException, Request, Response

from backend.app.accounts import (
    PRIVACY_VERSION,
    TERMS_VERSION,
    SavedCheckRequest,
    OtpStartRequest,
    OtpVerifyRequest,
    _normalise_supabase_api_url,
    _require_csrf,
    auth_config,
    configured_origins,
    delete_account,
    normalise_saved_check,
    start_otp,
    verify_otp,
)


class AccountFoundationTests(unittest.TestCase):
    def sample_result(self):
        return {
            "currency": "USD",
            "amount": 1000,
            "horizon_days": 7,
            "risk_level": "Medium",
            "confidence_score": 0.72,
            "current_rate": 1450.25,
            "current_cost_rwf": 1_450_250,
            "possible_extra_cost_rwf": 8_701.5,
            "analysis_date": "2026-07-17",
            "model_version": "2026-07-19T13:14:08+00:00",
            "class_probabilities": {"Low": 0.2, "Medium": 0.72, "High": 0.08},
        }

    def test_saved_check_is_bound_to_user_and_preserves_snapshot(self):
        record = normalise_saved_check(
            SavedCheckRequest(result=self.sample_result()),
            "user-123",
        )
        self.assertEqual(record["user_id"], "user-123")
        self.assertEqual(record["currency"], "USD")
        self.assertEqual(record["likelihood_probability"], 0.72)
        self.assertEqual(record["rate_date"], "2026-07-17")
        self.assertEqual(record["model_version"], "2026-07-19T13:14:08+00:00")
        self.assertEqual(record["result"]["risk_level"], "Medium")
        self.assertEqual(len(record["signature"]), 64)

    def test_invalid_saved_result_is_rejected(self):
        result = self.sample_result()
        result["currency"] = "GBP"
        with self.assertRaises(HTTPException) as context:
            normalise_saved_check(SavedCheckRequest(result=result), "user-123")
        self.assertEqual(context.exception.status_code, 400)

    def test_public_auth_config_contains_no_secrets(self):
        with (
            patch("backend.app.accounts.AUTH_CONFIGURED", True),
            patch("backend.app.accounts.ENABLED_AUTH_METHODS", ("email",)),
            patch("backend.app.accounts.SUPABASE_SERVICE_ROLE_KEY", ""),
            patch("backend.app.accounts.SELF_DELETE_RPC_ENABLED", True),
        ):
            payload = auth_config()
        self.assertEqual(payload["terms_version"], TERMS_VERSION)
        self.assertEqual(payload["privacy_version"], PRIVACY_VERSION)
        self.assertEqual(payload["methods"], ["email"])
        self.assertTrue(payload["registration_enabled"])
        self.assertTrue(payload["account_deletion_enabled"])
        self.assertNotIn("service_role", payload)
        self.assertNotIn("key", payload)

    def test_supabase_api_url_rejects_database_connections(self):
        self.assertEqual(
            _normalise_supabase_api_url(
                "postgresql://postgres.example:secret@db.example.supabase.com:5432/postgres"
            ),
            "",
        )
        self.assertEqual(
            _normalise_supabase_api_url("https://project-ref.supabase.co/"),
            "https://project-ref.supabase.co",
        )

    def test_disabled_phone_provider_is_rejected_before_sending_code(self):
        payload = OtpStartRequest(
            channel="phone",
            contact="+250781234567",
            intent="signin",
        )
        with (
            patch("backend.app.accounts.AUTH_CONFIGURED", True),
            patch("backend.app.accounts.ENABLED_AUTH_METHODS", ("email",)),
            patch("backend.app.accounts._request_json") as provider_request,
        ):
            with self.assertRaises(HTTPException) as context:
                start_otp(payload)
        self.assertEqual(context.exception.status_code, 503)
        provider_request.assert_not_called()

    def test_cors_origins_are_explicit(self):
        origins = configured_origins()
        self.assertNotIn("*", origins)
        self.assertIn("http://127.0.0.1:8000", origins)
        self.assertIn("https://fxguard-ai-web.onrender.com", origins)

    def test_signup_requires_legal_acknowledgement(self):
        payload = OtpStartRequest(
            channel="phone",
            contact="+250781234567",
            intent="signup",
            accepted_terms=False,
        )
        with patch("backend.app.accounts.AUTH_CONFIGURED", True):
            with patch("backend.app.accounts.ENABLED_AUTH_METHODS", ("phone",)):
                with self.assertRaises(HTTPException) as context:
                    start_otp(payload)
        self.assertEqual(context.exception.status_code, 400)

    def test_verified_session_uses_http_only_cookies_and_records_consent(self):
        payload = OtpVerifyRequest(
            channel="email",
            contact="owner@example.com",
            intent="signup",
            accepted_terms=True,
            token="123456",
        )
        provider_response = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "user": {"id": "user-123", "email": "owner@example.com"},
        }
        response = Response()
        with (
            patch("backend.app.accounts.AUTH_CONFIGURED", True),
            patch("backend.app.accounts.ENABLED_AUTH_METHODS", ("email",)),
            patch("backend.app.accounts._request_json", return_value=provider_response),
            patch("backend.app.accounts._record_consent") as record_consent,
        ):
            result = verify_otp(payload, response)

        self.assertEqual(result["status"], "signed_in")
        self.assertEqual(result["user"]["identifier"], "ow***@example.com")
        record_consent.assert_called_once()
        cookie_headers = [
            value.decode("latin-1")
            for name, value in response.raw_headers
            if name.lower() == b"set-cookie"
        ]
        self.assertEqual(len(cookie_headers), 3)
        self.assertTrue(all("HttpOnly" in value for value in cookie_headers))
        self.assertTrue(any(value.startswith("fxguard_access=") for value in cookie_headers))
        self.assertTrue(any(value.startswith("fxguard_refresh=") for value in cookie_headers))

    def test_csrf_header_must_match_cookie(self):
        valid_request = Request({
            "type": "http",
            "headers": [
                (b"cookie", b"fxguard_csrf=matching-token"),
                (b"x-csrf-token", b"matching-token"),
            ],
        })
        _require_csrf(valid_request)

        invalid_request = Request({
            "type": "http",
            "headers": [
                (b"cookie", b"fxguard_csrf=cookie-token"),
                (b"x-csrf-token", b"different-token"),
            ],
        })
        with self.assertRaises(HTTPException) as context:
            _require_csrf(invalid_request)
        self.assertEqual(context.exception.status_code, 403)

    def test_database_migration_enforces_user_ownership(self):
        migration_dir = (
            Path(__file__).resolve().parents[1]
            / "supabase"
            / "migrations"
        )
        migration = (migration_dir / "001_accounts_and_checks.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("on delete cascade", migration.lower())
        self.assertIn("enable row level security", migration.lower())
        self.assertIn("auth.uid()", migration)
        self.assertIn("revoke all on public.payment_checks from anon", migration.lower())
        deletion_migration = (
            migration_dir / "002_self_service_account_deletion.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("where id = (select auth.uid())", deletion_migration.lower())
        self.assertIn("revoke all", deletion_migration.lower())
        self.assertIn("to authenticated", deletion_migration.lower())

    def test_account_deletion_uses_scoped_rpc_without_service_key(self):
        now = datetime.now(timezone.utc).isoformat()
        request = Request({
            "type": "http",
            "headers": [
                (
                    b"cookie",
                    b"fxguard_access=access-token; fxguard_csrf=matching-token",
                ),
                (b"x-csrf-token", b"matching-token"),
            ],
        })
        response = Response()
        user = {"id": "user-123", "last_sign_in_at": now}
        with (
            patch("backend.app.accounts.SUPABASE_SERVICE_ROLE_KEY", ""),
            patch("backend.app.accounts.SELF_DELETE_RPC_ENABLED", True),
            patch(
                "backend.app.accounts._user_with_session",
                return_value=(user, "access-token", "matching-token"),
            ),
            patch("backend.app.accounts._rest") as rest,
        ):
            result = delete_account(request, response)

        self.assertEqual(result["status"], "account_deleted")
        rest.assert_called_once_with(
            "rpc/delete_own_account",
            method="POST",
            payload={},
            access_token="access-token",
            prefer="return=minimal",
        )


if __name__ == "__main__":
    unittest.main()
