"""
Auth controller (signup/login) with bcrypt + JWT.
No fake email verification. Includes auth logging.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import bcrypt
import jwt

from db.mongo import get_db


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jwt_secret() -> str:
    return os.environ.get("JWT_SECRET_KEY", "medcare-ai-secret-key-change-in-production")


def _jwt_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256")


def _jwt_exp_hours() -> int:
    try:
        return int(os.environ.get("JWT_EXPIRATION_HOURS", "24"))
    except Exception:
        return 24


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def _generate_user_id() -> str:
    # short URL-safe id (not guessable enough alone; still treat as identifier)
    return "usr_" + secrets.token_urlsafe(16)


def _issue_token(user: Dict) -> str:
    payload = {
        "user_id": user["user_id"],
        "email": user["email"],
        "role": user.get("role", "user"),
        "iat": int(_utc_now().timestamp()),
        "exp": int((_utc_now() + timedelta(hours=_jwt_exp_hours())).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def log_auth_event(
    user_id: Optional[str],
    event: str,
    success: bool,
    meta: Optional[Dict] = None,
) -> None:
    db = get_db()
    db.auth_logs.insert_one(
        {
            "user_id": user_id,
            "event": event,
            "success": bool(success),
            "meta": meta or {},
            "timestamp": _utc_now(),
        }
    )


def signup(name: str, email: str, password: str, role: str = "user") -> Dict:
    db = get_db()
    email_norm = (email or "").strip().lower()
    if role not in ("user", "admin"):
        role = "user"

    existing = db.users.find_one({"email": email_norm})
    if existing:
        return {"success": False, "error": "Email already registered"}

    user = {
        "user_id": _generate_user_id(),
        "name": (name or "").strip(),
        "email": email_norm,
        "password_hash": _hash_password(password),
        "role": role,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    db.users.insert_one(user)
    log_auth_event(user["user_id"], "signup", True, {"role": role})

    token = _issue_token(user)
    return {
        "success": True,
        "user": {"user_id": user["user_id"], "name": user["name"], "email": user["email"], "role": user["role"]},
        "token": token,
    }


def login(email: str, password: str, device_info: Optional[Dict] = None) -> Dict:
    db = get_db()
    email_norm = (email or "").strip().lower()
    user = db.users.find_one({"email": email_norm})
    if not user:
        log_auth_event(None, "login", False, {"email": email_norm, "reason": "not_found", "device": device_info or {}})
        return {"success": False, "error": "Invalid email or password"}

    if not _verify_password(password or "", user.get("password_hash", "")):
        log_auth_event(user.get("user_id"), "login", False, {"reason": "bad_password", "device": device_info or {}})
        return {"success": False, "error": "Invalid email or password"}

    log_auth_event(user["user_id"], "login", True, {"device": device_info or {}})
    token = _issue_token(user)
    return {
        "success": True,
        "user": {"user_id": user["user_id"], "name": user.get("name", ""), "email": user["email"], "role": user.get("role", "user")},
        "token": token,
    }

