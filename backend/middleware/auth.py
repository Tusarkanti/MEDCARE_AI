"""
JWT auth + role protection middleware.
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Callable, Dict, Optional

import jwt
from flask import request, jsonify, g


def _jwt_secret() -> str:
    return os.environ.get("JWT_SECRET_KEY", "medcare-ai-secret-key-change-in-production")


def _jwt_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "HS256")


def extract_bearer_token() -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    return token or None


def decode_token(token: str) -> Optional[Dict]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[_jwt_algorithm()])
    except Exception:
        return None


def auth_required(fn: Callable):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Let browser CORS preflight pass without JWT checks.
        if request.method == "OPTIONS":
            return "", 204
        token = extract_bearer_token()
        if not token:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        payload = decode_token(token)
        if not payload:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        g.user_id = payload.get("user_id")
        g.email = payload.get("email")
        g.role = payload.get("role", "user")
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn: Callable):
    @auth_required
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(g, "role", "user") != "admin":
            return jsonify({"success": False, "error": "Forbidden"}), 403
        return fn(*args, **kwargs)

    return wrapper

