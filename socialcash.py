"""Social Cash — an independent, unofficial facilitator that turns a social-trading balance into
real-world spend. Not affiliated with, endorsed by, or operated by FOMO Labs or Pump.fun.

Two platforms plug into the same flow, distinguished by how "identity" resolves:
  - fomo: identity is a FOMO handle, resolved to its linked wallets via fomoapi.io (fomo_client.py).
  - pumpfun: identity IS the connected Solana wallet — Pump.fun has no separate handle/wallet lookup
    to resolve, so the wallet address itself is the account (pumpfun_client.py just reads its live
    SOL/USDC balance).

Either way: connect proves wallet ownership with a signature, a top-up sends USDC/SOL/USDT straight
from that wallet to a no-KYC card issuer's own deposit address, and a confirmed deposit turns into a
funded virtual card with Apple Pay / Google Pay provisioning. Social Cash never custodies funds — the
issuer (see card_issuer.py) is the only place the money ever sits.

Only issuer_card_id, last4, brand, expiry and status are ever stored here — a PAN/CVV reveal is
proxied straight through to the caller and never written to socialcash_cards.
"""
import time
from collections import defaultdict, deque

import base58
import nacl.signing
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

import fomo_client
import onchain
import pumpfun_client
from card_issuer import IssuerError, get_issuer
from db import db, new_id, utcnow_iso

router = APIRouter(prefix="/api", tags=["socialcash"])

PLATFORMS = {"fomo", "pumpfun"}
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


def _display_handle(h: str) -> str:
    """Same cleanup as _clean_handle but case-preserved — the wallet-connect JS signs the message
    using the handle exactly as typed, so verification must build the same string, not the
    lowercased identity used for storage/dedup."""
    return (h or "").strip().lstrip("@")


def _norm_wallet(address: str, chain: str) -> str:
    a = (address or "").strip()
    return a.lower() if chain == "evm" else a  # Solana addresses are base58 and case-sensitive


def _norm_identity(platform: str, identity: str) -> str:
    return _clean_handle(identity) if platform == "fomo" else (identity or "").strip()


def identity_for(platform: str, handle: str, address: str) -> str:
    """FOMO's identity is the handle; Pump.fun's identity is the connected wallet itself."""
    return address if platform == "pumpfun" else _clean_handle(handle)


def connect_message(platform: str, identity: str, address: str) -> str:
    if platform == "pumpfun":
        return f"Social Cash · use {address} as my Pump.fun wallet"
    return f"Social Cash · link {address} to @{identity} on FOMO"


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


async def _balances_for(platform: str, identity: str) -> dict:
    if platform == "pumpfun":
        return await pumpfun_client.get_balances(identity)
    return await fomo_client.get_balances(identity)


class ConnectRequest(BaseModel):
    platform: str = Field(pattern="^(fomo|pumpfun)$")
    handle: str = Field(default="", max_length=40)   # required when platform == "fomo"
    address: str = Field(min_length=8, max_length=64)
    chain: str = Field(pattern="^(solana|evm)$")
    signature: str = Field(min_length=8, max_length=256)
    label: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def _check_platform_fields(self):
        if self.platform == "fomo" and not self.handle.strip():
            raise ValueError("handle is required to connect a FOMO account")
        if self.platform == "pumpfun" and self.chain != "solana":
            raise ValueError("Pump.fun is Solana-only")
        return self


class TopupRequest(BaseModel):
    platform: str = Field(pattern="^(fomo|pumpfun)$")
    identity: str = Field(min_length=1, max_length=64)
    amount_usd: float = Field(gt=0)
    asset: str
    chain: str = Field(pattern="^(solana|evm)$")


class ConfirmRequest(BaseModel):
    tx_hash: str = Field(min_length=6, max_length=128)


class IdentityOnly(BaseModel):
    platform: str = Field(pattern="^(fomo|pumpfun)$")
    identity: str


@router.get("/config")
async def config():
    issuer = get_issuer()
    return {
        "issuer": issuer.name,
        "demo_mode": issuer.name == "demo",
        "platforms": sorted(PLATFORMS),
        "fomoapi_configured": fomo_client.configured(),
        "min_topup_usd": MIN_TOPUP_USD, "max_topup_usd": MAX_TOPUP_USD, "max_daily_usd": MAX_DAILY_USD,
        "supported_assets": sorted(SUPPORTED_ASSETS),
        "disclaimer": "Social Cash is an independent product for social-trading communities. It is "
                      "not affiliated with, endorsed by, or operated by FOMO Labs or Pump.fun.",
    }


