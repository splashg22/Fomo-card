"""fomoapi.io client — resolves a FOMO (fomo.family) handle to its linked Solana + EVM wallets and
live balances. fomoapi.io is an independent, third-party data API; FOMO Card is not affiliated with
FOMO Labs. Set FOMOAPI_KEY to hit the real API — without one every call degrades to a deterministic,
clearly-labelled demo profile so the connect -> load -> spend flow stays runnable end-to-end before
a real key is issued.
"""
import hashlib
import os
import time

import httpx

BASE_URL = os.environ.get("FOMOAPI_BASE_URL", "https://api.fomoapi.io").rstrip("/")
API_KEY = os.environ.get("FOMOAPI_KEY", "").strip()

_TTL = 20.0
_cache: dict[str, tuple[float, dict]] = {}


def configured() -> bool:
    return bool(API_KEY)


def _demo_profile(handle: str) -> dict:
    """Deterministic per-handle fake data — same handle always yields the same demo wallets/balances,
    so a UI built against this can be tested without a real fomoapi.io key."""
    h = hashlib.sha256(handle.lower().encode()).hexdigest()
    usdc = round(50 + (int(h[:6], 16) % 200_000) / 100, 2)
    sol_bal = round((int(h[6:10], 16) % 50_000) / 1000, 4)
    return {
        "handle": handle,
        "demo": True,
        "wallets": {
            "solana": "Fomo" + h[:38],
            "evm": "0x" + h[:40],
        },
        "balances": {"USDC": usdc, "SOL": sol_bal},
        "usd_value": round(usdc + sol_bal * 150.0, 2),
        "pnl_30d_usd": round(((int(h[10:14], 16) % 40_000) - 20_000) / 100, 2),
    }


async def _get(path: str) -> dict | None:
    if not configured():
        return None
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with httpx.AsyncClient(timeout=10, headers=headers) as c:
        r = await c.get(f"{BASE_URL}{path}")
        r.raise_for_status()
        return r.json()


async def resolve_handle(handle: str) -> dict:
    """GET /v2/users/{handle} — handle -> linked Solana + EVM wallets, PnL, theses, leaderboard rank."""
    handle = (handle or "").strip().lstrip("@")
    if not handle:
        raise ValueError("handle required")
    key = f"user:{handle.lower()}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    try:
        data = await _get(f"/v2/users/{handle}")
    except Exception:
        data = None
    profile = data or _demo_profile(handle)
    profile.setdefault("handle", handle)
    _cache[key] = (time.time(), profile)
    return profile


async def get_balances(handle: str) -> dict:
    """GET /v2/users/{handle}/balances — live holdings across every linked wallet, USD-valued."""
    handle = (handle or "").strip().lstrip("@")
    key = f"bal:{handle.lower()}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    try:
        data = await _get(f"/v2/users/{handle}/balances")
    except Exception:
        data = None
    if data is None:
        profile = _demo_profile(handle)
        data = {"handle": handle, "demo": True, "balances": profile["balances"], "usd_value": profile["usd_value"]}
    _cache[key] = (time.time(), data)
    return data
