"""
Chat routes (v2) - real LLM + Mongo persistence.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request, g

from controllers.chat_controller import create_new_chat, get_history, send_message
from middleware.auth import auth_required


chat_bp = Blueprint("chat_v2", __name__, url_prefix="/api/v2/chat")


@chat_bp.get("/history")
@auth_required
def history():
    chat_id = request.args.get("chat_id")
    limit = int(request.args.get("limit", 50))
    result = get_history(user_id=g.user_id, chat_id=chat_id, limit=limit)
    return jsonify(result)


@chat_bp.post("/new")
@auth_required
def new_chat():
    chat = create_new_chat(g.user_id)
    return jsonify({"success": True, "chat_id": chat["chat_id"]})


@chat_bp.post("/send")
@auth_required
def send():
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    chat_id = data.get("chat_id")
    if not message:
        return jsonify({"success": False, "error": "message is required"}), 400

    result = send_message(user_id=g.user_id, message=message, chat_id=chat_id)
    return jsonify(result), (200 if result.get("success") else 502)

