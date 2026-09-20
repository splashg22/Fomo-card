# Social Cash

The facilitator for spending your social trading cash — an independent, unofficial spend layer for
[FOMO](https://fomo.family) and [Pump.fun](https://pump.fun) traders. **Not affiliated with,
endorsed by, or operated by FOMO Labs or Pump.fun.**

> Renamed from FOMO Card. If you're looking at a repo still called `fomo-card`, that's this
> project — GitHub redirects the old name automatically once it's renamed.

**Testing this with real people?** See [TESTING.md](TESTING.md) for a plain-language walkthrough —
including exactly what's demo vs. real right now.

Connect a FOMO handle or a Pump.fun wallet, load a virtual card straight from your linked wallet by
sending USDC/SOL/USDT to a no-KYC card issuer's own deposit address, then spend it — Apple Pay,
Google Pay, or the card number online. Social Cash is a thin, mostly-stateless layer on top of
things it doesn't own:

- **[fomoapi.io](https://fomoapi.io)** — independent FOMO handle → wallet/balance resolution
- **Solana RPC** — for Pump.fun, the connected wallet already *is* the account, so balances are
  just read live on-chain; no separate handle/data API needed
- **A no-KYC card issuer** (built for [Cryptocardium](https://cryptocardium.com), pluggable) —
  actually issues and funds the card

Social Cash never custodies your money: you send crypto directly from your own wallet to the
issuer's deposit address. We only read balances and call the issuer's API on your behalf.

## Architecture

```
main.py             FastAPI app, CORS, startup DB indexes
db.py               Mongo connection + new_id()/utcnow_iso() helpers
fomo_client.py      fomoapi.io client (handle resolve, balances) — demo fallback if no key
pumpfun_client.py   reads a Solana wallet's live SOL + USDC balance — no key, no demo fallback
onchain.py          best-effort Solana/EVM deposit tx confirmation
card_issuer.py      CardIssuer interface — DemoIssuer (no keys needed) + CryptocardiumIssuer
socialcash.py       /api/* router: connect, top-up, confirm, cards, reveal, freeze, webhooks
pages.py            the whole site (/ and /fragment/*) — htmx from a CDN, one small inline
                    script for MetaMask/Phantom wallet-connect signing
```

No React, no build step, no npm — `pages.py` renders plain HTML server-side and htmx (loaded from
a CDN in the page itself) drives every dynamic swap. The card issuer is behind an interface
(`CardIssuer` in `card_issuer.py`) so you can add another no-KYC issuer without touching
`socialcash.py`. Adding a third platform means one new `<platform>_client.py` plus a couple of
branches in `socialcash.py` — the top-up/card/issuer flow underneath is already platform-agnostic.

**How the two platforms differ:** a FOMO account's *identity* is its handle, which fomoapi.io
resolves to whatever wallets are linked to it. A Pump.fun account has no such lookup — the wallet
you connect **is** the identity, full stop, so `pumpfun_client.py` just reads that one wallet's
balance directly from a public Solana RPC. `socialcash.py` treats both the same way past that
point: an `{platform, identity}` pair keys everything else (top-ups, cards, rate limits).

**Security:** PAN/CVV are never persisted — a reveal is proxied straight from the issuer to the
caller and only logged as an event (platform + identity + card id + timestamp), never the secret
itself. Only `issuer_card_id`, `last4`, `brand`, `expiry` and `status` live in the database.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional — every var has a safe default (see below)
```

You need a MongoDB instance. Easiest local options:
- `docker run -d -p 27017:27017 mongo:7` — then leave `MONGO_URL` at its default
  (`mongodb://localhost:27017`)
- A free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster — put its connection string in
  `MONGO_URL`

## Run it

```bash
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000. With no `.env` at all:

- **FOMO** runs in **DEMO mode**: `fomoapi.io` calls return deterministic fake wallets/balances
  (same handle → same fake data every time), and the card issuer defaults to `DemoIssuer`, which
  issues a fake, clearly-labelled sandbox card with no real money movement anywhere.
- **Pump.fun** needs no demo mode — it reads your *actual* connected wallet's real SOL/USDC balance
  from public Solana RPC. Only the card funding step is fake (via `DemoIssuer`) until you set a real
  issuer key.

That's enough to exercise the **entire** connect → load → confirm → spend UI end to end, for either
platform, before you have a single real API key.

## Testing a full load → spend flow (demo mode)

1. Open http://localhost:8000. Under **FOMO account**, type any handle (e.g. `@degen`) and click
   **Connect EVM wallet** (needs MetaMask, or another injected wallet, installed) or **Connect
   Phantom**. Or, under **Pump.fun wallet**, just click **Connect Phantom** — no handle needed. Sign
   the one message it asks for — that's the whole "auth" step, no funds move.
2. You'll see your linked balances (fake for FOMO, real on-chain for Pump.fun). Pick an amount
   under **Load a card** and click **Get deposit address**.
3. In demo mode you don't actually need to send anything — paste any string (e.g. `0xdemo123...`)
   into the transaction hash field and click **I sent it — confirm**. (In real/`cryptocardium`
   mode this is where you'd actually broadcast a transfer and paste the real tx hash/signature.)
4. Your card appears: masked number, expiry, status. Click **Reveal PAN (once)** to see the (fake)
   full number/CVV — shown once, never stored. Try **Freeze**/**Unfreeze**, and
   **Add to Apple/Google Pay** (demo mode explains there's nothing real to provision yet).

Or drive the API directly:

```bash
# 1. connect (needs a real signature in practice — see socialcash.py:connect_message)
curl -X POST localhost:8000/api/connect -H 'content-type: application/json' -d '{
  "platform": "fomo", "handle": "degen", "address": "0xabc...", "chain": "evm", "signature": "0x..."
}'
# or, for Pump.fun (no handle — the wallet is the identity):
curl -X POST localhost:8000/api/connect -H 'content-type: application/json' -d '{
  "platform": "pumpfun", "address": "9WzD...SolanaAddress", "chain": "solana", "signature": "0x..."
}'

# 2. start a top-up
curl -X POST localhost:8000/api/topups -H 'content-type: application/json' -d '{
  "platform": "fomo", "identity": "degen", "amount_usd": 50, "asset": "USDC", "chain": "evm"
}'

# 3. confirm it (demo mode funds immediately regardless of the tx hash's validity)
curl -X POST localhost:8000/api/topups/<topup_id>/confirm -H 'content-type: application/json' \
  -d '{"tx_hash": "0xdeadbeef..."}'

# 4. see your card
curl "localhost:8000/api/cards?platform=fomo&identity=degen"
```

## Going live with a real issuer

1. Get a `CRYPTOCARDIUM_API_KEY` (or another issuer's key — implement `CardIssuer` for it in
   `card_issuer.py` and add it to `get_issuer()`).
2. Set `CARD_ISSUER=cryptocardium` and the key in `.env`.
3. **Verify every endpoint path/payload in `CryptocardiumIssuer` against their current docs** — the
   shapes there are a best-effort guess at their documented REST model (issue, fund, freeze,
   reveal, Apple/Google Pay provisioning, webhooks), each marked `# TODO verify`, not a confirmed
   integration.
4. Set `CRYPTOCARDIUM_WEBHOOK_SECRET` and point their webhook at
   `POST /api/webhooks/cryptocardium` — that's the real source of truth for authorizations,
   settlements, and declines, not the best-effort on-chain check in `onchain.py`.
5. Get a `FOMOAPI_KEY` from fomoapi.io for real FOMO handle/wallet/balance resolution. Pump.fun
   needs no equivalent key — `pumpfun_client.py` already reads real balances via public RPC.

## Real limits and risks (read before you rely on this)

- No-KYC card tiers cap spend to stay non-KYC — typically low hundreds to a couple thousand
  dollars a month (`MAX_TOPUP_USD`/`MAX_DAILY_USD` in `socialcash.py` — tune to your issuer's
  actual program limits). Higher limits or a physical card usually require a light KYC step with
  the issuer directly.
- You are dependent on the issuer's program rules, fees, and solvency; they can freeze or decline
  at their own discretion.
- No-KYC crypto card products sit in real regulatory territory (money transmission, AML) in most
  jurisdictions. This repo doesn't take a legal position for you — get real advice before running
  it for real money.
- Rate limiting here is in-process (a Python `dict` of sliding windows) — fine for a single
  instance, not safe across multiple workers/replicas. Swap for Redis before scaling out.
- Pump.fun identity has no signature-verified handle layer to fall back on — if someone doesn't
  control the wallet they connect, there's no account recovery path. That's inherent to "the
  wallet is the account," not a bug to fix.

## Tests

```bash
pip install pytest
uvicorn main:app --port 8000 &
FOMOCARD_BASE_URL=http://localhost:8000 pytest tests/ -v
```
