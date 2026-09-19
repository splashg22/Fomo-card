"""Integration tests for Social Cash. Point FOMOCARD_BASE_URL at a running instance
(e.g. http://localhost:8000). Assumes DEMO mode (no CRYPTOCARDIUM_API_KEY set), which is the
default — the demo issuer funds a sandbox card instantly with no real money."""
import os

import requests
from eth_account import Account
from eth_account.messages import encode_defunct

BASE_URL = os.environ.get("FOMOCARD_BASE_URL", "http://localhost:8000").rstrip("/")

S = requests.Session()
S.headers.update({"Content-Type": "application/json"})


def fomo_connect_body(handle: str) -> dict:
    acct = Account.create()
    address = acct.address.lower()
    message = f"Social Cash · link {address} to @{handle} on FOMO"
    signature = acct.sign_message(encode_defunct(text=message)).signature.hex()
    if not signature.startswith("0x"):
        signature = "0x" + signature
    return {"platform": "fomo", "handle": handle, "address": address, "chain": "evm", "signature": signature}


class TestConfig:
    def test_health(self):
        r = S.get(f"{BASE_URL}/health", timeout=20)
        assert r.status_code == 200, r.text

    def test_config(self):
        r = S.get(f"{BASE_URL}/api/config", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("issuer", "demo_mode", "platforms", "min_topup_usd", "max_topup_usd", "supported_assets", "disclaimer"):
            assert k in d
        assert set(d["platforms"]) == {"fomo", "pumpfun"}


class TestFomoConnect:
    def test_connect_requires_valid_signature(self):
        body = fomo_connect_body("TEST_badsig")
        body["signature"] = body["signature"][:-4] + "dead"
        r = S.post(f"{BASE_URL}/api/connect", json=body, timeout=20)
        assert r.status_code == 401, r.text

    def test_connect_requires_handle(self):
        acct = Account.create()
        r = S.post(f"{BASE_URL}/api/connect", json={
            "platform": "fomo", "handle": "", "address": acct.address, "chain": "evm", "signature": "0x" + "ab" * 65,
        }, timeout=20)
        assert r.status_code == 422, r.text

    def test_connect_happy_path(self):
        body = fomo_connect_body("TEST_connect")
        r = S.post(f"{BASE_URL}/api/connect", json=body, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["user"]["platform"] == "fomo"
        assert d["user"]["identity"] == "test_connect"
        assert d["user"]["wallet_address"] == body["address"]
        assert "balances" in d

    def test_profile_requires_connect_first(self):
        r = S.get(f"{BASE_URL}/api/profile", params={"platform": "fomo", "identity": "TEST_never_connected_xyz"}, timeout=20)
        assert r.status_code == 404


class TestPumpfunConnect:
    def test_pumpfun_must_be_solana(self):
        acct = Account.create()
        r = S.post(f"{BASE_URL}/api/connect", json={
            "platform": "pumpfun", "address": acct.address, "chain": "evm", "signature": "0x" + "ab" * 65,
        }, timeout=20)
        assert r.status_code == 422, r.text

    def test_pumpfun_connect_rejects_bad_signature(self):
        # A syntactically-plausible but wrong signature/address pair should be rejected, not accepted.
        r = S.post(f"{BASE_URL}/api/connect", json={
            "platform": "pumpfun", "address": "11111111111111111111111111111111", "chain": "solana",
            "signature": "0x" + "00" * 64,
        }, timeout=20)
        assert r.status_code in (400, 401), r.text


class TestTopupAndCard:
    handle = "TEST_topupflow"

    @classmethod
    def setup_class(cls):
        body = fomo_connect_body(cls.handle)
        r = S.post(f"{BASE_URL}/api/connect", json=body, timeout=20)
        assert r.status_code == 200, r.text

    def test_topup_amount_bounds(self):
        r = S.post(f"{BASE_URL}/api/topups",
                   json={"platform": "fomo", "identity": self.handle, "amount_usd": 5000, "asset": "USDC", "chain": "evm"}, timeout=20)
        assert r.status_code == 422, r.text

    def test_topup_unsupported_asset(self):
        r = S.post(f"{BASE_URL}/api/topups",
                   json={"platform": "fomo", "identity": self.handle, "amount_usd": 50, "asset": "DOGE", "chain": "evm"}, timeout=20)
        assert r.status_code == 422, r.text

    def test_topup_confirm_and_card_funded(self):
        r = S.post(f"{BASE_URL}/api/topups",
                   json={"platform": "fomo", "identity": self.handle, "amount_usd": 50, "asset": "USDC", "chain": "evm"}, timeout=20)
        assert r.status_code == 200, r.text
        topup = r.json()["topup"]
        assert topup["status"] == "pending_deposit"
        assert topup["deposit_address"]

        c = S.post(f"{BASE_URL}/api/topups/{topup['id']}/confirm",
                   json={"tx_hash": "0x" + "ab" * 32}, timeout=20)
        assert c.status_code == 200, c.text
        out = c.json()
        assert out["card"]["balance_usd"] >= 50.0
        assert out["card"]["last4"]
        assert "pan" not in out["card"] and "cvv" not in out["card"]

        # idempotent re-confirm
        c2 = S.post(f"{BASE_URL}/api/topups/{topup['id']}/confirm",
                    json={"tx_hash": "0x" + "ab" * 32}, timeout=20)
        assert c2.status_code == 200
        assert c2.json().get("already_funded") is True

        cards = S.get(f"{BASE_URL}/api/cards", params={"platform": "fomo", "identity": self.handle}, timeout=20)
        assert cards.status_code == 200
        assert len(cards.json()["cards"]) >= 1

    def test_reveal_is_rate_limited(self):
        cards = S.get(f"{BASE_URL}/api/cards", params={"platform": "fomo", "identity": self.handle}, timeout=20).json()["cards"]
        assert cards, "expected a funded card from the previous test"
        cid = cards[0]["issuer_card_id"]
        codes = []
        for _ in range(5):
            r = S.post(f"{BASE_URL}/api/cards/{cid}/reveal", json={"platform": "fomo", "identity": self.handle}, timeout=20)
            codes.append(r.status_code)
        assert 429 in codes, f"expected a 429 among {codes}"

    def test_freeze_unfreeze(self):
        cards = S.get(f"{BASE_URL}/api/cards", params={"platform": "fomo", "identity": self.handle}, timeout=20).json()["cards"]
        cid = cards[0]["issuer_card_id"]
        f = S.post(f"{BASE_URL}/api/cards/{cid}/freeze", json={"platform": "fomo", "identity": self.handle}, timeout=20)
        assert f.status_code == 200 and f.json()["status"] == "frozen"
        u = S.post(f"{BASE_URL}/api/cards/{cid}/unfreeze", json={"platform": "fomo", "identity": self.handle}, timeout=20)
        assert u.status_code == 200 and u.json()["status"] == "active"

    def test_history(self):
        r = S.get(f"{BASE_URL}/api/topups", params={"platform": "fomo", "identity": self.handle}, timeout=20)
        assert r.status_code == 200
        assert any(t["status"] == "funded" for t in r.json()["topups"])


class TestSite:
    def test_site_page(self):
        r = S.get(f"{BASE_URL}/", timeout=30)
        assert r.status_code == 200
        assert "Social Cash" in r.text
        assert "not affiliated with FOMO Labs or Pump.fun" in r.text
        assert 'data-testid="fomo-connect"' in r.text and 'data-testid="pumpfun-connect"' in r.text
