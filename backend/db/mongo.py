"""
MongoDB connection + indexes (production-style)
==============================================
Central place for MongoDB connection and collection setup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from pymongo import MongoClient, ASCENDING, DESCENDING


@dataclass(frozen=True)
class MongoConfig:
    uri: str
    db_name: str


_client: Optional[MongoClient] = None
_db = None


def get_mongo_config() -> MongoConfig:
    return MongoConfig(
        uri=os.environ.get("MONGO_URI", "mongodb://localhost:27017"),
        db_name=os.environ.get("MONGO_DB_NAME", "medcare_ai"),
    )


def get_client() -> MongoClient:
    global _client
    if _client is None:
        cfg = get_mongo_config()
        _client = MongoClient(cfg.uri)
    return _client


def get_db():
    global _db
    if _db is None:
        cfg = get_mongo_config()
        _db = get_client()[cfg.db_name]
    return _db


def init_indexes() -> None:
    """
    Create indexes used by the production-style routes.
    Safe to call multiple times.
    """
    db = get_db()

    # Users
    db.users.create_index([("user_id", ASCENDING)], unique=True)
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.users.create_index([("role", ASCENDING), ("created_at", DESCENDING)])

    # Chats
    db.chats.create_index([("chat_id", ASCENDING)], unique=True)
    db.chats.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])

    # Predictions
    db.predictions.create_index([("prediction_id", ASCENDING)], unique=True)
    db.predictions.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])
    db.predictions.create_index([("predicted_disease", ASCENDING), ("timestamp", DESCENDING)])

    # Vitals
    db.vitals.create_index([("vital_id", ASCENDING)], unique=True)
    db.vitals.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])

    # Auth logs
    db.auth_logs.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])
    db.auth_logs.create_index([("event", ASCENDING), ("timestamp", DESCENDING)])

