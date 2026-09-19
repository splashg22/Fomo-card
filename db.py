"""Mongo connection + tiny shared helpers. Deliberately minimal — Social Cash doesn't need a
receipt/ledger settlement stack, just somewhere to persist users, cards and top-ups."""
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "socialcash")

# A short server-selection timeout means a missing/unreachable Mongo fails in ~4s with a clear error
# instead of motor's 30s default, which just looks like the app hung.
client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=4000)
db = client[DB_NAME]


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