@router.post("/connect")
async def connect(body: ConnectRequest):
    address = _norm_wallet(body.address, body.chain)
    identity = identity_for(body.platform, body.handle, address)
    if _rate_limited(f"connect:{body.platform}:{identity}", 10, 60):
        raise HTTPException(429, "too many connect attempts — try again in a minute")
    message_identity = _display_handle(body.handle) if body.platform == "fomo" else identity
    message = connect_message(body.platform, message_identity, address)
    if not verify_wallet_signature(body.chain, address, message, body.signature):
        raise HTTPException(401, "signature does not match — sign exactly: " + message)

    doc = {
        "platform": body.platform, "identity": identity,
        "handle": identity if body.platform == "fomo" else None,
        "label": body.label.strip()[:40],
        "wallet_chain": body.chain, "wallet_address": address,
        "connected_at": utcnow_iso(), "updated_at": utcnow_iso(),
    }
    if body.platform == "fomo":
        profile = await fomo_client.resolve_handle(identity)
        doc["fomo_wallets"] = profile.get("wallets", {})
        doc["demo_profile"] = bool(profile.get("demo"))
    await db.socialcash_users.update_one({"platform": body.platform, "identity": identity}, {"$set": doc}, upsert=True)
    balances = await _balances_for(body.platform, identity)
    return {"user": doc, "balances": balances}


@router.get("/profile")
async def profile(platform: str, identity: str):
    if platform not in PLATFORMS:
        raise HTTPException(422, f"platform must be one of {sorted(PLATFORMS)}")
    identity = _norm_identity(platform, identity)
    user = await db.socialcash_users.find_one({"platform": platform, "identity": identity}, {"_id": 0})
    if not user:
        raise HTTPException(404, "connect this account first")
    balances = await _balances_for(platform, identity)
    cards = await db.socialcash_cards.find({"platform": platform, "identity": identity}, {"_id": 0, "pan": 0, "cvv": 0}).to_list(10)
    return {"user": user, "balances": balances, "cards": cards}


@router.post("/topups")
async def create_topup(body: TopupRequest):
    if body.platform not in PLATFORMS:
        raise HTTPException(422, f"platform must be one of {sorted(PLATFORMS)}")
    identity = _norm_identity(body.platform, body.identity)
    user = await db.socialcash_users.find_one({"platform": body.platform, "identity": identity})
    if not user:
        raise HTTPException(404, "connect this account first")
    if _rate_limited(f"topup:{body.platform}:{identity}", 6, 60):
        raise HTTPException(429, "too many top-up attempts — try again in a minute")
    if body.platform == "pumpfun" and body.chain != "solana":
        raise HTTPException(422, "Pump.fun is Solana-only — send from a Solana wallet")
    asset = body.asset.strip().upper()
    if asset not in SUPPORTED_ASSETS:
        raise HTTPException(422, f"unsupported asset — use one of {sorted(SUPPORTED_ASSETS)}")
    if not (MIN_TOPUP_USD <= body.amount_usd <= MAX_TOPUP_USD):
        raise HTTPException(422, f"amount must be between ${MIN_TOPUP_USD:g} and ${MAX_TOPUP_USD:g} on this no-KYC tier")
    since = utcnow_iso()[:10]
    day_total = 0.0
    async for t in db.socialcash_topups.find(
            {"platform": body.platform, "identity": identity, "status": "funded", "created_at": {"$gte": since}}, {"amount_usd": 1}):
        day_total += t.get("amount_usd", 0)
    if day_total + body.amount_usd > MAX_DAILY_USD:
        raise HTTPException(422, f"daily no-KYC limit reached (${MAX_DAILY_USD:g}/day) — try a smaller amount or again tomorrow")
    issuer = get_issuer()
    try:
        deposit_address = await issuer.deposit_address(asset, body.chain)
    except IssuerError as e:
        raise HTTPException(502, f"issuer unavailable: {e}")
    topup = {
        "id": new_id(), "platform": body.platform, "identity": identity, "amount_usd": round(body.amount_usd, 2),
        "asset": asset, "chain": body.chain, "deposit_address": deposit_address,
        "status": "pending_deposit", "tx_hash": None,
        "created_at": utcnow_iso(), "updated_at": utcnow_iso(),
    }
    await db.socialcash_topups.insert_one(dict(topup))
    return {
        "topup": topup,
        "instructions": f"Send exactly {body.amount_usd:g} USD of {asset} on {body.chain} to {deposit_address}, "
                        f"then confirm below with the transaction hash.",
    }


