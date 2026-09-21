"""Pump.fun 'client' — unlike FOMO, Pump.fun doesn't have a well-known third-party API that maps a
handle to linked wallets: on Pump.fun the connected Solana wallet already *is* the identity. So
there's no handle resolution here, just a live read of that wallet's spendable balance (SOL + USDC)
straight from a public Solana RPC. No API key required, and no demo fallback needed either — a
failed RPC just reports zero rather than guessing at fake data.
"""
import asyncio
import os

import httpx

SOLANA_RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").rstrip("/")
# Circulating USDC mint on Solana mainnet — override via env if you want to track a different asset.
USDC_MINT_SOLANA = os.environ.get("USDC_MINT_SOLANA", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

LAMPORTS_PER_SOL = 1_000_000_000


async def _rpc(method: str, params: list):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(SOLANA_RPC_URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            r.raise_for_status()
            return r.json().get("result")
    except Exception:
        return None


async def sol_balance(address: str) -> float:
    res = await _rpc("getBalance", [address])
    if not res:
        return 0.0
    return round((res.get("value") or 0) / LAMPORTS_PER_SOL, 6)


async def usdc_balance(address: str) -> float:
    res = await _rpc("getTokenAccountsByOwner", [address, {"mint": USDC_MINT_SOLANA}, {"encoding": "jsonParsed"}])
    if not res:
        return 0.0
    total = 0.0
    for acct in res.get("value") or []:
        try:
            total += float(acct["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
        except (KeyError, TypeError, ValueError):
            continue
    return round(total, 2)


async def get_balances(wallet_address: str) -> dict:
    """The wallet address itself is both the identity and the thing we read — no handle involved."""
    sol, usdc = await asyncio.gather(sol_balance(wallet_address), usdc_balance(wallet_address))
    return {"wallet": wallet_address, "demo": False, "balances": {"SOL": sol, "USDC": usdc},
            "usd_value": None, "live": True}
