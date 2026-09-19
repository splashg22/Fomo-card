"""FOMO Card — an independent, unofficial spend layer for fomo.family traders.

Not affiliated with, endorsed by, or operated by FOMO Labs. Resolves a FOMO handle to its linked
wallets via fomoapi.io, lets the user send USDC/SOL/USDT from that wallet straight to a no-KYC card
issuer's deposit address, and turns a confirmed deposit into a funded virtual card with Apple Pay /
Google Pay provisioning. FOMO Card never custodies funds: the on-chain transfer goes user -> issuer
directly, and the issuer (see card_issuer.py) is the only place the money ever sits.

Only issuer_card_id, last4, brand, expiry and status are ever stored here — a PAN/CVV reveal is
proxied straight through to the caller and never written to fomocard_cards.
"""
import time
from collections import defaultdict, deque

import base58
import nacl.signing
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import onchain
from card_issuer import IssuerError, get_issuer
from db import db, new_id, utcnow_iso
from fomo_client import configured as fomoapi_configured
from fomo_client import get_balances, resolve_handle

router = APIRouter(prefix="/api", tags=["fomocard"])

MIN_TOPUP_USD = 5.0
MAX_TOPUP_USD = 1000.0   # typical single-transaction ceiling on a no-KYC card tier
MAX_DAILY_USD = 2000.0   # typical no-KYC daily ceiling — TODO tune to your issuer's real program limits
SUPPORTED_ASSETS = {"USDC", "SOL", "USDT"}

_hits: dict[str, deque] = defaultdict(deque)


def _rate_limited(key: str, max_calls: int, window_sec: float) -> bool:
    """In-process sliding-window limiter. Good enough for a single-instance MVP; swap for a shared
    store (Redis) before running more than one backend worker."""
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > window_sec:
        q.popleft()
    if len(q) >= max_calls:
        return True
    q.append(now)
    return False


def _clean_handle(h: str) -> str:
    return (h or "").strip().lstrip("@").lower()


def _norm_wallet(address: str, chain: str) -> str:
    a = (address or "").strip()
    return a.lower() if chain == "evm" else a  # Solana addresses are base58 and case-sensitive


def connect_message(handle: str, address: str) -> str:
    return f"FOMO Card · link {address} to @{handle}"


def _verify_evm(address: str, message: str, signature: str) -> bool:
    try:
        recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception:
        return False
    return recovered.lower() == address.lower()


def _verify_solana(address: str, message: str, signature: str) -> bool:
    try:
        pubkey = base58.b58decode(address)
        sig = bytes.fromhex(signature[2:]) if signature.startswith("0x") else base58.b58decode(signature)
        nacl.signing.VerifyKey(pubkey).verify(message.encode(), sig)
        return True
    except Exception:
        return False


def verify_wallet_signature(chain: str, address: str, message: str, signature: str) -> bool:
    if chain == "evm":
        return _verify_evm(address, message, signature)
    if chain == "solana":
        return _verify_solana(address, message, signature)
    return False


class ConnectRequest(BaseModel):
    handle: str = Field(min_length=1, max_length=40)
    address: str = Field(min_length=8, max_length=64)
    chain: str = Field(pattern="^(solana|evm)$")
    signature: str = Field(min_length=8, max_length=256)
    label: str = Field(default="", max_length=40)


class TopupRequest(BaseModel):
    handle: str
    amount_usd: float = Field(gt=0)
    asset: str
    chain: str = Field(pattern="^(solana|evm)$")


class ConfirmRequest(BaseModel):
    tx_hash: str = Field(min_length=6, max_length=128)


class HandleOnly(BaseModel):
    handle: str


@router.get("/config")
async def config():
    issuer = get_issuer()
    return {
        "issuer": issuer.name,
        "demo_mode": issuer.name == "demo",
        "fomoapi_configured": fomoapi_configured(),
        "min_topup_usd": MIN_TOPUP_USD, "max_topup_usd": MAX_TOPUP_USD, "max_daily_usd": MAX_DAILY_USD,
        "supported_assets": sorted(SUPPORTED_ASSETS),
        "disclaimer": "FOMO Card is an independent product built for fomo.family traders. It is not "
                      "affiliated with, endorsed by, or operated by FOMO Labs.",
    }


@router.post("/connect")
async def connect(body: ConnectRequest):
    handle = _clean_handle(body.handle)
    if not handle:
        raise HTTPException(422, "handle required")
    if _rate_limited(f"connect:{handle}", 10, 60):
        raise HTTPException(429, "too many connect attempts — try again in a minute")
    address = _norm_wallet(body.address, body.chain)
    message = connect_message(handle, address)
    if not verify_wallet_signature(body.chain, address, message, body.signature):
        raise HTTPException(401, "signature does not match — sign exactly: " + message)
    profile = await resolve_handle(handle)
    doc = {
        "handle": handle, "label": body.label.strip()[:40],
        "wallet_chain": body.chain, "wallet_address": address,
        "fomo_wallets": profile.get("wallets", {}),
        "demo_profile": bool(profile.get("demo")),
        "connected_at": utcnow_iso(), "updated_at": utcnow_iso(),
    }
    await db.fomocard_users.update_one({"handle": handle}, {"$set": doc}, upsert=True)
    balances = await get_balances(handle)
    return {"user": doc, "balances": balances}


