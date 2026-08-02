from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field


TERMS_VERSION = "1.0"
PRIVACY_VERSION = "1.0"

SUPPORTED_AUTH_METHODS = ("email", "phone")


def _usable_secret(value: str) -> str:
    cleaned = value.strip()
    lowered = cleaned.lower()
    if not cleaned or "your_" in lowered or "replace_" in lowered:
        return ""
    return cleaned


def _normalise_supabase_api_url(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    parsed = urllib.parse.urlparse(cleaned)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not hostname.endswith(".supabase.co"):
        return ""
    return cleaned


RAW_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_URL = _normalise_supabase_api_url(RAW_SUPABASE_URL)
SUPABASE_KEY = _usable_secret(
    os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    or os.getenv("SUPABASE_ANON_KEY", "")
)
SUPABASE_SERVICE_ROLE_KEY = _usable_secret(
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
)
SELF_DELETE_RPC_ENABLED = (
    os.getenv("AUTH_SELF_DELETE_RPC", "true").strip().lower() == "true"
)
ENABLED_AUTH_METHODS = tuple(
    method
    for method in (
        value.strip().lower()
        for value in os.getenv("AUTH_METHODS", "email").split(",")
    )
    if method in SUPPORTED_AUTH_METHODS
)
AUTH_CONFIGURED = bool(SUPABASE_URL and SUPABASE_KEY and ENABLED_AUTH_METHODS)

IS_DEPLOYED = bool(os.getenv("RENDER") or os.getenv("AUTH_COOKIE_SECURE") == "true")
COOKIE_SECURE = IS_DEPLOYED
COOKIE_SAMESITE = "none" if COOKIE_SECURE else "lax"
ACCESS_COOKIE = "fxguard_access"
REFRESH_COOKIE = "fxguard_refresh"
CSRF_COOKIE = "fxguard_csrf"

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")

router = APIRouter(prefix="/api", tags=["accounts"])


class OtpStartRequest(BaseModel):
    channel: Literal["email", "phone"]
    contact: str = Field(min_length=3, max_length=254)
    intent: Literal["signup", "signin"]
    accepted_terms: bool = False
    terms_version: str = TERMS_VERSION
    privacy_version: str = PRIVACY_VERSION


class OtpVerifyRequest(OtpStartRequest):
    token: str = Field(min_length=4, max_length=12)


class SavedCheckRequest(BaseModel):
    checked_at: datetime | None = None
    result: dict[str, Any]


def configured_origins() -> list[str]:
    configured = [
        value.strip().rstrip("/")
        for value in os.getenv("ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    ]
    defaults = [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "https://fxguard-ai-web.onrender.com",
        "https://fxguard-ai.onrender.com",
    ]
    return list(dict.fromkeys([*configured, *defaults]))


def _require_config() -> None:
    if not AUTH_CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail="Accounts are not connected yet. Guest payment checks are still available.",
        )


def _require_auth_method(channel: str) -> None:
    if channel not in ENABLED_AUTH_METHODS:
        raise HTTPException(
            status_code=503,
            detail=f"{channel.title()} sign-in is not enabled yet. Use an available sign-in method.",
        )


def _safe_provider_detail(raw: bytes, fallback: str) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return fallback
    if not isinstance(payload, dict):
        return fallback
    detail = payload.get("msg") or payload.get("message") or payload.get("error_description")
    return str(detail)[:240] if detail else fallback


def _request_json(
    path: str,
    *,
    method: str = "POST",
    payload: Any = None,
    access_token: str | None = None,
    service_role: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    _require_config()
    key = SUPABASE_SERVICE_ROLE_KEY if service_role else SUPABASE_KEY
    if service_role and not key:
        raise HTTPException(status_code=503, detail="Secure account deletion is not configured yet.")

    headers = {
        "apikey": key,
        "Accept": "application/json",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    elif service_role:
        headers["Authorization"] = f"Bearer {key}"
    if extra_headers:
        headers.update(extra_headers)

    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    request = urllib.request.Request(
        f"{SUPABASE_URL}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code if 400 <= exc.code < 500 else 502
        raise HTTPException(
            status_code=status,
            detail=_safe_provider_detail(raw, "The account service could not complete this request."),
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(
            status_code=502,
            detail="The account service is temporarily unavailable. Please try again.",
        ) from exc


def _normalise_contact(channel: str, contact: str) -> str:
    value = contact.strip()
    if channel == "email":
        value = value.lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise HTTPException(status_code=400, detail="Enter a valid email address.")
        return value

    value = re.sub(r"[\s()-]", "", value)
    if not PHONE_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail="Enter the phone number with its country code, for example +250 78 123 4567.",
        )
    return value


def _set_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def _set_session(response: Response, session: dict[str, Any]) -> str:
    access_token = str(session.get("access_token") or "")
    refresh_token = str(session.get("refresh_token") or "")
    if not access_token or not refresh_token:
        raise HTTPException(status_code=502, detail="The account session could not be created.")
    expires_in = max(300, int(session.get("expires_in") or 3600))
    csrf_token = secrets.token_urlsafe(32)
    _set_cookie(response, ACCESS_COOKIE, access_token, expires_in)
    _set_cookie(response, REFRESH_COOKIE, refresh_token, 60 * 60 * 24 * 30)
    _set_cookie(response, CSRF_COOKIE, csrf_token, 60 * 60 * 24 * 30)
    return csrf_token


def _clear_session(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name,
            path="/",
            secure=COOKIE_SECURE,
            httponly=True,
            samesite=COOKIE_SAMESITE,
        )


def _user_with_session(request: Request, response: Response) -> tuple[dict[str, Any], str, str]:
    _require_config()
    access_token = request.cookies.get(ACCESS_COOKIE, "")
    refresh_token = request.cookies.get(REFRESH_COOKIE, "")
    if not access_token:
        raise HTTPException(status_code=401, detail="Sign in to continue.")

    try:
        user = _request_json("/auth/v1/user", method="GET", access_token=access_token)
    except HTTPException as exc:
        if exc.status_code not in (401, 403) or not refresh_token:
            raise HTTPException(status_code=401, detail="Your session has ended. Sign in again.") from exc
        session = _request_json(
            "/auth/v1/token?grant_type=refresh_token",
            payload={"refresh_token": refresh_token},
        )
        access_token = str(session.get("access_token") or "")
        csrf_token = _set_session(response, session)
        user = _request_json("/auth/v1/user", method="GET", access_token=access_token)
        return user, access_token, csrf_token

    csrf_token = request.cookies.get(CSRF_COOKIE, "")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        _set_cookie(response, CSRF_COOKIE, csrf_token, 60 * 60 * 24 * 30)
    return user, access_token, csrf_token


def _require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="This request could not be verified. Refresh and try again.")


def _masked_identifier(user: dict[str, Any]) -> tuple[str, str]:
    email = str(user.get("email") or "")
    if email:
        local, _, domain = email.partition("@")
        visible = local[:2] if len(local) > 1 else local[:1]
        return "email", f"{visible}***@{domain}"
    phone = str(user.get("phone") or "")
    if phone:
        return "phone", f"{phone[:4]} *** {phone[-4:]}"
    return "account", "Signed-in account"


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    method, identifier = _masked_identifier(user)
    return {
        "id": user.get("id"),
        "method": method,
        "identifier": identifier,
        "created_at": user.get("created_at"),
    }


def _rest(
    path: str,
    *,
    method: str = "GET",
    payload: Any = None,
    access_token: str,
    prefer: str | None = None,
) -> Any:
    headers = {"Accept-Profile": "public", "Content-Profile": "public"}
    if prefer:
        headers["Prefer"] = prefer
    return _request_json(
        f"/rest/v1/{path}",
        method=method,
        payload=payload,
        access_token=access_token,
        extra_headers=headers,
    )


def _record_consent(
    user_id: str,
    access_token: str,
    request: OtpVerifyRequest,
    accepted_at: str | None = None,
) -> None:
    payload = {
        "user_id": user_id,
        "terms_version": request.terms_version,
        "privacy_version": request.privacy_version,
        "contact_method": request.channel,
        "accepted_at": accepted_at or datetime.now(timezone.utc).isoformat(),
    }
    _rest(
        "consent_records?on_conflict=user_id,terms_version,privacy_version",
        method="POST",
        payload=payload,
        access_token=access_token,
        prefer="resolution=merge-duplicates,return=minimal",
    )


def normalise_saved_check(payload: SavedCheckRequest, user_id: str) -> dict[str, Any]:
    result = payload.result
    encoded = json.dumps(result, separators=(",", ":"), default=str)
    if len(encoded.encode("utf-8")) > 100_000:
        raise HTTPException(status_code=400, detail="This result is too large to save.")

    currency = str(result.get("currency") or "").upper()
    if currency not in {"USD", "EUR", "KES"}:
        raise HTTPException(status_code=400, detail="This result has an unsupported currency.")
    horizon = int(result.get("horizon_days") or 0)
    if not 1 <= horizon <= 100:
        raise HTTPException(status_code=400, detail="This result has an unsupported period.")
    payment_date = str(result.get("payment_date") or "")
    if not payment_date:
        raise HTTPException(status_code=400, detail="This result has no payment date.")
    risk_level = str(result.get("risk_level") or "")
    if risk_level not in {"Low", "Medium", "High"}:
        raise HTTPException(status_code=400, detail="This result has an invalid risk level.")
    amount = float(result.get("amount") or result.get("amount_currency") or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="This result has an invalid invoice amount.")

    signature_source = f"{currency}|{amount:.4f}|{payment_date}"
    signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()
    checked_at = payload.checked_at or datetime.now(timezone.utc)
    return {
        "user_id": user_id,
        "signature": signature,
        "checked_at": checked_at.astimezone(timezone.utc).isoformat(),
        "currency": currency,
        "amount": amount,
        "horizon_days": horizon,
        "payment_date": payment_date,
        "risk_level": risk_level,
        "likelihood_probability": result.get("confidence_score", result.get("confidence")),
        "current_rate": result.get("current_rate"),
        "current_cost_rwf": result.get("current_cost_rwf"),
        "estimated_extra_cost_rwf": result.get("possible_extra_cost_rwf"),
        "rate_date": result.get("analysis_date"),
        "model_version": result.get("model_version"),
        "result": result,
    }


def _check_for_frontend(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "checkedAt": row.get("checked_at"),
        "amount": row.get("amount"),
        "currency": row.get("currency"),
        "horizon": row.get("horizon_days"),
        "paymentDate": (row.get("result") or {}).get("payment_date"),
        "risk": row.get("risk_level"),
        "cost": row.get("current_cost_rwf"),
        "extra": row.get("estimated_extra_cost_rwf"),
        "rate": row.get("current_rate"),
        "full": row.get("result"),
    }


@router.get("/auth/config")
def auth_config():
    configuration_message = None
    if not SUPABASE_URL and RAW_SUPABASE_URL.strip():
        configuration_message = (
            "The account service URL is invalid. Configure the HTTPS Supabase project URL."
        )
    elif not AUTH_CONFIGURED:
        configuration_message = (
            "Account connection is not ready. Guest payment checks remain available."
        )
    return {
        "enabled": AUTH_CONFIGURED,
        "methods": list(ENABLED_AUTH_METHODS) if AUTH_CONFIGURED else [],
        "registration_enabled": AUTH_CONFIGURED,
        "account_deletion_enabled": bool(
            AUTH_CONFIGURED
            and (SUPABASE_SERVICE_ROLE_KEY or SELF_DELETE_RPC_ENABLED)
        ),
        "message": configuration_message,
        "terms_version": TERMS_VERSION,
        "privacy_version": PRIVACY_VERSION,
    }


@router.post("/auth/otp/start")
def start_otp(payload: OtpStartRequest):
    _require_config()
    _require_auth_method(payload.channel)
    contact = _normalise_contact(payload.channel, payload.contact)
    if payload.intent == "signup":
        if not payload.accepted_terms:
            raise HTTPException(status_code=400, detail="Accept the Terms of Use and acknowledge the Privacy Notice to create an account.")
        if payload.terms_version != TERMS_VERSION or payload.privacy_version != PRIVACY_VERSION:
            raise HTTPException(status_code=409, detail="The legal notice has changed. Review it and try again.")

    body: dict[str, Any] = {
        payload.channel: contact,
        "create_user": payload.intent == "signup",
    }
    if payload.intent == "signup":
        body["data"] = {
            "terms_version": TERMS_VERSION,
            "privacy_version": PRIVACY_VERSION,
            "accepted_at": datetime.now(timezone.utc).isoformat(),
        }
    _request_json("/auth/v1/otp", payload=body)
    destination = "phone" if payload.channel == "phone" else "email"
    return {"status": "code_sent", "message": f"A sign-in code was sent to your {destination}."}


@router.post("/auth/otp/verify")
def verify_otp(payload: OtpVerifyRequest, response: Response):
    _require_config()
    _require_auth_method(payload.channel)
    contact = _normalise_contact(payload.channel, payload.contact)
    if payload.intent == "signup" and not payload.accepted_terms:
        raise HTTPException(status_code=400, detail="Account terms were not accepted.")
    verification = _request_json(
        "/auth/v1/verify",
        payload={
            payload.channel: contact,
            "token": payload.token.strip(),
            "type": "sms" if payload.channel == "phone" else "email",
        },
    )
    user = verification.get("user") or {}
    user_id = str(user.get("id") or "")
    access_token = str(verification.get("access_token") or "")
    if not user_id or not access_token:
        raise HTTPException(status_code=502, detail="The account could not be verified.")
    metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    has_current_acceptance = (
        metadata.get("terms_version") == TERMS_VERSION
        and metadata.get("privacy_version") == PRIVACY_VERSION
    )
    if payload.intent == "signup" or has_current_acceptance:
        _record_consent(user_id, access_token, payload, metadata.get("accepted_at"))
    csrf_token = _set_session(response, verification)
    return {"status": "signed_in", "user": _public_user(user), "csrf_token": csrf_token}


@router.get("/auth/session")
def auth_session(request: Request, response: Response):
    if not AUTH_CONFIGURED:
        return {"authenticated": False, "enabled": False}
    try:
        user, _, csrf_token = _user_with_session(request, response)
    except HTTPException as exc:
        if exc.status_code == 401:
            return {"authenticated": False, "enabled": True}
        raise
    return {
        "authenticated": True,
        "enabled": True,
        "user": _public_user(user),
        "csrf_token": csrf_token,
    }


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    _require_csrf(request)
    access_token = request.cookies.get(ACCESS_COOKIE, "")
    if access_token and AUTH_CONFIGURED:
        try:
            _request_json("/auth/v1/logout", access_token=access_token)
        except HTTPException:
            pass
    _clear_session(response)
    return {"status": "signed_out"}


@router.get("/checks")
def list_checks(request: Request, response: Response):
    user, access_token, csrf_token = _user_with_session(request, response)
    user_id = urllib.parse.quote(str(user["id"]), safe="")
    rows = _rest(
        f"payment_checks?user_id=eq.{user_id}&select=*&order=checked_at.desc&limit=50",
        access_token=access_token,
    ) or []
    return {"checks": [_check_for_frontend(row) for row in rows], "csrf_token": csrf_token}


@router.post("/checks")
def save_check(payload: SavedCheckRequest, request: Request, response: Response):
    _require_csrf(request)
    user, access_token, csrf_token = _user_with_session(request, response)
    record = normalise_saved_check(payload, str(user["id"]))
    rows = _rest(
        "payment_checks?on_conflict=user_id,signature",
        method="POST",
        payload=record,
        access_token=access_token,
        prefer="resolution=merge-duplicates,return=representation",
    ) or []
    return {"check": _check_for_frontend(rows[0]), "csrf_token": csrf_token}


@router.delete("/checks")
def clear_checks(request: Request, response: Response):
    _require_csrf(request)
    user, access_token, csrf_token = _user_with_session(request, response)
    user_id = urllib.parse.quote(str(user["id"]), safe="")
    _rest(
        f"payment_checks?user_id=eq.{user_id}",
        method="DELETE",
        access_token=access_token,
        prefer="return=minimal",
    )
    return {"status": "cleared", "csrf_token": csrf_token}


@router.delete("/checks/{check_id}")
def delete_check(check_id: str, request: Request, response: Response):
    _require_csrf(request)
    user, access_token, csrf_token = _user_with_session(request, response)
    query = urllib.parse.urlencode({"id": f"eq.{check_id}", "user_id": f"eq.{user['id']}"})
    _rest(
        f"payment_checks?{query}",
        method="DELETE",
        access_token=access_token,
        prefer="return=minimal",
    )
    return {"status": "deleted", "csrf_token": csrf_token}


@router.get("/account/export")
def export_account_data(request: Request, response: Response):
    user, access_token, csrf_token = _user_with_session(request, response)
    user_id = urllib.parse.quote(str(user["id"]), safe="")
    checks = _rest(
        f"payment_checks?user_id=eq.{user_id}&select=*&order=checked_at.desc",
        access_token=access_token,
    ) or []
    consents = _rest(
        f"consent_records?user_id=eq.{user_id}&select=*&order=accepted_at.desc",
        access_token=access_token,
    ) or []
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {
            "id": user.get("id"),
            "email": user.get("email"),
            "phone": user.get("phone"),
            "created_at": user.get("created_at"),
        },
        "checks": checks,
        "consent_records": consents,
        "csrf_token": csrf_token,
    }


@router.delete("/account")
def delete_account(request: Request, response: Response):
    _require_csrf(request)
    user, access_token, _ = _user_with_session(request, response)
    last_sign_in_raw = str(user.get("last_sign_in_at") or "")
    try:
        last_sign_in = datetime.fromisoformat(last_sign_in_raw.replace("Z", "+00:00"))
        seconds_since_sign_in = (datetime.now(timezone.utc) - last_sign_in).total_seconds()
    except (TypeError, ValueError):
        seconds_since_sign_in = float("inf")
    if seconds_since_sign_in > 10 * 60:
        raise HTTPException(
            status_code=403,
            detail="For your security, sign out and sign in again before deleting your account.",
        )
    user_id = urllib.parse.quote(str(user["id"]), safe="")
    if SUPABASE_SERVICE_ROLE_KEY:
        _request_json(
            f"/auth/v1/admin/users/{user_id}",
            method="DELETE",
            service_role=True,
        )
    elif SELF_DELETE_RPC_ENABLED:
        _rest(
            "rpc/delete_own_account",
            method="POST",
            payload={},
            access_token=access_token,
            prefer="return=minimal",
        )
    else:
        raise HTTPException(
            status_code=503,
            detail="Secure account deletion is not configured yet.",
        )
    _clear_session(response)
    return {"status": "account_deleted"}
