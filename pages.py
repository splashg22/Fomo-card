"""FOMO CARD — the whole standalone site. Dark, quiet, built for the fomo.family crowd. Unofficial.

No React host here (unlike the version of this product that briefly lived inside a bigger multi-
product stack) — htmx is loaded straight from a CDN and a small inline script handles the one thing
htmx can't: signing a message with the visitor's own MetaMask/Phantom wallet before the connect form
submits. Everything else (dashboard swaps, polling history, card actions) is plain htmx.
"""
import html as _html

from card_issuer import get_issuer
from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

import fomocard as fc

router = APIRouter(tags=["site"])


def esc(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


def err_text(e) -> str:
    return str(getattr(e, "detail", e))


CSS = """
<style>
#fc{--bg:#111214;--bg2:#17181b;--card:#1a1b1e;--ink:#e7e7ea;--ink2:#96979c;--ink3:#68696e;--line:#2a2b2f;
--accent:#8a9a90;--bad:#b97575;--good:#7f9e88;
--head:"Archivo","Space Grotesk",sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace;--sans:Inter,-apple-system,system-ui,sans-serif;
background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.55;min-height:100vh}
#fc *{box-sizing:border-box}
#fc ::selection{background:var(--accent);color:#111214}
#fc a{color:var(--accent);text-decoration:none}
#fc .w{max-width:1080px;margin:0 auto;padding:0 24px}
#fc .bar{position:sticky;top:0;z-index:40;background:rgba(17,18,20,.9);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
#fc .bar-in{display:flex;align-items:center;gap:20px;padding:16px 24px;max-width:1200px;margin:0 auto}
#fc .mk{font-family:var(--head);font-weight:600;font-size:18px;letter-spacing:-.01em;display:flex;align-items:center;gap:8px;color:var(--ink)}
#fc .mk i{width:24px;height:24px;background:var(--bg2);border:1px solid var(--line);border-radius:6px;display:grid;place-items:center;font-size:12px;font-weight:700;color:var(--ink2);font-style:normal}
#fc .right{margin-left:auto}
#fc .badge{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--ink3);border:1px solid var(--line);border-radius:999px;padding:5px 12px;background:var(--bg2)}
#fc section{padding:56px 0;position:relative;z-index:1}
#fc .kick{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3)}
#fc h1{font-family:var(--head);font-size:clamp(30px,4.4vw,48px);line-height:1.08;margin:14px 0 0;font-weight:600;letter-spacing:-.01em;color:var(--ink)}
#fc h1 em{font-style:normal;color:var(--ink)}
#fc h2{font-family:var(--head);font-size:clamp(22px,2.6vw,28px);margin:0 0 20px;font-weight:600;letter-spacing:-.01em}
#fc p.lede{color:var(--ink2);max-width:56ch;margin:18px 0 0;font-size:17px;line-height:1.65}
#fc .grid{display:grid;gap:20px}
@media(min-width:900px){#fc .g2{grid-template-columns:1fr 1fr}#fc .g3{grid-template-columns:repeat(3,1fr)}}
#fc .card{border:1px solid var(--line);border-radius:16px;background:var(--card);overflow:hidden}
#fc .card>header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:10px}
#fc .card>header h3{margin:0;font-family:var(--head);font-size:15px;font-weight:700}
#fc .card .body{padding:18px}
#fc label{display:block;margin-top:12px}
#fc label span{font-size:12px;font-weight:600;color:var(--ink2)}
#fc input,#fc select{width:100%;margin-top:6px;background:var(--bg2);border:1px solid var(--line);border-radius:10px;color:var(--ink);font-family:var(--mono);font-size:14px;padding:11px 12px;outline:none}
#fc input:focus,#fc select:focus{border-color:var(--accent)}
#fc .hint{font-size:13px;color:var(--ink3);margin-top:8px;line-height:1.6}
#fc .btn{font-family:var(--head);font-weight:600;font-size:14px;padding:11px 18px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#12130f;cursor:pointer;transition:opacity .15s}
#fc .btn:hover{opacity:.88}
#fc .btn:active{opacity:.75}
#fc .btn.o{background:transparent;border-color:var(--line);color:var(--ink)}
#fc .btn.sm{padding:7px 12px;font-size:12px}
#fc .btn[disabled]{opacity:.4;cursor:default}
#fc .amts{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
#fc .amts label{margin:0;flex:1;min-width:64px}
#fc .amts input{display:none}
#fc .amts span{display:block;text-align:center;border:1px solid var(--line);border-radius:8px;padding:9px;font-family:var(--mono);font-weight:600;cursor:pointer;background:var(--bg2);color:var(--ink2)}
#fc .amts input:checked+span{background:var(--bg2);color:var(--ink);border-color:var(--accent)}
#fc table{width:100%;border-collapse:collapse;font-size:13px;font-family:var(--mono)}
#fc th{text-align:left;font-family:var(--sans);font-weight:600;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink3);padding:10px 14px;border-bottom:1px solid var(--line);white-space:nowrap}
#fc td{padding:11px 14px;border-bottom:1px solid var(--line);white-space:nowrap;color:var(--ink2)}
#fc tbody tr:last-child td{border-bottom:0}
#fc .tag{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-family:var(--mono);font-size:11px;background:var(--bg2);color:var(--ink2)}
#fc .panel{border:1px solid var(--line);border-radius:12px;background:var(--bg2);padding:20px}
#fc .panel.go{border-color:var(--good)}
#fc .panel.stop{border-color:var(--bad)}
#fc .panel.warn{border-color:var(--ink3)}
#fc .panel .big{font-family:var(--head);font-weight:600;font-size:19px;letter-spacing:-.01em}
#fc pre{margin:10px 0 0;font-family:var(--mono);font-size:12px;line-height:1.7;white-space:pre-wrap;word-break:break-word;color:var(--ink2);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;max-height:260px;overflow:auto}
#fc .cc{border-radius:14px;padding:22px;background:var(--bg2);border:1px solid var(--line);position:relative;overflow:hidden;max-width:360px}
#fc .cc .brand{font-family:var(--head);font-weight:600;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3)}
#fc .cc .pan{font-family:var(--mono);font-size:20px;letter-spacing:.12em;margin-top:34px;color:var(--ink)}
#fc .cc .row{display:flex;justify-content:space-between;margin-top:16px;font-family:var(--mono);font-size:11px;color:var(--ink2)}
#fc .steps{display:grid;gap:20px;margin-top:26px}
@media(min-width:900px){#fc .steps{grid-template-columns:repeat(3,1fr)}}
#fc .step{border:1px solid var(--line);border-radius:12px;background:var(--card);padding:20px}
#fc .step .n{font-family:var(--head);font-weight:600;font-size:22px;color:var(--ink3)}
#fc .step .t{font-family:var(--head);font-size:16px;font-weight:600;margin-top:10px}
#fc .step .d{color:var(--ink2);font-size:14px;line-height:1.6;margin-top:6px}
#fc details{border-bottom:1px solid var(--line)}
#fc summary{padding:16px 2px;cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:14px;font-family:var(--head);font-size:16px;font-weight:600}
#fc summary::-webkit-details-marker{display:none}
#fc summary:after{content:"+";color:var(--ink3)}
#fc details[open] summary:after{content:"–"}
#fc details p{margin:0;padding:0 2px 18px;color:var(--ink2);font-size:14px;line-height:1.7;max-width:68ch}
#fc footer{padding:32px 0 56px;color:var(--ink3);font-size:13px;border-top:1px solid var(--line);position:relative;z-index:1}
#fc footer .ln{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px}
#fc footer a{color:var(--ink2)}
#fc .disclaimer{font-size:12px;color:var(--ink3);line-height:1.7;max-width:70ch;margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}
#fc [data-pending="1"]{opacity:.5}
#fc .flash{animation:fc-in .25s ease}
@keyframes fc-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
</style>
"""

# Loaded once at the bottom of the page: htmx drives every hx-get/hx-post form and fragment swap
# (including ones added later, like the dashboard) with zero extra JS from us. The only thing htmx
# can't do — sign a message with the visitor's own wallet — gets one small inline script below it.
HTMX_CDN = '<script src="https://unpkg.com/htmx.org@1.9.12" crossorigin="anonymous"></script>'

WALLET_JS = """
<script>
(function () {
  function toHex(bytes) { return "0x" + Array.from(bytes).map(function (b) { return b.toString(16).padStart(2, "0"); }).join(""); }
  document.addEventListener("click", async function (ev) {
    var btn = ev.target.closest && ev.target.closest("[data-fomo-connect]");
    if (!btn) return;
    var kind = btn.dataset.fomoConnect; // "evm" | "solana"
    var form = btn.closest("form");
    var say = function (msg, bad) {
      var out = form.querySelector("[data-fomo-status]");
      if (out) out.innerHTML = bad ? '<span style="color:#ff5470">' + msg + "</span>" : msg;
    };
    var handleInput = form.querySelector('input[name="fomo_handle"]');
    var handle = (handleInput.value || "").trim().replace(/^@/, "");
    if (!handle) { say("enter your FOMO handle first", true); return; }
    btn.disabled = true;
    try {
      var address, signature, message;
      if (kind === "solana") {
        var sol = window.solana;
        if (!sol || !sol.isPhantom) { say("Phantom wallet not found", true); return; }
        var resp = await sol.connect();
        address = resp.publicKey.toString();
        message = "FOMO Card \\u00b7 link " + address + " to @" + handle;
        var signed = await sol.signMessage(new TextEncoder().encode(message), "utf8");
        signature = toHex(signed.signature);
      } else {
        var eth = window.ethereum;
        if (!eth) { say("MetaMask (or another injected wallet) not found", true); return; }
        var accounts = await eth.request({ method: "eth_requestAccounts" });
        address = accounts[0];
        message = "FOMO Card \\u00b7 link " + address + " to @" + handle;
        signature = await eth.request({ method: "personal_sign", params: [message, address] });
      }
      form.querySelector('input[name="fomo_address"]').value = address;
      form.querySelector('input[name="fomo_chain"]').value = kind;
      form.querySelector('input[name="fomo_signature"]').value = signature;
      say("connected " + address.slice(0, 6) + "\\u2026" + address.slice(-4) + " \\u2014 linking\\u2026");
      form.requestSubmit();
    } catch (e) {
      say((e && e.message) || "wallet connection failed", true);
    } finally {
      btn.disabled = false;
    }
  }, true);
})();
</script>
"""

DISCLAIMER = ("FOMO Card is an independent, unofficial product built for fomo.family traders. It is not "
              "affiliated with, endorsed by, or operated by FOMO Labs. Card issuance and funds custody are "
              "handled entirely by the underlying card issuer — FOMO Card never holds your money. No-KYC card "
              "tiers carry real per-transaction and daily spend limits, and issuers can freeze or decline at "
              "their own discretion. This is a minimum-viable product: verify amounts and limits before you rely "
              "on it for real spend.")

FAQ = [
    ("Is this official FOMO Labs?", "No. FOMO Card is an independent, third-party product built on top of "
     "fomoapi.io (an independent FOMO data API) and a no-KYC card issuer. It is not affiliated with FOMO Labs."),
    ("Does FOMO Card hold my money?", "No. You send USDC/SOL/USDT directly from your own FOMO-linked wallet to "
     "the card issuer's deposit address. FOMO Card only reads balances, resolves your handle, and calls the "
     "issuer's API on your behalf — it is never in the custody path."),
    ("Why is there a limit on how much I can load?", "Real no-KYC card tiers cap spend to stay non-KYC — "
     "typically low hundreds to a couple thousand dollars a month. Higher limits or a physical card usually "
     "require a light KYC step with the issuer directly."),
    ("What happens if I reveal my card and lose the tab?", "Nothing is stored — the PAN/CVV are shown to you "
     "once, straight from the issuer, and never written to our database. If you lose it, reveal again (rate "
     "limited) rather than write it down insecurely."),
]


def _bar() -> str:
    return """
<header class="bar"><div class="bar-in">
  <a class="mk" href="/" data-testid="brand-home-link"><i>F</i>FOMO CARD</a>
  <span class="badge">unofficial · not affiliated with FOMO Labs</span>
  <div class="right"></div>
</div></header>"""


def _connect_html() -> str:
    return """
<div class="card" data-testid="fomocard-connect"><header><h3>Connect your FOMO handle</h3><span class="tag">~30 seconds</span></header>
<div class="body">
<form hx-post="/fragment/connect" hx-target="#fc-app" hx-swap="innerHTML" data-testid="fomocard-connect-form">
  <label><span>FOMO handle</span><input name="fomo_handle" placeholder="@yourhandle" maxlength="40" data-testid="fomocard-handle-input"></label>
  <input type="hidden" name="fomo_address"><input type="hidden" name="fomo_chain"><input type="hidden" name="fomo_signature">
  <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
    <button class="btn" type="button" data-fomo-connect="evm" data-testid="fomocard-connect-evm">Connect EVM wallet</button>
    <button class="btn o" type="button" data-fomo-connect="solana" data-testid="fomocard-connect-solana">Connect Phantom (Solana)</button>
  </div>
  <p class="hint" data-fomo-status data-testid="fomocard-connect-status">Signs one message proving you own the wallet linked to your FOMO handle — no funds move, no approval needed.</p>
</form>
</div></div>"""


def _card_action_form(cid: str, handle: str, action: str, label: str, testid: str) -> str:
    return f"""<form hx-post="/fragment/card-action" hx-target="#fc-card-out-{cid}" hx-swap="innerHTML" style="display:inline-block;margin:0">
  <input type="hidden" name="handle" value="{esc(handle)}"><input type="hidden" name="issuer_card_id" value="{cid}"><input type="hidden" name="action" value="{action}">
  <button class="btn o sm" type="submit" data-testid="{testid}">{esc(label)}</button></form>"""


async def _card_html(card: dict, handle: str) -> str:
    status = card.get("status", "active")
    cid = esc(card["issuer_card_id"])
    freeze_action, freeze_label = ("unfreeze", "Unfreeze") if status == "frozen" else ("freeze", "Freeze")
    return f"""
<div class="cc" data-testid="fomocard-card-{cid}">
  <div class="brand">{esc(card.get('brand', 'Visa'))}{' · DEMO' if card.get('demo') else ''}</div>
  <div class="pan">•••• •••• •••• {esc(card.get('last4', '••••'))}</div>
  <div class="row"><span>exp {esc(card.get('expiry', '--/--'))}</span><span>{esc(status).upper()}</span></div>
</div>
<div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">
  {_card_action_form(cid, handle, 'reveal', 'Reveal PAN (once)', 'fomocard-reveal-btn')}
  {_card_action_form(cid, handle, freeze_action, freeze_label, 'fomocard-freeze-btn')}
  {_card_action_form(cid, handle, 'apple-pay', 'Add to Apple Pay', 'fomocard-applepay-btn')}
  {_card_action_form(cid, handle, 'google-pay', 'Add to Google Pay', 'fomocard-googlepay-btn')}
</div>
<div id="fc-card-out-{cid}" class="fc-card-out" style="margin-top:10px"></div>"""


async def _history_html(handle: str) -> str:
    rows = (await fc.list_topups(handle))["topups"]
    if not rows:
        return '<p class="hint" data-testid="fomocard-history-empty">No top-ups yet.</p>'
    body = "".join(f"""<tr><td>{esc(t['created_at'][:19])}</td><td class="tag">{esc(t['status'])}</td>
      <td>${t['amount_usd']:.2f}</td><td>{esc(t['asset'])} · {esc(t['chain'])}</td>
      <td>{esc((t.get('tx_hash') or '—')[:14])}…</td></tr>""" for t in rows)
    return f"""<table><thead><tr><th>when</th><th>status</th><th>amount</th><th>asset</th><th>tx</th></tr></thead><tbody>{body}</tbody></table>"""


async def _dashboard_html(handle: str) -> str:
    try:
        prof = await fc.profile(handle)
    except Exception as e:
        return f'<div class="panel stop flash"><div class="big">Not connected</div><p class="hint">{err_text(e)}</p></div>{_connect_html()}'
    user, bal, cards = prof["user"], prof["balances"], prof["cards"]
    issuer = get_issuer()
    demo = " · DEMO DATA (set FOMOAPI_KEY for live balances)" if user.get("demo_profile") else ""
    bal_rows = "".join(f'<span class="tag">{esc(k)}: {v:g}</span>' for k, v in (bal.get("balances") or {}).items())
    cards_html = "".join([await _card_html(c, handle) for c in cards]) or '<p class="hint">No card yet — load one below.</p>'
    return f"""
<div class="grid g2">
  <div class="card" data-testid="fomocard-dashboard"><header><h3>@{esc(handle)}</h3><span class="tag">{esc(user.get('wallet_chain'))} · {esc(user.get('wallet_address', '')[:6])}…{esc(user.get('wallet_address', '')[-4:])}</span></header>
    <div class="body">
      <div class="hint">Linked balances{demo}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">{bal_rows}</div>
      <div class="hint" style="margin-top:14px">Card issuer: <b>{esc(issuer.name)}</b>{' (demo mode — no real card is issued)' if issuer.name == 'demo' else ''}</div>
      <div style="margin-top:16px">{cards_html}</div>
    </div></div>
  <div class="card"><header><h3>Load FOMO Card</h3><span class="tag">non-custodial</span></header>
    <div class="body">
      <form hx-post="/fragment/topup" hx-target="#fc-topup-out" hx-swap="innerHTML" data-testid="fomocard-topup-form">
        <input type="hidden" name="handle" value="{esc(handle)}">
        <label><span>amount (USD)</span>
          <div class="amts">
            <label><input type="radio" name="amount_usd" value="25"><span>$25</span></label>
            <label><input type="radio" name="amount_usd" value="50" checked><span>$50</span></label>
            <label><input type="radio" name="amount_usd" value="100"><span>$100</span></label>
            <label><input type="radio" name="amount_usd" value="250"><span>$250</span></label>
          </div>
        </label>
        <label><span>asset</span><select name="asset"><option>USDC</option><option>USDT</option><option>SOL</option></select></label>
        <label><span>send from</span><select name="chain"><option value="solana">Solana</option><option value="evm">EVM (Base/ETH)</option></select></label>
        <button class="btn" type="submit" style="margin-top:16px" data-testid="fomocard-topup-submit">Get deposit address</button>
      </form>
      <div id="fc-topup-out" style="margin-top:14px" data-testid="fomocard-topup-out"></div>
    </div></div>
</div>
<div class="card" style="margin-top:20px"><header><h3>Top-up history</h3></header>
  <div class="body" style="overflow:auto" hx-get="/fragment/history?handle={esc(handle)}" hx-trigger="load, every 15s" hx-swap="innerHTML">{await _history_html(handle)}</div></div>"""


@router.get("/health")
async def health():
    return {"ok": True, "issuer": get_issuer().name}


PAGE_TITLE = "FOMO Card"
PAGE_DESCRIPTION = ("FOMO Card is the facilitator for spending your FOMO cash — connect your FOMO "
                    "wallet, load a card, and spend it in real life. Independent, not affiliated with FOMO Labs.")


@router.get("/", response_class=HTMLResponse)
async def page():
    faq = "".join(f'<details{" open" if i == 0 else ""}><summary>{q}</summary><p>{a}</p></details>' for i, (q, a) in enumerate(FAQ))
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(PAGE_TITLE)}</title>
<meta name="description" content="{esc(PAGE_DESCRIPTION)}">
{CSS}
</head>
<body>
<div id="fc">
{_bar()}
<section style="padding-top:48px"><div class="w"><div class="grid" style="grid-template-columns:1fr;gap:32px">
  <div>
    <span class="kick">FOMO Card</span>
    <h1>The facilitator for spending your FOMO cash.</h1>
    <p class="lede">FOMO Card sits between your wallet and a card issuer: connect your FOMO handle, move some balance onto a card, and spend it — online or with Apple Pay / Google Pay. No KYC on the starter tier.</p>
  </div>
  <div id="fc-app" data-testid="fomocard-app">{_connect_html()}</div>
