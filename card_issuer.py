"""Card issuer abstraction for Social Cash.

Social Cash is a branded spend layer on top of an existing no-KYC card program — it does not become a
Visa/Mastercard principal member or run its own BIN. Every issuer implements the same `CardIssuer`
interface so socialcash.py's funding/issuance flow never has to know which one is behind it; switch
with the CARD_ISSUER env var.

DemoIssuer needs no API key and lets the whole connect -> load -> spend loop run end-to-end locally,
clearly labelled `demo: True` everywhere so it can never be mistaken for a real, spendable card.
CryptocardiumIssuer talks to a real no-KYC issuer's REST API. The endpoint shapes below follow their
documented model (issue, fund, freeze, reveal, Apple/Google Pay provisioning, webhooks) — verify the
exact paths and payloads against Cryptocardium's current docs/MCP server before going live; treat
every `# TODO verify` below as a checklist item, not a guarantee.

Security: nothing here ever logs a PAN, CVV or webhook secret. Callers must not persist the dict
`reveal()` returns beyond handing it to the user once.
"""
import hashlib
import hmac
import os
import secrets
from abc import ABC, abstractmethod

import httpx


class IssuerError(Exception):
    pass


class CardIssuer(ABC):
    name = "base"

    @abstractmethod
    async def deposit_address(self, asset: str, chain: str) -> str: ...

    @abstractmethod
    async def create_card(self, external_user_id: str, label: str) -> dict: ...

    @abstractmethod
    async def fund_card(self, issuer_card_id: str, amount_usd: float, asset: str, tx_hash: str) -> dict: ...

    @abstractmethod
    async def get_card(self, issuer_card_id: str) -> dict: ...

    @abstractmethod
    async def set_frozen(self, issuer_card_id: str, frozen: bool) -> dict: ...

    @abstractmethod
    async def reveal(self, issuer_card_id: str) -> dict: ...

    @abstractmethod
    async def provision(self, issuer_card_id: str, wallet: str) -> dict: ...

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        return False


class DemoIssuer(CardIssuer):
    """No external calls, no real money movement, no server-side state (safe under multiple workers).
    Card identity is derived deterministically from the caller's own id; our DB (socialcash_cards) stays
    the source of truth for balance and status, exactly as it would for a real issuer synced by webhook."""
    name = "demo"

    async def deposit_address(self, asset: str, chain: str) -> str:
        seed = f"socialcash-demo-deposit-{asset}-{chain}".encode()
        prefix = "Demo" if chain == "solana" else "0xDEMO"
        return prefix + hashlib.sha256(seed).hexdigest()[:34]

    async def create_card(self, external_user_id: str, label: str) -> dict:
        h = hashlib.sha256(f"socialcash-demo-card-{external_user_id}-{secrets.token_hex(4)}".encode()).hexdigest()
        digits = "".join(c for c in h if c.isdigit())
        return {
            "issuer_card_id": "demo_" + h[:20],
            "last4": (digits[:4] or "0000").ljust(4, "0"),
            "brand": "Visa (Demo)",
            "expiry": "12/29",
            "status": "active",
            "balance_usd": 0.0,
            "demo": True,
        }

    async def fund_card(self, issuer_card_id: str, amount_usd: float, asset: str, tx_hash: str) -> dict:
        return {"status": "funded", "demo": True}

    async def get_card(self, issuer_card_id: str) -> dict:
        return {"issuer_card_id": issuer_card_id, "status": "active", "demo": True}

    async def set_frozen(self, issuer_card_id: str, frozen: bool) -> dict:
        return {"status": "frozen" if frozen else "active", "demo": True}

    async def reveal(self, issuer_card_id: str) -> dict:
        h = hashlib.sha256(issuer_card_id.encode()).hexdigest()
        digits = "".join(c for c in h if c.isdigit())[:16].ljust(16, "0")
        return {
            "pan": digits, "cvv": "000", "expiry": "12/29", "demo": True,
            "note": "Demo card — not real and not spendable. Set CARD_ISSUER=cryptocardium with a "
                    "real CRYPTOCARDIUM_API_KEY to issue a live card.",
        }

    async def provision(self, issuer_card_id: str, wallet: str) -> dict:
        return {
            "provisioned": False, "demo": True,
            "note": f"Demo mode has no real {wallet} provisioning token — configure a real issuer to enable it.",
        }