@router.get("/profile")
async def profile(handle: str):
    handle = _clean_handle(handle)
    user = await db.fomocard_users.find_one({"handle": handle}, {"_id": 0})
    if not user:
        raise HTTPException(404, "connect this FOMO handle first")
    balances = await get_balances(handle)
    cards = await db.fomocard_cards.find({"handle": handle}, {"_id": 0, "pan": 0, "cvv": 0}).to_list(10)
    return {"user": user, "balances": balances, "cards": cards}


@router.post("/topups")
async def create_topup(body: TopupRequest):
    handle = _clean_handle(body.handle)
    user = await db.fomocard_users.find_one({"handle": handle})
    if not user:
        raise HTTPException(404, "connect this FOMO handle first")
    if _rate_limited(f"topup:{handle}", 6, 60):
        raise HTTPException(429, "too many top-up attempts — try again in a minute")
    asset = body.asset.strip().upper()
    if asset not in SUPPORTED_ASSETS:
        raise HTTPException(422, f"unsupported asset — use one of {sorted(SUPPORTED_ASSETS)}")
    if not (MIN_TOPUP_USD <= body.amount_usd <= MAX_TOPUP_USD):
        raise HTTPException(422, f"amount must be between ${MIN_TOPUP_USD:g} and ${MAX_TOPUP_USD:g} on this no-KYC tier")
    since = utcnow_iso()[:10]
    day_total = 0.0
    async for t in db.fomocard_topups.find({"handle": handle, "status": "funded", "created_at": {"$gte": since}}, {"amount_usd": 1}):
        day_total += t.get("amount_usd", 0)
    if day_total + body.amount_usd > MAX_DAILY_USD:
        raise HTTPException(422, f"daily no-KYC limit reached (${MAX_DAILY_USD:g}/day) — try a smaller amount or again tomorrow")
    issuer = get_issuer()
    try:
        deposit_address = await issuer.deposit_address(asset, body.chain)
    except IssuerError as e:
        raise HTTPException(502, f"issuer unavailable: {e}")
    topup = {
        "id": new_id(), "handle": handle, "amount_usd": round(body.amount_usd, 2),
        "asset": asset, "chain": body.chain, "deposit_address": deposit_address,
        "status": "pending_deposit", "tx_hash": None,
        "created_at": utcnow_iso(), "updated_at": utcnow_iso(),
    }
    await db.fomocard_topups.insert_one(dict(topup))
    return {
        "topup": topup,
        "instructions": f"Send exactly {body.amount_usd:g} USD of {asset} on {body.chain} to {deposit_address}, "
                        f"then confirm below with the transaction hash.",
    }


@router.post("/topups/{topup_id}/confirm")
async def confirm_topup(topup_id: str, body: ConfirmRequest):
    topup = await db.fomocard_topups.find_one({"id": topup_id}, {"_id": 0})
    if not topup:
        raise HTTPException(404, "no such top-up")
    if topup["status"] == "funded":
        return {"topup": topup, "already_funded": True}
    if topup["status"] not in ("pending_deposit", "awaiting_confirmation"):
        raise HTTPException(409, f"top-up is {topup['status']}, cannot confirm")
    handle = topup["handle"]
    if _rate_limited(f"confirm:{handle}", 10, 60):
        raise HTTPException(429, "too many confirm attempts — try again in a minute")

    confirmed = await onchain.tx_confirmed(topup["chain"], body.tx_hash)
    issuer = get_issuer()
    demo_mode = issuer.name == "demo"
    if confirmed is False:
        raise HTTPException(400, "that transaction was not found or failed on-chain")
    if confirmed is None and not demo_mode:
        # a real deployment should wait for the issuer's own webhook before crediting a card; the RPC
        # check here is only a best-effort corroboration, not the source of truth.
        await db.fomocard_topups.update_one({"id": topup_id}, {"$set": {
            "tx_hash": body.tx_hash, "status": "awaiting_confirmation", "updated_at": utcnow_iso()}})
        return {
            "topup": {**topup, "status": "awaiting_confirmation", "tx_hash": body.tx_hash},
            "note": "could not verify this transaction on-chain yet — it will finalize via the issuer's webhook",
        }

    card = await db.fomocard_cards.find_one({"handle": handle}, {"_id": 0})
    try:
        if not card:
            issued = await issuer.create_card(handle, f"FOMO Card · @{handle}")
            card = {**issued, "handle": handle, "created_at": utcnow_iso(), "updated_at": utcnow_iso()}
            await db.fomocard_cards.insert_one(dict(card))
        funded = await issuer.fund_card(card["issuer_card_id"], topup["amount_usd"], topup["asset"], body.tx_hash)
    except IssuerError as e:
        raise HTTPException(502, f"issuer funding failed: {e}")

    await db.fomocard_cards.update_one(
        {"issuer_card_id": card["issuer_card_id"]},
        {"$inc": {"balance_usd": topup["amount_usd"]}, "$set": {"status": "active", "updated_at": utcnow_iso()}},
    )
    await db.fomocard_topups.update_one(
        {"id": topup_id}, {"$set": {"tx_hash": body.tx_hash, "status": "funded", "updated_at": utcnow_iso()}})
    card = await db.fomocard_cards.find_one({"issuer_card_id": card["issuer_card_id"]}, {"_id": 0, "pan": 0, "cvv": 0})
    topup = await db.fomocard_topups.find_one({"id": topup_id}, {"_id": 0})
    return {"topup": topup, "card": card, "funded": funded}


