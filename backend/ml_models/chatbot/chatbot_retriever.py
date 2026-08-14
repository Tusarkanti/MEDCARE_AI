"""
Local chatbot retriever model (trained from your train.csv)
==============================================================
This is a real trained ML model:
- TF-IDF (word + char ngrams) over the CSV questions
- Cosine similarity retrieval to select the best matching answer

No external LLM calls are required.
"""

from __future__ import annotations

import os
import joblib
import numpy as np

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from scipy.sparse import hstack, issparse


@dataclass
class RetrievalResult:
    success: bool
    answer: str = ""
    matched_question: str = ""
    matched_qtype: str = ""
    similarity: float = 0.0
    threshold: float = 0.0
    meta: Dict[str, Any] = None


class ChatbotRetriever:
    def __init__(self, artifacts_dir: str):
        self.artifacts_dir = artifacts_dir
        self.is_loaded = False
        self.error: Optional[str] = None

        self.vectorizer_word = None
        self.vectorizer_char = None
        self.X = None  # combined TF-IDF matrix for all questions
        self.answers: List[str] = []
        self.questions: List[str] = []
        self.qtypes: List[str] = []
        self.threshold: float = 0.15

    def load(self) -> bool:
        try:
            self.vectorizer_word = joblib.load(os.path.join(self.artifacts_dir, "vectorizer_word.joblib"))
            self.vectorizer_char = joblib.load(os.path.join(self.artifacts_dir, "vectorizer_char.joblib"))
            self.X = joblib.load(os.path.join(self.artifacts_dir, "X_tfidf.joblib"))
            self.answers = joblib.load(os.path.join(self.artifacts_dir, "answers.joblib"))
            self.questions = joblib.load(os.path.join(self.artifacts_dir, "questions.joblib"))
            self.qtypes = joblib.load(os.path.join(self.artifacts_dir, "qtypes.joblib"))
            self.threshold = float(joblib.load(os.path.join(self.artifacts_dir, "threshold.joblib")))

            if not issparse(self.X):
                # We expect sparse matrix, but keep a safe path.
                self.X = np.asarray(self.X)

            self.is_loaded = True
            return True
        except Exception as e:
            self.error = str(e)
            self.is_loaded = False
            return False

    def answer(self, user_message: str) -> RetrievalResult:
        if not self.is_loaded:
            return RetrievalResult(success=False, meta={"error": self.error})

        q = (user_message or "").strip()
        if not q:
            return RetrievalResult(success=False, meta={"error": "empty_input"})

        q_word = self.vectorizer_word.transform([q])
        q_char = self.vectorizer_char.transform([q])
        q_vec = hstack([q_word, q_char])

        # cosine similarity via dot product (TF-IDF default L2 normalization)
        scores = self.X.dot(q_vec.T)
        if hasattr(scores, "toarray"):
            scores = scores.toarray()
        scores = np.asarray(scores).reshape(-1)

        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx]) if scores.size else 0.0

        ans = self.answers[best_idx] if self.answers else ""
        mq = self.questions[best_idx] if self.questions else ""
        mqt = self.qtypes[best_idx] if self.qtypes else ""

        if best_score < self.threshold:
            fallback = (
                "I couldn't find an exact match for your question in the knowledge base I was trained on. "
                "For safe guidance, please consult a healthcare professional."
            )
            return RetrievalResult(
                success=True,
                answer=fallback,
                matched_question=mq,
                matched_qtype=mqt,
                similarity=best_score,
                threshold=self.threshold,
                meta={"retrieval":"fallback_low_similarity"},
            )

        return RetrievalResult(
            success=True,
            answer=ans,
            matched_question=mq,
            matched_qtype=mqt,
            similarity=best_score,
            threshold=self.threshold,
            meta={"retrieval":"exact_match_by_similarity"},
        )