@router.post("/topups/{topup_id}/confirm")
async def confirm_topup(topup_id: str, body: ConfirmRequest):
    topup = await db.socialcash_topups.find_one({"id": topup_id}, {"_id": 0})
    if not topup:
        raise HTTPException(404, "no such top-up")
    if topup["status"] == "funded":
        return {"topup": topup, "already_funded": True}
    if topup["status"] not in ("pending_deposit", "awaiting_confirmation"):
        raise HTTPException(409, f"top-up is {topup['status']}, cannot confirm")
    platform, identity = topup["platform"], topup["identity"]
    if _rate_limited(f"confirm:{platform}:{identity}", 10, 60):
        raise HTTPException(429, "too many confirm attempts — try again in a minute")

    issuer = get_issuer()
    demo_mode = issuer.name == "demo"
    # Demo transactions never exist on a real chain, so skip the RPC round-trip entirely instead of
    # waiting on a public node just to have the result ignored a few lines down.
    confirmed = None if demo_mode else await onchain.tx_confirmed(topup["chain"], body.tx_hash)
    if confirmed is False:
        raise HTTPException(400, "that transaction was not found or failed on-chain")
    if confirmed is None and not demo_mode:
        # a real deployment should wait for the issuer's own webhook before crediting a card; the RPC
        # check here is only a best-effort corroboration, not the source of truth.
        await db.socialcash_topups.update_one({"id": topup_id}, {"$set": {
            "tx_hash": body.tx_hash, "status": "awaiting_confirmation", "updated_at": utcnow_iso()}})
        return {
            "topup": {**topup, "status": "awaiting_confirmation", "tx_hash": body.tx_hash},
            "note": "could not verify this transaction on-chain yet — it will finalize via the issuer's webhook",
        }

    card = await db.socialcash_cards.find_one({"platform": platform, "identity": identity}, {"_id": 0})
    label = f"@{identity}" if platform == "fomo" else identity
    try:
        if not card:
            issued = await issuer.create_card(f"{platform}:{identity}", f"Social Cash · {label}")
            card = {**issued, "platform": platform, "identity": identity, "created_at": utcnow_iso(), "updated_at": utcnow_iso()}
            await db.socialcash_cards.insert_one(dict(card))
        funded = await issuer.fund_card(card["issuer_card_id"], topup["amount_usd"], topup["asset"], body.tx_hash)
    except IssuerError as e:
        raise HTTPException(502, f"issuer funding failed: {e}")

    # Prefer the issuer's own reported balance when it gives one — it's the source of truth for real
    # money. Only fall back to incrementing by the top-up amount (the demo issuer reports no balance).
    if funded.get("balance_usd") is not None:
        await db.socialcash_cards.update_one(
            {"issuer_card_id": card["issuer_card_id"]},
            {"$set": {"balance_usd": funded["balance_usd"], "status": "active", "updated_at": utcnow_iso()}},
        )
    else:
        await db.socialcash_cards.update_one(
            {"issuer_card_id": card["issuer_card_id"]},
            {"$inc": {"balance_usd": topup["amount_usd"]}, "$set": {"status": "active", "updated_at": utcnow_iso()}},
        )
    await db.socialcash_topups.update_one(
        {"id": topup_id}, {"$set": {"tx_hash": body.tx_hash, "status": "funded", "updated_at": utcnow_iso()}})
    card = await db.socialcash_cards.find_one({"issuer_card_id": card["issuer_card_id"]}, {"_id": 0, "pan": 0, "cvv": 0})
    topup = await db.socialcash_topups.find_one({"id": topup_id}, {"_id": 0})
    return {"topup": topup, "card": card, "funded": funded}


@router.get("/topups")
async def list_topups(platform: str, identity: str, limit: int = 30):
    identity = _norm_identity(platform, identity)
    rows = await db.socialcash_topups.find({"platform": platform, "identity": identity}, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 100))
    return {"topups": rows}


