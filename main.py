"""FOMO Card — standalone entrypoint.

Run locally with: uvicorn main:app --reload --port 8000
"""
import logging
import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

import fomocard
import pages
from card_issuer import get_issuer
from db import db

app = FastAPI(
    title="FOMO Card",
    description="An independent, unofficial no-KYC crypto spend card layer for fomo.family traders. "
                "Not affiliated with, endorsed by, or operated by FOMO Labs.",
)

app.include_router(fomocard.router)
app.include_router(pages.router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("fomocard")


@app.on_event("startup")
async def startup():
    await db.fomocard_users.create_index("handle", unique=True)
    await db.fomocard_cards.create_index("issuer_card_id", unique=True)
    await db.fomocard_cards.create_index("handle")
    await db.fomocard_topups.create_index("id", unique=True)
    await db.fomocard_topups.create_index("handle")
    logger.info("FOMO Card up — issuer=%s", get_issuer().name)


@app.on_event("shutdown")
async def shutdown():
    db.client.close()