class CryptocardiumIssuer(CardIssuer):
    """https://cryptocardium.com — no-KYC virtual/physical cards, crypto funded, Apple/Google Pay on
    some BINs, REST API + native MCP server. TODO verify every path/payload below against their
    current docs before relying on it in production; this is a best-effort integration shape."""
    name = "cryptocardium"

    def __init__(self):
        self.base = os.environ.get("CRYPTOCARDIUM_BASE_URL", "https://api.cryptocardium.com/v1").rstrip("/")
        self.key = os.environ.get("CRYPTOCARDIUM_API_KEY", "").strip()
        self.webhook_secret = os.environ.get("CRYPTOCARDIUM_WEBHOOK_SECRET", "").strip()
        if not self.key:
            raise IssuerError("CRYPTOCARDIUM_API_KEY is not set")

    async def _req(self, method: str, path: str, **kw) -> dict:
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=20, headers=headers) as c:
            r = await c.request(method, f"{self.base}{path}", **kw)
        if r.status_code >= 400:
            raise IssuerError(f"Cryptocardium {method} {path} -> HTTP {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    async def deposit_address(self, asset: str, chain: str) -> str:  # TODO verify endpoint shape
        data = await self._req("GET", f"/deposit-addresses?asset={asset}&chain={chain}")
        addr = data.get("address") or data.get("deposit_address")
        if not addr:
            raise IssuerError("issuer returned no deposit address")
        return addr

    async def create_card(self, external_user_id: str, label: str) -> dict:  # TODO verify endpoint shape
        data = await self._req("POST", "/cards", json={"external_user_id": external_user_id, "label": label, "kyc": "none"})
        return {
            "issuer_card_id": data.get("id") or data.get("card_id"),
            "last4": data.get("last4"),
            "brand": data.get("brand", "Visa"),
            "expiry": data.get("expiry") or data.get("exp"),
            "status": data.get("status", "active"),
            "balance_usd": float(data.get("balance_usd") or 0),
            "demo": False,
        }

    async def fund_card(self, issuer_card_id: str, amount_usd: float, asset: str, tx_hash: str) -> dict:
        data = await self._req("POST", f"/cards/{issuer_card_id}/fund",
                                json={"amount_usd": amount_usd, "asset": asset, "tx_hash": tx_hash})
        return {"status": data.get("status", "funded"), "balance_usd": float(data.get("balance_usd") or 0)}

    async def get_card(self, issuer_card_id: str) -> dict:
        data = await self._req("GET", f"/cards/{issuer_card_id}")
        return {
            "issuer_card_id": issuer_card_id, "last4": data.get("last4"), "brand": data.get("brand", "Visa"),
            "expiry": data.get("expiry"), "status": data.get("status"),
            "balance_usd": float(data.get("balance_usd") or 0),
        }

    async def set_frozen(self, issuer_card_id: str, frozen: bool) -> dict:
        data = await self._req("POST", f"/cards/{issuer_card_id}/{'freeze' if frozen else 'unfreeze'}")
        return {"status": data.get("status", "frozen" if frozen else "active")}

    async def reveal(self, issuer_card_id: str) -> dict:
        """Single-use, short-TTL PAN reveal. Never persist the result beyond one response to the user."""
        data = await self._req("POST", f"/cards/{issuer_card_id}/reveal")
        return {"pan": data.get("pan"), "cvv": data.get("cvv"), "expiry": data.get("expiry")}

    async def provision(self, issuer_card_id: str, wallet: str) -> dict:
        """`wallet` is 'apple-pay' or 'google-pay'."""
        return await self._req("POST", f"/cards/{issuer_card_id}/provision/{wallet}")

    def verify_webhook(self, raw_body: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            return False
        expected = hmac.new(self.webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        given = (signature or "")
        if given.startswith("sha256="):
            given = given[len("sha256="):]
        return hmac.compare_digest(expected, given)


def get_issuer() -> CardIssuer:
    kind = os.environ.get("CARD_ISSUER", "").strip().lower()
    if not kind:
        kind = "cryptocardium" if os.environ.get("CRYPTOCARDIUM_API_KEY", "").strip() else "demo"
    if kind == "cryptocardium":
        return CryptocardiumIssuer()
    return DemoIssuer()
