"""Social Cash — standalone entrypoint.

Run locally with: uvicorn main:app --reload --port 8000
"""
import logging
import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

import pages
import socialcash
from card_issuer import get_issuer
from db import MONGO_URL, db

app = FastAPI(
    title="Social Cash",
    description="An independent, unofficial facilitator that lets FOMO and Pump.fun traders spend "
                "their balance on a real card. Not affiliated with, endorsed by, or operated by "
                "FOMO Labs or Pump.fun.",
)

app.include_router(socialcash.router)
app.include_router(pages.router)

app.add_middleware(
    CORSMiddleware,
    # No cookies/sessions anywhere in this app — every write is authenticated per-request by a wallet
    # signature — so there's no credentialed state for allow_credentials to protect, and pairing it
    # with a wildcard origin is a combination browsers themselves reject as insecure.
    allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("socialcash")


@app.on_event("startup")
async def startup():
    try:
        await db.socialcash_users.create_index([("platform", 1), ("identity", 1)], unique=True)
        await db.socialcash_cards.create_index("issuer_card_id", unique=True)
        await db.socialcash_cards.create_index([("platform", 1), ("identity", 1)])
        await db.socialcash_topups.create_index("id", unique=True)
        await db.socialcash_topups.create_index([("platform", 1), ("identity", 1)])
    except Exception as e:
        raise RuntimeError(
            f"Could not reach MongoDB at {MONGO_URL} — is it running? Start one with "
            "`docker run -d -p 27017:27017 mongo:7`, or point MONGO_URL (in .env) at a reachable "
            "instance, e.g. a free MongoDB Atlas cluster. See README.md > Setup."
        ) from e
    logger.info("Social Cash up — issuer=%s", get_issuer().name)


@app.on_event("shutdown")
async def shutdown():
    db.client.close()
