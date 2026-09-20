# Testing Social Cash

Thanks for trying this out. Here's everything you need in plain language — no code required.

## What this is

Social Cash connects a **FOMO handle** or a **Pump.fun wallet** to a spendable balance you can use
anywhere Apple Pay, Google Pay, or a card number works. You send crypto once, from your own wallet,
straight to the issuer — nothing sits with us in between.

## Before you start

You'll need one of these:
- **A FOMO handle** + any injected wallet (MetaMask) or Phantom, **or**
- **Phantom** (Solana wallet) — no handle needed, your wallet is the account

You do **not** need a seed phrase, an email, an ID, or a password. You'll sign one message with your
wallet to prove you own it — that's it.

## The flow

1. Open the site. Pick the **FOMO** or **Pump.fun** tab.
2. Enter your handle (FOMO only) and click **Connect & sign** / **Connect Phantom**. Approve the
   signature request your wallet pops up — this doesn't move any money.
3. Pick an amount and click **Get deposit address**. You'll get a real address to send USDC, SOL, or
   USDT to.
4. Send it from your wallet, then paste the transaction hash/signature back in and click **confirm**.
5. Your card appears — masked number, expiry, status. Click **Reveal PAN (once)** to see the full
   number when you need it, or **Add to Apple/Google Pay**.

## Important: demo mode vs. real mode

Right now this runs in **demo mode** by default:
- FOMO balances are fake, deterministic sample data (same handle → same numbers every time) —
  set a real `FOMOAPI_KEY` to see actual linked wallets/balances.
- Pump.fun balances are **real** — that part already reads your actual wallet's SOL/USDC on-chain.
- The card itself is **always fake in demo mode** — no real card is issued, no real money moves,
  regardless of platform. You'll see `DEMO` on the card face. Set `CARD_ISSUER=cryptocardium` with a
  real issuer key to issue an actual spendable card.

**If you want testers spending real money on a real card, that switch hasn't been flipped yet** — it
needs a real card issuer API key (Cryptocardium or another no-KYC issuer) and, for FOMO, a real
fomoapi.io key. Until then, testers are validating the flow and UI, not real spend.

## Known limits (even once real)

- No-KYC card tiers cap spend — typically low hundreds to a couple thousand dollars a month.
- The issuer can freeze or decline a transaction at their own discretion.
- Pump.fun has no account-recovery path: the wallet you connect **is** the account, permanently.
- This is a minimum-viable prototype. Verify amounts before relying on it for anything real.

## Reporting an issue

Tell us: what platform (FOMO/Pump.fun), what step, what you expected vs. what happened, and — if
you can — the exact error text or a screenshot. That's usually enough to reproduce it.
