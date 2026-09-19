"""Best-effort on-chain deposit confirmation for Social Cash — Solana + EVM, read-only, no custody.

This only corroborates a user-submitted deposit transaction hash before a top-up is marked funded
in our own ledger. It never raises: an unreachable or unconfigured RPC degrades to "unknown" rather
than blocking the flow. In production, the card issuer's own webhook (see card_issuer.py) is the
authoritative confirmation — this module exists so the happy path also works stand-alone against
public RPCs while that webhook is being wired up.
"""
import os

import httpx

SOLANA_RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").rstrip("/")
EVM_RPC_URL = os.environ.get("FOMOCARD_EVM_RPC_URL", "").rstrip("/")


async def _rpc(url: str, method: str, params: list) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            r.raise_for_status()
            return r.json().get("result")
    except Exception:
        return None


async def solana_tx_confirmed(signature: str) -> bool | None:
    res = await _rpc(SOLANA_RPC_URL, "getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])
    if not res:
        return None
    st = (res.get("value") or [None])[0]
    if not st:
        return None
    if st.get("err"):
        return False
    return st.get("confirmationStatus") in ("confirmed", "finalized")


async def evm_tx_confirmed(tx_hash: str) -> bool | None:
    if not EVM_RPC_URL:
        return None
    res = await _rpc(EVM_RPC_URL, "eth_getTransactionReceipt", [tx_hash])
    if not res:
        return None
    return res.get("status") in ("0x1", 1)


async def tx_confirmed(chain: str, tx_hash: str) -> bool | None:
    if chain == "solana":
        return await solana_tx_confirmed(tx_hash)
    if chain == "evm":
        return await evm_tx_confirmed(tx_hash)
    return None
