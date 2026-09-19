"""Mongo connection + tiny shared helpers. Deliberately minimal — FOMO Card doesn't need a
receipt/ledger settlement stack, just somewhere to persist users, cards and top-ups."""
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "fomocard")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
