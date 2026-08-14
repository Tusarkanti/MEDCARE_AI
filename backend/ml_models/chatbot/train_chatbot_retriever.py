"""
Train local chatbot retriever model from train.csv
=====================================================
Produces artifacts under:
  backend/ml_models/chatbot/artifacts/

Run:
  python backend/ml_models/chatbot/train_chatbot_retriever.py
"""

from __future__ import annotations

import os
import joblib
import argparse
import numpy as np
import pandas as pd

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from scipy.sparse import hstack


def train(train_csv_path: str, artifacts_dir: str) -> None:
    os.makedirs(artifacts_dir, exist_ok=True)

    df = pd.read_csv(train_csv_path)
    required = ["qtype", "Question", "Answer"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"train.csv missing columns: {missing}")

    df = df.dropna(subset=["Question", "Answer", "qtype"]).copy()
    df["Question"] = df["Question"].astype(str).str.strip()
    df["Answer"] = df["Answer"].astype(str).str.strip()
    df["qtype"] = df["qtype"].astype(str).str.strip()

    questions = df["Question"].tolist()
    answers = df["Answer"].tolist()
    qtypes = df["qtype"].tolist()

    # Word TF-IDF
    vec_word = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        stop_words="english",
        max_features=int(os.environ.get("CHATBOT_WORD_MAX_FEATURES", "60000")),
        sublinear_tf=True,
        norm="l2",
    )
    X_word = vec_word.fit_transform(questions)

    # Char TF-IDF helps with misspellings/variations.
    vec_char = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        max_features=int(os.environ.get("CHATBOT_CHAR_MAX_FEATURES", "80000")),
        sublinear_tf=True,
        norm="l2",
    )
    X_char = vec_char.fit_transform(questions)

    X = hstack([X_word, X_char]).tocsr()

    # Heuristic threshold: adjust later based on evaluation.
    threshold = float(os.environ.get("CHATBOT_SIMILARITY_THRESHOLD", "0.15"))

    # Save artifacts
    joblib.dump(vec_word, os.path.join(artifacts_dir, "vectorizer_word.joblib"), compress=3)
    joblib.dump(vec_char, os.path.join(artifacts_dir, "vectorizer_char.joblib"), compress=3)
    joblib.dump(X, os.path.join(artifacts_dir, "X_tfidf.joblib"), compress=3)
    joblib.dump(answers, os.path.join(artifacts_dir, "answers.joblib"), compress=3)
    joblib.dump(questions, os.path.join(artifacts_dir, "questions.joblib"), compress=3)
    joblib.dump(qtypes, os.path.join(artifacts_dir, "qtypes.joblib"), compress=3)
    joblib.dump(threshold, os.path.join(artifacts_dir, "threshold.joblib"), compress=3)

    print("OK: Chatbot retriever trained")
    print(f"   N questions: {len(questions)}")
    print(f"   Word features: {X_word.shape[1]} | Char features: {X_char.shape[1]}")
    print(f"   Combined matrix shape: {X.shape}")
    print(f"   Similarity threshold: {threshold}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train_csv", default="backend/data/train.csv")
    parser.add_argument("--artifacts_dir", default="backend/ml_models/chatbot/artifacts")
    args = parser.parse_args()

    train(args.train_csv, args.artifacts_dir)