@router.get("/topups")
async def list_topups(handle: str, limit: int = 30):
    handle = _clean_handle(handle)
    rows = await db.fomocard_topups.find({"handle": handle}, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 100))
    return {"topups": rows}


@router.get("/cards")
async def list_cards(handle: str):
    handle = _clean_handle(handle)
    rows = await db.fomocard_cards.find({"handle": handle}, {"_id": 0, "pan": 0, "cvv": 0}).to_list(10)
    return {"cards": rows}


@router.post("/cards/{issuer_card_id}/reveal")
async def reveal_card(issuer_card_id: str, body: HandleOnly):
    handle = _clean_handle(body.handle)
    card = await db.fomocard_cards.find_one({"issuer_card_id": issuer_card_id, "handle": handle})
    if not card:
        raise HTTPException(404, "card not found for this handle")
    if _rate_limited(f"reveal:{handle}", 3, 3600):
        raise HTTPException(429, "too many reveal attempts — try again later")
    try:
        secret = await get_issuer().reveal(issuer_card_id)
    except IssuerError as e:
        raise HTTPException(502, f"issuer reveal failed: {e}")
    await db.fomocard_events.insert_one({
        "id": new_id(), "handle": handle, "issuer_card_id": issuer_card_id,
        "kind": "pan_revealed", "created_at": utcnow_iso(),
    })
    return secret  # single-use — the client shows this once and discards it; nothing sensitive is stored


async def _set_frozen(issuer_card_id: str, handle: str, frozen: bool) -> dict:
    handle = _clean_handle(handle)
    card = await db.fomocard_cards.find_one({"issuer_card_id": issuer_card_id, "handle": handle})
    if not card:
        raise HTTPException(404, "card not found for this handle")
    try:
        result = await get_issuer().set_frozen(issuer_card_id, frozen)
    except IssuerError as e:
        raise HTTPException(502, f"issuer request failed: {e}")
    status = result.get("status", "frozen" if frozen else "active")
    await db.fomocard_cards.update_one({"issuer_card_id": issuer_card_id}, {"$set": {"status": status, "updated_at": utcnow_iso()}})
    return {"issuer_card_id": issuer_card_id, "status": status}


@router.post("/cards/{issuer_card_id}/freeze")
async def freeze_card(issuer_card_id: str, body: HandleOnly):
    return await _set_frozen(issuer_card_id, body.handle, True)


@router.post("/cards/{issuer_card_id}/unfreeze")
async def unfreeze_card(issuer_card_id: str, body: HandleOnly):
    return await _set_frozen(issuer_card_id, body.handle, False)


async def _provision(issuer_card_id: str, handle: str, wallet: str) -> dict:
    handle = _clean_handle(handle)
    card = await db.fomocard_cards.find_one({"issuer_card_id": issuer_card_id, "handle": handle})
    if not card:
        raise HTTPException(404, "card not found for this handle")
    try:
        return await get_issuer().provision(issuer_card_id, wallet)
    except IssuerError as e:
        raise HTTPException(502, f"issuer request failed: {e}")


@router.get("/cards/{issuer_card_id}/apple-pay")
async def apple_pay(issuer_card_id: str, handle: str):
    return await _provision(issuer_card_id, handle, "apple-pay")


@router.get("/cards/{issuer_card_id}/google-pay")
async def google_pay(issuer_card_id: str, handle: str):
    return await _provision(issuer_card_id, handle, "google-pay")


@router.post("/webhooks/{issuer_name}")
async def webhook(issuer_name: str, request: Request):
    raw = await request.body()
    signature = request.headers.get("x-cryptocardium-signature", "") or request.headers.get("x-signature", "")
    issuer = get_issuer()
    if issuer.name != issuer_name or not issuer.verify_webhook(raw, signature):
        raise HTTPException(401, "invalid webhook signature")
    payload = await request.json()
    await db.fomocard_events.insert_one({
        "id": new_id(), "issuer": issuer_name, "kind": payload.get("type", "unknown"),
        "payload": payload, "created_at": utcnow_iso(),
    })
    card_id = payload.get("card_id") or payload.get("issuer_card_id")
    if card_id and payload.get("type") in ("authorization", "settlement", "decline"):
        await db.fomocard_cards.update_one(
            {"issuer_card_id": card_id}, {"$set": {"last_event": payload.get("type"), "last_event_at": utcnow_iso()}})
    return {"received": True}
