"""
Auth routes (v2) - production-style blueprint.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from controllers.auth_controller import login as login_fn
from controllers.auth_controller import signup as signup_fn


auth_bp = Blueprint("auth_v2", __name__, url_prefix="/api/v2/auth")


@auth_bp.post("/signup")
def signup():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"success": False, "error": "name, email, password are required"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

    # Security: never allow creating admin from public signup
    result = signup_fn(name=name, email=email, password=password, role="user")
    return jsonify(result), (200 if result.get("success") else 400)


@auth_bp.post("/login")
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    device_info = data.get("device_info") or {}

    if not email or not password:
        return jsonify({"success": False, "error": "email and password are required"}), 400

    result = login_fn(email=email, password=password, device_info=device_info)
    return jsonify(result), (200 if result.get("success") else 401)

