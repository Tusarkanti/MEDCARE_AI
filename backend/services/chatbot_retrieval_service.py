"""
Chatbot retrieval service (no external API)
==============================================
Uses the trained TF-IDF retriever over backend/data/train.csv.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ml_models.chatbot.chatbot_retriever import ChatbotRetriever


_service: Optional["ChatbotRetrievalService"] = None


def get_service() -> "ChatbotRetrievalService":
    global _service
    if _service is None:
        _service = ChatbotRetrievalService()
    return _service


@dataclass
class ChatbotAnswer:
    success: bool
    answer: str
    similarity: float = 0.0
    matched_question: str = ""
    matched_qtype: str = ""
    meta: Dict[str, Any] = None


class ChatbotRetrievalService:
    def __init__(self):
        artifacts_dir = os.environ.get(
            "CHATBOT_ARTIFACTS_DIR",
            os.path.join(os.path.dirname(__file__), "..", "ml_models", "chatbot", "artifacts"),
        )
        self.retriever = ChatbotRetriever(artifacts_dir=artifacts_dir)
        self.loaded = self.retriever.load()

    def is_loaded(self) -> bool:
        return self.loaded

    def reply(self, user_message: str) -> ChatbotAnswer:
        if not self.loaded:
            return ChatbotAnswer(
                success=False,
                answer="Chat knowledge base is not available. Please try again later.",
                meta={"error": self.retriever.error},
            )

        res = self.retriever.answer(user_message)
        if not res.success:
            return ChatbotAnswer(success=False, answer="Could not generate a response.", meta=res.meta or {})

        return ChatbotAnswer(
            success=True,
            answer=res.answer,
            similarity=float(res.similarity),
            matched_question=res.matched_question,
            matched_qtype=res.matched_qtype,
            meta=res.meta or {},
        )