</div></div></section>

<section id="how"><div class="w"><span class="kick">How it works</span><h2>Three steps.</h2>
  <div class="steps">
    <div class="step"><div class="n">1</div><div class="t">Connect</div><div class="d">Sign one message with the wallet linked to your FOMO handle. We resolve your handle through fomoapi.io and read your balances.</div></div>
    <div class="step"><div class="n">2</div><div class="t">Load</div><div class="d">Pick an amount and send USDC/SOL/USDT straight to the card issuer's deposit address — never to us. We watch for confirmation.</div></div>
    <div class="step"><div class="n">3</div><div class="t">Spend</div><div class="d">Once it lands, your card is funded. Add it to Apple Pay or Google Pay, or use the number online. Real limits apply on the no-KYC tier.</div></div>
  </div></div></section>

<section id="faq"><div class="w"><span class="kick">FAQ</span><h2>Questions</h2><div style="margin-top:18px;border-top:1px solid var(--line)">{faq}</div></div></section>

<footer><div class="w"><div>FOMO Card · the facilitator for spending your FOMO cash</div>
<div class="ln"><a href="https://github.com/splashg22/fomo-card" target="_blank" rel="noreferrer">Source on GitHub</a>
<a href="https://fomoapi.io" target="_blank" rel="noreferrer">fomoapi.io</a>
<a href="https://cryptocardium.com" target="_blank" rel="noreferrer">Cryptocardium</a></div>
<div class="disclaimer">{DISCLAIMER}</div></div></footer>
</div>
{HTMX_CDN}
{WALLET_JS}
</body>
</html>""")


@router.get("/fragment/history", response_class=HTMLResponse)
async def fragment_history(handle: str):
    return HTMLResponse(await _history_html(fc._clean_handle(handle)))


@router.post("/fragment/connect", response_class=HTMLResponse)
async def fragment_connect(fomo_handle: str = Form(""), fomo_address: str = Form(""),
                            fomo_chain: str = Form(""), fomo_signature: str = Form("")):
    if not (fomo_handle and fomo_address and fomo_chain and fomo_signature):
        return HTMLResponse(f'<div class="panel stop flash"><div class="big">Connect a wallet first</div>'
                             f'<p class="hint">Enter a handle, then click one of the connect buttons.</p></div>{_connect_html()}')
    try:
        await fc.connect(fc.ConnectRequest(handle=fomo_handle, address=fomo_address, chain=fomo_chain, signature=fomo_signature))
    except Exception as e:
        return HTMLResponse(f'<div class="panel stop flash" data-testid="fomocard-connect-error"><div class="big">Not connected</div>'
                             f'<p class="hint">{err_text(e)}</p></div>{_connect_html()}')
    return HTMLResponse(await _dashboard_html(fc._clean_handle(fomo_handle)))


@router.post("/fragment/topup", response_class=HTMLResponse)
async def fragment_topup(handle: str = Form(""), amount_usd: str = Form("50"), asset: str = Form("USDC"), chain: str = Form("solana")):
    try:
        out = await fc.create_topup(fc.TopupRequest(handle=handle, amount_usd=float(amount_usd), asset=asset, chain=chain))
    except Exception as e:
        return HTMLResponse(f'<div class="panel stop flash" data-testid="fomocard-topup-error"><div class="big">Could not start top-up</div><p class="hint">{err_text(e)}</p></div>')
    t = out["topup"]
    return HTMLResponse(f"""<div class="panel warn flash" data-testid="fomocard-topup-pending">
  <div class="big">Send {t['amount_usd']:g} USD of {esc(t['asset'])}</div>
  <p class="hint">{esc(out['instructions'])}</p>
  <pre data-testid="fomocard-deposit-address">{esc(t['deposit_address'])}</pre>
  <form hx-post="/fragment/confirm" hx-target="#fc-topup-out" hx-swap="innerHTML" style="margin-top:12px" data-testid="fomocard-confirm-form">
    <input type="hidden" name="handle" value="{esc(handle)}"><input type="hidden" name="topup_id" value="{esc(t['id'])}">
    <label><span>transaction hash / signature</span><input name="tx_hash" placeholder="paste it after you send" data-testid="fomocard-tx-input"></label>
    <button class="btn" type="submit" style="margin-top:12px" data-testid="fomocard-confirm-submit">I sent it — confirm</button>
  </form></div>""")


@router.post("/fragment/confirm", response_class=HTMLResponse)
async def fragment_confirm(handle: str = Form(""), topup_id: str = Form(""), tx_hash: str = Form("")):
    try:
        out = await fc.confirm_topup(topup_id, fc.ConfirmRequest(tx_hash=tx_hash))
    except Exception as e:
        return HTMLResponse(f'<div class="panel stop flash" data-testid="fomocard-confirm-error"><div class="big">Not confirmed</div><p class="hint">{err_text(e)}</p></div>')
    if out.get("card"):
        card_html = await _card_html(out["card"], handle)
        return HTMLResponse(f'<div class="panel go flash" data-testid="fomocard-funded"><div class="big">Card funded ✓</div>'
                             f'<p class="hint">Your FOMO Card is live. Add it to Apple/Google Pay below, or reveal the number to spend online.</p>'
                             f'<div style="margin-top:14px">{card_html}</div></div>')
    return HTMLResponse(f'<div class="panel warn flash" data-testid="fomocard-awaiting"><div class="big">Awaiting confirmation</div>'
                         f'<p class="hint">{esc(out.get("note", "still checking — try again shortly"))}</p></div>')


@router.post("/fragment/card-action", response_class=HTMLResponse)
async def fragment_card_action(handle: str = Form(""), issuer_card_id: str = Form(""), action: str = Form("")):
    try:
        if action == "reveal":
            secret = await fc.reveal_card(issuer_card_id, fc.HandleOnly(handle=handle))
            return HTMLResponse(f'<div class="panel warn flash" data-testid="fomocard-reveal-out"><div class="big">One-time reveal</div>'
                                 f'<pre>PAN  {esc(secret.get("pan"))}\nCVV  {esc(secret.get("cvv"))}\nEXP  {esc(secret.get("expiry"))}</pre>'
                                 f'<p class="hint">{esc(secret.get("note", "Shown once — not stored. Refresh to hide it."))}</p></div>')
        if action in ("freeze", "unfreeze"):
            r = await (fc.freeze_card(issuer_card_id, fc.HandleOnly(handle=handle)) if action == "freeze"
                       else fc.unfreeze_card(issuer_card_id, fc.HandleOnly(handle=handle)))
            return HTMLResponse(f'<div class="panel go flash"><div class="big">Card {esc(r["status"])}</div></div>')
        if action in ("apple-pay", "google-pay"):
            r = await (fc.apple_pay(issuer_card_id, handle) if action == "apple-pay" else fc.google_pay(issuer_card_id, handle))
            return HTMLResponse(f'<div class="panel {"go" if r.get("provisioned") else "warn"} flash">'
                                 f'<div class="big">{"Provisioned" if r.get("provisioned") else "Not available yet"}</div>'
                                 f'<p class="hint">{esc(r.get("note", "Check your wallet app to finish adding the card."))}</p></div>')
    except Exception as e:
        return HTMLResponse(f'<div class="panel stop flash"><div class="big">Failed</div><p class="hint">{err_text(e)}</p></div>')
    return HTMLResponse('<div class="panel stop flash"><div class="big">Unknown action</div></div>')