@router.get("/cards")
async def list_cards(platform: str, identity: str):
    identity = _norm_identity(platform, identity)
    rows = await db.socialcash_cards.find({"platform": platform, "identity": identity}, {"_id": 0, "pan": 0, "cvv": 0}).to_list(10)
    return {"cards": rows}


@router.post("/cards/{issuer_card_id}/reveal")
async def reveal_card(issuer_card_id: str, body: IdentityOnly):
    identity = _norm_identity(body.platform, body.identity)
    card = await db.socialcash_cards.find_one({"issuer_card_id": issuer_card_id, "platform": body.platform, "identity": identity})
    if not card:
        raise HTTPException(404, "card not found for this account")
    if _rate_limited(f"reveal:{body.platform}:{identity}", 3, 3600):
        raise HTTPException(429, "too many reveal attempts — try again later")
    try:
        secret = await get_issuer().reveal(issuer_card_id)
    except IssuerError as e:
        raise HTTPException(502, f"issuer reveal failed: {e}")
    await db.socialcash_events.insert_one({
        "id": new_id(), "platform": body.platform, "identity": identity, "issuer_card_id": issuer_card_id,
        "kind": "pan_revealed", "created_at": utcnow_iso(),
    })
    return secret  # single-use — the client shows this once and discards it; nothing sensitive is stored


async def _set_frozen(issuer_card_id: str, platform: str, identity: str, frozen: bool) -> dict:
    identity = _norm_identity(platform, identity)
    card = await db.socialcash_cards.find_one({"issuer_card_id": issuer_card_id, "platform": platform, "identity": identity})
    if not card:
        raise HTTPException(404, "card not found for this account")
    try:
        result = await get_issuer().set_frozen(issuer_card_id, frozen)
    except IssuerError as e:
        raise HTTPException(502, f"issuer request failed: {e}")
    status = result.get("status", "frozen" if frozen else "active")
    await db.socialcash_cards.update_one({"issuer_card_id": issuer_card_id}, {"$set": {"status": status, "updated_at": utcnow_iso()}})
    return {"issuer_card_id": issuer_card_id, "status": status}


@router.post("/cards/{issuer_card_id}/freeze")
async def freeze_card(issuer_card_id: str, body: IdentityOnly):
    return await _set_frozen(issuer_card_id, body.platform, body.identity, True)


@router.post("/cards/{issuer_card_id}/unfreeze")
async def unfreeze_card(issuer_card_id: str, body: IdentityOnly):
    return await _set_frozen(issuer_card_id, body.platform, body.identity, False)


async def _provision(issuer_card_id: str, platform: str, identity: str, wallet: str) -> dict:
    identity = _norm_identity(platform, identity)
    card = await db.socialcash_cards.find_one({"issuer_card_id": issuer_card_id, "platform": platform, "identity": identity})
    if not card:
        raise HTTPException(404, "card not found for this account")
    try:
        return await get_issuer().provision(issuer_card_id, wallet)
    except IssuerError as e:
        raise HTTPException(502, f"issuer request failed: {e}")


@router.post("/cards/{issuer_card_id}/apple-pay")
async def apple_pay(issuer_card_id: str, body: IdentityOnly):
    return await _provision(issuer_card_id, body.platform, body.identity, "apple-pay")


@router.post("/cards/{issuer_card_id}/google-pay")
async def google_pay(issuer_card_id: str, body: IdentityOnly):
    return await _provision(issuer_card_id, body.platform, body.identity, "google-pay")


@router.post("/webhooks/{issuer_name}")
async def webhook(issuer_name: str, request: Request):
    raw = await request.body()
    signature = request.headers.get("x-cryptocardium-signature", "") or request.headers.get("x-signature", "")
    issuer = get_issuer()
    if issuer.name != issuer_name or not issuer.verify_webhook(raw, signature):
        raise HTTPException(401, "invalid webhook signature")
    payload = await request.json()
    await db.socialcash_events.insert_one({
        "id": new_id(), "issuer": issuer_name, "kind": payload.get("type", "unknown"),
        "payload": payload, "created_at": utcnow_iso(),
    })
    card_id = payload.get("card_id") or payload.get("issuer_card_id")
    if card_id and payload.get("type") in ("authorization", "settlement", "decline"):
        await db.socialcash_cards.update_one(
            {"issuer_card_id": card_id}, {"$set": {"last_event": payload.get("type"), "last_event_at": utcnow_iso()}})
    return {"received": True}
