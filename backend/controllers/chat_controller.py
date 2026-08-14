"""
Chat controller (MongoDB persistence + optional ML augmentation)
===============================================================
Stores chat history per user in MongoDB.

Schema (matches your request):
Chats collection:
- chat_id
- user_id
- messages: [{role, message, response, timestamp, meta?}]
- timestamps (we keep created_at/updated_at + per-message timestamp)
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from db.mongo import get_db
from services.chatbot_retrieval_service import get_service as get_chatbot_retrieval_service


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_chat_id() -> str:
    return "chat_" + secrets.token_urlsafe(16)


def get_or_create_active_chat(user_id: str) -> Dict:
    """
    Returns the user's most recently updated chat; creates one if none exists.
    """
    db = get_db()
    chat = db.chats.find_one({"user_id": user_id}, sort=[("updated_at", -1)])
    if chat:
        return chat

    doc = {
        "chat_id": _new_chat_id(),
        "user_id": user_id,
        "messages": [],
        "timestamps": [],
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    db.chats.insert_one(doc)
    return doc


def create_new_chat(user_id: str) -> Dict:
    db = get_db()
    doc = {
        "chat_id": _new_chat_id(),
        "user_id": user_id,
        "messages": [],
        "timestamps": [],
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    db.chats.insert_one(doc)
    return doc


def _build_prompt_messages(
    user_message: str,
    history: List[Dict],
    ml_context: Optional[Dict] = None,
) -> List[Dict[str, str]]:
    """
    Convert stored chat history to LLM messages.
    We keep it concise (last N turns).
    """
    system = (
        "You are MedCare AI, a helpful healthcare assistant.\n"
        "- Provide general health information and guidance.\n"
        "- Do NOT claim to be a doctor.\n"
        "- Do NOT provide definitive diagnoses.\n"
        "- If symptoms suggest emergency (chest pain, stroke signs, severe breathing trouble), urge immediate emergency services.\n"
        "- Be clear, structured, and empathetic.\n"
    )

    if ml_context and ml_context.get("predictions"):
        top = ml_context["predictions"][0]
        system += (
            "\nYou also have access to an ML symptom-based risk predictor.\n"
            f"Latest ML top prediction: {top.get('disease')} with confidence {top.get('confidence')}%.\n"
            "Use it as supportive context only (not a diagnosis)."
        )

    msgs: List[Dict[str, str]] = [{"role": "system", "content": system}]

    # Use last 10 turns max for context
    tail = history[-10:] if len(history) > 10 else history
    for item in tail:
        um = (item.get("message") or "").strip()
        ar = (item.get("response") or "").strip()
        if um:
            msgs.append({"role": "user", "content": um})
        if ar:
            msgs.append({"role": "assistant", "content": ar})

    msgs.append({"role": "user", "content": user_message})
    return msgs


def _maybe_predict_from_text(user_message: str, user_id: str) -> Optional[Dict]:
    """
    Optional integration: if the Intake NLP + prediction pipeline is available,
    normalize symptoms from free text and run ensemble prediction.
    """
    try:
        from services.intake_nlp_service import IntakeNLPService
        from services.prediction_service import PredictionService
    except Exception:
        return None

    try:
        symptoms = IntakeNLPService.normalize_symptoms(user_message)
        if not symptoms:
            return None
        pred = PredictionService().predict_from_symptoms(symptoms, patient_info=None, top_k=3)
        if not pred.get("success"):
            return None

        # Persist prediction record (action storage)
        db = get_db()
        db.predictions.insert_one(
            {
                "prediction_id": "pred_" + secrets.token_urlsafe(12),
                "user_id": user_id,
                "symptoms": symptoms,
                "predicted_disease": (pred.get("predictions") or [{}])[0].get("disease"),
                "confidence": (pred.get("predictions") or [{}])[0].get("confidence"),
                "predictions": pred.get("predictions", []),
                "timestamp": _utc_now(),
                "source": "chat",
            }
        )

        return pred
    except Exception:
        return None


def send_message(user_id: str, message: str, chat_id: Optional[str] = None) -> Dict:
    db = get_db()

    if chat_id:
        chat = db.chats.find_one({"chat_id": chat_id, "user_id": user_id})
        if not chat:
            chat = get_or_create_active_chat(user_id)
    else:
        chat = get_or_create_active_chat(user_id)

    history = chat.get("messages", [])

    # Optional ML augmentation
    ml_context = _maybe_predict_from_text(message, user_id=user_id)

    # Primary local response generation: retrieval over your train.csv dataset.
    retriever = get_chatbot_retrieval_service()
    retrieval = retriever.reply(message)

    timestamp = _utc_now()
    if not retrieval.success:
        assistant_text = retrieval.answer or ""
        error = (retrieval.meta or {}).get("error") or "retrieval_error"
        stored = {
            "user_id": user_id,
            "message": message,
            "response": assistant_text,
            "timestamp": timestamp,
            "meta": {"success": False, "error": error, "ml": bool(ml_context), "retrieval": True},
        }
        db.chats.update_one(
            {"_id": chat["_id"]},
            {"$push": {"messages": stored, "timestamps": timestamp}, "$set": {"updated_at": timestamp}},
        )
        return {
            "success": False,
            "error": error,
            "chat_id": chat["chat_id"],
            "timestamp": timestamp.isoformat(),
            "ml": ml_context,
        }

    assistant_text = retrieval.answer
    stored = {
        "user_id": user_id,
        "message": message,
        "response": assistant_text,
        "timestamp": timestamp,
        "meta": {
            "success": True,
            "provider": "local_retrieval",
            "ml": bool(ml_context),
            "retrieval": {
                "similarity": retrieval.similarity,
                "qtype": retrieval.matched_qtype,
            },
        },
    }

    db.chats.update_one(
        {"_id": chat["_id"]},
        {"$push": {"messages": stored, "timestamps": timestamp}, "$set": {"updated_at": timestamp}},
    )

    return {
        "success": True,
        "chat_id": chat["chat_id"],
        "user_id": user_id,
        "message": message,
        "response": assistant_text,
        "timestamp": timestamp.isoformat(),
        "ml": ml_context,
    }


def get_history(user_id: str, chat_id: Optional[str] = None, limit: int = 50) -> Dict:
    db = get_db()
    if chat_id:
        chat = db.chats.find_one({"chat_id": chat_id, "user_id": user_id})
    else:
        chat = db.chats.find_one({"user_id": user_id}, sort=[("updated_at", -1)])

    if not chat:
        chat = create_new_chat(user_id)

    messages = chat.get("messages", [])
    if limit and len(messages) > limit:
        messages = messages[-int(limit) :]

    # Convert timestamps for JSON
    out = []
    for m in messages:
        ts = m.get("timestamp")
        out.append(
            {
                "user_id": m.get("user_id"),
                "message": m.get("message"),
                "response": m.get("response"),
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else ts,
                "meta": m.get("meta", {}),
            }
        )

    return {
        "success": True,
        "chat": {
            "chat_id": chat.get("chat_id"),
            "user_id": chat.get("user_id"),
            "created_at": chat.get("created_at").isoformat() if hasattr(chat.get("created_at"), "isoformat") else None,
            "updated_at": chat.get("updated_at").isoformat() if hasattr(chat.get("updated_at"), "isoformat") else None,
            "messages": out,
        },
    }

