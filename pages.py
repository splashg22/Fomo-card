"""SOCIAL CASH — the whole standalone site. Dark, quiet, built for social-trading communities.
Unofficial: not affiliated with FOMO Labs or Pump.fun.

No React host here — htmx is loaded straight from a CDN and a small inline script handles the one
thing htmx can't: signing a message with the visitor's own MetaMask/Phantom wallet before a connect
form submits. Everything else (dashboard swaps, polling history, card actions) is plain htmx.
"""
import html as _html

from card_issuer import get_issuer
from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

import socialcash as sc

router = APIRouter(tags=["site"])


def esc(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


def err_text(e) -> str:
    return str(getattr(e, "detail", e))


def short(addr: str) -> str:
    addr = addr or ""
    return f"{addr[:6]}…{addr[-4:]}" if len(addr) > 12 else addr


CSS = """
<style>
#sc{--bg:#0b0c0a;--bg2:#141613;--card:#171915;--ink:#eef1ec;--ink2:#9aa39c;--ink3:#666e68;--line:#262a24;
--pump:#00e676;--fomo:#ff5a36;--accent:var(--pump);--bad:#ff5c5c;--good:var(--pump);
--head:"Archivo","Space Grotesk",sans-serif;--mono:"IBM Plex Mono",ui-monospace,monospace;--sans:Inter,-apple-system,system-ui,sans-serif;
background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.55;min-height:100vh}
#sc *{box-sizing:border-box}
#sc ::selection{background:var(--pump);color:#0b0c0a}
#sc a{color:var(--pump);text-decoration:none}
#sc .w{max-width:1080px;margin:0 auto;padding:0 24px}
#sc .bar{position:sticky;top:0;z-index:40;background:rgba(11,12,10,.9);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
#sc .bar-in{display:flex;align-items:center;gap:20px;padding:16px 24px;max-width:1200px;margin:0 auto}
#sc .mk{font-family:var(--head);font-weight:700;font-size:18px;letter-spacing:-.01em;display:flex;align-items:center;gap:8px;color:var(--ink)}
#sc .mk i{width:26px;height:26px;background:linear-gradient(135deg,var(--pump),var(--fomo));border-radius:7px;display:grid;place-items:center;font-size:12px;font-weight:800;color:#0b0c0a;font-style:normal}
#sc .right{margin-left:auto}
#sc .badge{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--ink3);border:1px solid var(--line);border-radius:999px;padding:5px 12px;background:var(--bg2)}
#sc section{padding:56px 0;position:relative;z-index:1}
#sc .kick{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3)}
#sc .platforms{display:inline-flex;gap:8px;margin-top:14px}
#sc .ptag{font-family:var(--mono);font-size:11px;letter-spacing:.06em;border:1px solid;border-radius:999px;padding:4px 11px;font-weight:600}
#sc .ptag.fomo{color:var(--fomo);border-color:var(--fomo)}
#sc .ptag.pump{color:var(--pump);border-color:var(--pump)}
#sc h1{font-family:var(--head);font-size:clamp(30px,4.4vw,48px);line-height:1.08;margin:14px 0 0;font-weight:700;letter-spacing:-.015em;color:var(--ink)}
#sc h2{font-family:var(--head);font-size:clamp(22px,2.6vw,28px);margin:0 0 20px;font-weight:700;letter-spacing:-.01em}
#sc p.lede{color:var(--ink2);max-width:56ch;margin:18px 0 0;font-size:17px;line-height:1.65}
#sc .grid{display:grid;gap:20px}
@media(min-width:900px){#sc .g2{grid-template-columns:1fr 1fr}#sc .g3{grid-template-columns:repeat(3,1fr)}}
#sc .card{border:1px solid var(--line);border-top:3px solid var(--line);border-radius:16px;background:var(--card);overflow:hidden}
#sc .card.fomo{border-top-color:var(--fomo)}
#sc .card.pump{border-top-color:var(--pump)}
#sc .card>header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:10px}
#sc .card>header h3{margin:0;font-family:var(--head);font-size:15px;font-weight:700}
#sc .card .body{padding:18px}
#sc label{display:block;margin-top:12px}
#sc label span{font-size:12px;font-weight:600;color:var(--ink2)}
#sc input,#sc select{width:100%;margin-top:6px;background:var(--bg2);border:1px solid var(--line);border-radius:10px;color:var(--ink);font-family:var(--mono);font-size:14px;padding:11px 12px;outline:none}
#sc input:focus,#sc select:focus{border-color:var(--accent)}
#sc .hint{font-size:13px;color:var(--ink3);margin-top:8px;line-height:1.6}
#sc .btn{font-family:var(--head);font-weight:700;font-size:14px;padding:11px 18px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#0b0c0a;cursor:pointer;transition:opacity .15s,transform .1s}
#sc .btn:hover{opacity:.88}
#sc .btn:active{opacity:.75;transform:scale(.98)}
#sc .btn.o{background:transparent;border-color:var(--line);color:var(--ink)}
#sc .btn.fomo{background:var(--fomo);border-color:var(--fomo);color:#1a0800}
#sc .btn.fomo.o{background:transparent;color:var(--fomo)}
#sc .btn.pump{background:var(--pump);border-color:var(--pump);color:#04140a}
#sc .btn.pump.o{background:transparent;color:var(--pump)}
#sc .btn.sm{padding:7px 12px;font-size:12px}
#sc .btn[disabled]{opacity:.4;cursor:default}
#sc .amts{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
#sc .amts label{margin:0;flex:1;min-width:64px}
#sc .amts input{display:none}
#sc .amts span{display:block;text-align:center;border:1px solid var(--line);border-radius:8px;padding:9px;font-family:var(--mono);font-weight:600;cursor:pointer;background:var(--bg2);color:var(--ink2)}
#sc .amts input:checked+span{background:var(--bg2);color:var(--ink);border-color:var(--accent)}
#sc table{width:100%;border-collapse:collapse;font-size:13px;font-family:var(--mono)}
#sc th{text-align:left;font-family:var(--sans);font-weight:600;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink3);padding:10px 14px;border-bottom:1px solid var(--line);white-space:nowrap}
#sc td{padding:11px 14px;border-bottom:1px solid var(--line);white-space:nowrap;color:var(--ink2)}
#sc tbody tr:last-child td{border-bottom:0}
#sc .tag{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-family:var(--mono);font-size:11px;background:var(--bg2);color:var(--ink2)}
#sc .panel{border:1px solid var(--line);border-radius:12px;background:var(--bg2);padding:20px}
#sc .panel.go{border-color:var(--good)}
#sc .panel.stop{border-color:var(--bad)}
#sc .panel.warn{border-color:var(--ink3)}
#sc .panel .big{font-family:var(--head);font-weight:600;font-size:19px;letter-spacing:-.01em}
#sc pre{margin:10px 0 0;font-family:var(--mono);font-size:12px;line-height:1.7;white-space:pre-wrap;word-break:break-word;color:var(--ink2);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;max-height:260px;overflow:auto}
#sc .cc{border-radius:14px;padding:22px;background:var(--bg2);border:1px solid var(--line);position:relative;overflow:hidden;max-width:360px}
#sc .cc:before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--fomo),var(--pump))}
#sc .cc .brand{font-family:var(--head);font-weight:600;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3)}
#sc .cc .pan{font-family:var(--mono);font-size:20px;letter-spacing:.12em;margin-top:34px;color:var(--ink)}
#sc .cc .row{display:flex;justify-content:space-between;margin-top:16px;font-family:var(--mono);font-size:11px;color:var(--ink2)}
#sc .steps{display:grid;gap:20px;margin-top:26px}
@media(min-width:900px){#sc .steps{grid-template-columns:repeat(3,1fr)}}
#sc .step{border:1px solid var(--line);border-radius:12px;background:var(--card);padding:20px}
#sc .step .n{font-family:var(--head);font-weight:600;font-size:22px;color:var(--ink3)}
#sc .step .t{font-family:var(--head);font-size:16px;font-weight:600;margin-top:10px}
#sc .step .d{color:var(--ink2);font-size:14px;line-height:1.6;margin-top:6px}
#sc details{border-bottom:1px solid var(--line)}
#sc summary{padding:16px 2px;cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:14px;font-family:var(--head);font-size:16px;font-weight:600}
#sc summary::-webkit-details-marker{display:none}
#sc summary:after{content:"+";color:var(--ink3)}
#sc details[open] summary:after{content:"–"}
#sc details p{margin:0;padding:0 2px 18px;color:var(--ink2);font-size:14px;line-height:1.7;max-width:68ch}
#sc footer{padding:32px 0 56px;color:var(--ink3);font-size:13px;border-top:1px solid var(--line);position:relative;z-index:1}
#sc footer .ln{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px}
#sc footer a{color:var(--ink2)}
#sc .disclaimer{font-size:12px;color:var(--ink3);line-height:1.7;max-width:70ch;margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}
#sc [data-pending="1"]{opacity:.5}
#sc .flash{animation:sc-in .25s ease}
@keyframes sc-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
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
    var btn = ev.target.closest && ev.target.closest("[data-connect]");
    if (!btn) return;
    var kind = btn.dataset.connect;       // "evm" | "solana"
    var platform = btn.dataset.platform;  // "fomo" | "pumpfun"
    var form = btn.closest("form");
    var say = function (msg, bad) {
      var out = form.querySelector("[data-status]");
      if (out) out.innerHTML = bad ? '<span style="color:#b97575">' + msg + "</span>" : msg;
    };
    var handle = "";
    if (platform === "fomo") {
      handle = (form.querySelector('input[name="handle"]').value || "").trim().replace(/^@/, "");
      if (!handle) return say("enter your FOMO handle first", true);
    }
    btn.disabled = true;
    try {
      var address, signature;
      if (kind === "solana") {
        var sol = window.solana;
        if (!sol || !sol.isPhantom) return say("Phantom wallet not found", true);
        var resp = await sol.connect();
        address = resp.publicKey.toString();
        var message = platform === "pumpfun"
          ? "Social Cash \\u00b7 use " + address + " as my Pump.fun wallet"
          : "Social Cash \\u00b7 link " + address + " to @" + handle + " on FOMO";
        var signed = await sol.signMessage(new TextEncoder().encode(message), "utf8");
        signature = toHex(signed.signature);
      } else {
        var eth = window.ethereum;
        if (!eth) return say("MetaMask (or another injected wallet) not found", true);
        var accounts = await eth.request({ method: "eth_requestAccounts" });
        address = accounts[0];
        var message2 = "Social Cash \\u00b7 link " + address + " to @" + handle + " on FOMO";
        signature = await eth.request({ method: "personal_sign", params: [message2, address] });
      }
      if (platform === "fomo") form.querySelector('input[name="handle"]').value = handle;
      form.querySelector('input[name="address"]').value = address;
      form.querySelector('input[name="chain"]').value = kind;
      form.querySelector('input[name="signature"]').value = signature;
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

DISCLAIMER = ("Social Cash is an independent, unofficial product for social-trading communities. It is "
              "not affiliated with, endorsed by, or operated by FOMO Labs or Pump.fun. Card issuance and "
              "funds custody are handled entirely by the underlying card issuer — Social Cash never holds "
              "your money. No-KYC card tiers carry real per-transaction and daily spend limits, and issuers "
              "can freeze or decline at their own discretion. This is a minimum-viable product: verify "
              "amounts and limits before you rely on it for real spend.")

FAQ = [
    ("Is this official FOMO Labs or Pump.fun?", "No. Social Cash is an independent, third-party product. "
     "For FOMO it uses fomoapi.io (an independent FOMO data API); for Pump.fun it just reads your connected "
     "wallet's own balance on-chain. It isn't affiliated with FOMO Labs or Pump.fun."),
    ("Does Social Cash hold my money?", "No. You send USDC/SOL/USDT directly from your own wallet to "
     "the card issuer's deposit address. Social Cash only reads balances and calls the issuer's API on "
     "your behalf — it is never in the custody path."),
    ("Why is there a limit on how much I can load?", "Real no-KYC card tiers cap spend to stay non-KYC — "
     "typically low hundreds to a couple thousand dollars a month. Higher limits or a physical card usually "
     "require a light KYC step with the issuer directly."),
    ("How is Pump.fun different from FOMO here?", "FOMO has a handle that fomoapi.io resolves to your "
     "linked wallets. Pump.fun doesn't need that — your connected Solana wallet already is your account, "
     "so there's no handle to type, just a wallet to connect."),
    ("What happens if I reveal my card and lose the tab?", "Nothing is stored — the PAN/CVV are shown to you "
     "once, straight from the issuer, and never written to our database. If you lose it, reveal again (rate "
     "limited) rather than write it down insecurely."),
]


def _bar() -> str:
    return """
<header class="bar"><div class="bar-in">
  <a class="mk" href="/" data-testid="brand-home-link"><i>S</i>SOCIAL CASH</a>
  <span class="badge">unofficial · not affiliated with FOMO Labs or Pump.fun</span>
  <div class="right"></div>
</div></header>"""


def _connect_html() -> str:
    return """
<div class="grid g2">
  <div class="card fomo" data-testid="fomo-connect"><header><h3>FOMO account</h3><span class="tag" style="border-color:var(--fomo);color:var(--fomo)">~30 seconds</span></header>
  <div class="body">
  <form hx-post="/fragment/connect" hx-target="#app" hx-swap="innerHTML" data-testid="fomo-connect-form">
    <input type="hidden" name="platform" value="fomo">
    <label><span>FOMO handle</span><input name="handle" placeholder="@yourhandle" maxlength="40" data-testid="fomo-handle-input"></label>
    <input type="hidden" name="address"><input type="hidden" name="chain"><input type="hidden" name="signature">
    <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
      <button class="btn fomo" type="button" data-connect="evm" data-platform="fomo" data-testid="fomo-connect-evm">Connect EVM wallet</button>
      <button class="btn fomo o" type="button" data-connect="solana" data-platform="fomo" data-testid="fomo-connect-solana">Connect Phantom</button>
    </div>
    <p class="hint" data-status data-testid="fomo-connect-status">Signs one message proving you own the wallet linked to your FOMO handle — no funds move.</p>
  </form>
  </div></div>

  <div class="card pump" data-testid="pumpfun-connect"><header><h3>Pump.fun wallet</h3><span class="tag" style="border-color:var(--pump);color:var(--pump)">Solana only</span></header>
  <div class="body">
  <form hx-post="/fragment/connect" hx-target="#app" hx-swap="innerHTML" data-testid="pumpfun-connect-form">
    <input type="hidden" name="platform" value="pumpfun">
    <input type="hidden" name="handle" value="">
    <input type="hidden" name="address"><input type="hidden" name="chain"><input type="hidden" name="signature">
    <p class="hint" style="margin-top:0">Pump.fun has no separate handle — your connected wallet is the account.</p>
    <div style="display:flex;gap:10px;margin-top:12px;flex-wrap:wrap">
      <button class="btn pump" type="button" data-connect="solana" data-platform="pumpfun" data-testid="pumpfun-connect-solana">Connect Phantom</button>
    </div>
    <p class="hint" data-status data-testid="pumpfun-connect-status">Signs one message proving you own this wallet — no funds move.</p>
  </form>
  </div></div>
</div>"""


def _card_action_form(cid: str, platform: str, identity: str, action: str, label: str, testid: str) -> str:
    tone = "fomo" if platform == "fomo" else "pump"
    return f"""<form hx-post="/fragment/card-action" hx-target="#card-out-{cid}" hx-swap="innerHTML" style="display:inline-block;margin:0">
  <input type="hidden" name="platform" value="{esc(platform)}"><input type="hidden" name="identity" value="{esc(identity)}">
  <input type="hidden" name="issuer_card_id" value="{cid}"><input type="hidden" name="action" value="{action}">
  <button class="btn {tone} o sm" type="submit" data-testid="{testid}">{esc(label)}</button></form>"""


async def _card_html(card: dict, platform: str, identity: str) -> str:
    status = card.get("status", "active")
    cid = esc(card["issuer_card_id"])
    freeze_action, freeze_label = ("unfreeze", "Unfreeze") if status == "frozen" else ("freeze", "Freeze")
    return f"""
<div class="cc" data-testid="card-{cid}">
  <div class="brand">{esc(card.get('brand', 'Visa'))}{' · DEMO' if card.get('demo') else ''}</div>
  <div class="pan">•••• •••• •••• {esc(card.get('last4', '••••'))}</div>
  <div class="row"><span>exp {esc(card.get('expiry', '--/--'))}</span><span>{esc(status).upper()}</span></div>
</div>
<div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap">
  {_card_action_form(cid, platform, identity, 'reveal', 'Reveal PAN (once)', 'reveal-btn')}
  {_card_action_form(cid, platform, identity, freeze_action, freeze_label, 'freeze-btn')}
  {_card_action_form(cid, platform, identity, 'apple-pay', 'Add to Apple Pay', 'applepay-btn')}
  {_card_action_form(cid, platform, identity, 'google-pay', 'Add to Google Pay', 'googlepay-btn')}
</div>
<div id="card-out-{cid}" style="margin-top:10px"></div>"""


async def _history_html(platform: str, identity: str) -> str:
    rows = (await sc.list_topups(platform, identity))["topups"]
    if not rows:
        return '<p class="hint" data-testid="history-empty">No top-ups yet.</p>'
    body = "".join(f"""<tr><td>{esc(t['created_at'][:19])}</td><td class="tag">{esc(t['status'])}</td>
      <td>${t['amount_usd']:.2f}</td><td>{esc(t['asset'])} · {esc(t['chain'])}</td>
      <td>{esc((t.get('tx_hash') or '—')[:14])}…</td></tr>""" for t in rows)
    return f"""<table><thead><tr><th>when</th><th>status</th><th>amount</th><th>asset</th><th>tx</th></tr></thead><tbody>{body}</tbody></table>"""


async def _dashboard_html(platform: str, identity: str) -> str:
    try:
        prof = await sc.profile(platform, identity)
    except Exception as e:
        return f'<div class="panel stop flash"><div class="big">Not connected</div><p class="hint">{err_text(e)}</p></div>{_connect_html()}'
    user, bal, cards = prof["user"], prof["balances"], prof["cards"]
    issuer = get_issuer()
    platform_label = "FOMO" if platform == "fomo" else "Pump.fun"
    ident_display = f"@{identity}" if platform == "fomo" else short(identity)
    demo = " · DEMO DATA (set FOMOAPI_KEY for live balances)" if user.get("demo_profile") else ""
    bal_rows = "".join(f'<span class="tag">{esc(k)}: {v:g}</span>' for k, v in (bal.get("balances") or {}).items())
    cards_html = "".join([await _card_html(c, platform, identity) for c in cards]) or '<p class="hint">No card yet — load one below.</p>'
    chain_options = '<option value="solana">Solana</option>' + ('' if platform == "pumpfun" else '<option value="evm">EVM (Base/ETH)</option>')
    platform_css = "fomo" if platform == "fomo" else "pump"
    platform_color = "var(--fomo)" if platform == "fomo" else "var(--pump)"
    return f"""
<div class="grid g2">
  <div class="card {platform_css}" data-testid="dashboard"><header><h3>{esc(platform_label)} · {esc(ident_display)}</h3><span class="tag" style="border-color:{platform_color};color:{platform_color}">{esc(user.get('wallet_chain'))} · {esc(short(user.get('wallet_address', '')))}</span></header>
    <div class="body">
      <div class="hint">Linked balances{demo}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">{bal_rows}</div>
      <div class="hint" style="margin-top:14px">Card issuer: <b>{esc(issuer.name)}</b>{' (demo mode — no real card is issued)' if issuer.name == 'demo' else ''}</div>
      <div style="margin-top:16px">{cards_html}</div>
    </div></div>
  <div class="card"><header><h3>Load a card</h3><span class="tag">non-custodial</span></header>
    <div class="body">
      <form hx-post="/fragment/topup" hx-target="#topup-out" hx-swap="innerHTML" data-testid="topup-form">
        <input type="hidden" name="platform" value="{esc(platform)}">
        <input type="hidden" name="identity" value="{esc(identity)}">
        <label><span>amount (USD)</span>
          <div class="amts">
            <label><input type="radio" name="amount_usd" value="25"><span>$25</span></label>
            <label><input type="radio" name="amount_usd" value="50" checked><span>$50</span></label>
            <label><input type="radio" name="amount_usd" value="100"><span>$100</span></label>
            <label><input type="radio" name="amount_usd" value="250"><span>$250</span></label>
          </div>
        </label>
        <label><span>asset</span><select name="asset"><option>USDC</option><option>USDT</option><option>SOL</option></select></label>
        <label><span>send from</span><select name="chain">{chain_options}</select></label>
        <button class="btn" type="submit" style="margin-top:16px" data-testid="topup-submit">Get deposit address</button>
      </form>
      <div id="topup-out" style="margin-top:14px" data-testid="topup-out"></div>
    </div></div>
</div>
<div class="card" style="margin-top:20px"><header><h3>Top-up history</h3></header>
  <div class="body" style="overflow:auto" hx-get="/fragment/history?platform={esc(platform)}&identity={esc(identity)}" hx-trigger="load, every 15s" hx-swap="innerHTML">{await _history_html(platform, identity)}</div></div>"""


PAGE_TITLE = "Social Cash"
PAGE_DESCRIPTION = ("Social Cash is the facilitator for spending your FOMO or Pump.fun balance — connect "
                    "your account, load a card, and spend it in real life. Independent, not affiliated "
                    "with FOMO Labs or Pump.fun.")


@router.get("/health")
async def health():
    return {"ok": True, "issuer": get_issuer().name}


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
<div id="sc">
{_bar()}
<section style="padding-top:48px"><div class="w"><div class="grid" style="grid-template-columns:1fr;gap:32px">
  <div>
    <span class="kick">Social Cash</span>
    <h1>The facilitator for spending your social trading cash.</h1>
    <p class="lede">Connect a FOMO handle or a Pump.fun wallet, move some balance onto a card, and spend it — online or with Apple Pay / Google Pay. No KYC on the starter tier.</p>
    <div class="platforms"><span class="ptag fomo">FOMO</span><span class="ptag pump">PUMP.FUN</span></div>
  </div>
  <div id="app" data-testid="app">{_connect_html()}</div>
</div></div></section>

<section id="how"><div class="w"><span class="kick">How it works</span><h2>Three steps.</h2>
  <div class="steps">
    <div class="step"><div class="n">1</div><div class="t">Connect</div><div class="d">Sign one message with your wallet. FOMO resolves your handle through fomoapi.io; Pump.fun just uses the wallet you connect.</div></div>
    <div class="step"><div class="n">2</div><div class="t">Load</div><div class="d">Pick an amount and send USDC/SOL/USDT straight to the card issuer's deposit address — never to us. We watch for confirmation.</div></div>
    <div class="step"><div class="n">3</div><div class="t">Spend</div><div class="d">Once it lands, your card is funded. Add it to Apple Pay or Google Pay, or use the number online. Real limits apply on the no-KYC tier.</div></div>
  </div></div></section>

<section id="faq"><div class="w"><span class="kick">FAQ</span><h2>Questions</h2><div style="margin-top:18px;border-top:1px solid var(--line)">{faq}</div></div></section>

<footer><div class="w"><div>Social Cash · the facilitator for spending your social trading cash</div>
<div class="ln"><a href="https://github.com/splashg22/fomo-card" target="_blank" rel="noreferrer">Source on GitHub</a>
<a href="https://fomoapi.io" target="_blank" rel="noreferrer">fomoapi.io</a>
<a href="https://cryptocardium.com" target="_blank" rel="noreferrer">Cryptocardium</a>
<a href="https://pump.fun" target="_blank" rel="noreferrer">Pump.fun</a></div>
<div class="disclaimer">{DISCLAIMER}</div></div></footer>
</div>
{HTMX_CDN}
{WALLET_JS}
</body>
</html>""")


@router.get("/fragment/history", response_class=HTMLResponse)
async def fragment_history(platform: str, identity: str):
    return HTMLResponse(await _history_html(platform, sc._norm_identity(platform, identity)))


@router.post("/fragment/connect", response_class=HTMLResponse)
async def fragment_connect(platform: str = Form(""), handle: str = Form(""), address: str = Form(""),
                            chain: str = Form(""), signature: str = Form("")):
    if not (platform and address and chain and signature) or (platform == "fomo" and not handle.strip()):
        return HTMLResponse(f'<div class="panel stop flash"><div class="big">Connect a wallet first</div>'
                             f'<p class="hint">Fill in the form, then click connect.</p></div>{_connect_html()}')
    try:
        out = await sc.connect(sc.ConnectRequest(platform=platform, handle=handle, address=address, chain=chain, signature=signature))
    except Exception as e:
        return HTMLResponse(f'<div class="panel stop flash" data-testid="connect-error"><div class="big">Not connected</div>'
                             f'<p class="hint">{err_text(e)}</p></div>{_connect_html()}')
    return HTMLResponse(await _dashboard_html(platform, out["user"]["identity"]))


@router.post("/fragment/topup", response_class=HTMLResponse)
async def fragment_topup(platform: str = Form(""), identity: str = Form(""), amount_usd: str = Form("50"),
                          asset: str = Form("USDC"), chain: str = Form("solana")):
    try:
        out = await sc.create_topup(sc.TopupRequest(platform=platform, identity=identity, amount_usd=float(amount_usd), asset=asset, chain=chain))
    except Exception as e:
        return HTMLResponse(f'<div class="panel stop flash" data-testid="topup-error"><div class="big">Could not start top-up</div><p class="hint">{err_text(e)}</p></div>')
    t = out["topup"]
    return HTMLResponse(f"""<div class="panel warn flash" data-testid="topup-pending">
  <div class="big">Send {t['amount_usd']:g} USD of {esc(t['asset'])}</div>
  <p class="hint">{esc(out['instructions'])}</p>
  <pre data-testid="deposit-address">{esc(t['deposit_address'])}</pre>
  <form hx-post="/fragment/confirm" hx-target="#topup-out" hx-swap="innerHTML" style="margin-top:12px" data-testid="confirm-form">
    <input type="hidden" name="platform" value="{esc(platform)}"><input type="hidden" name="identity" value="{esc(identity)}">
    <input type="hidden" name="topup_id" value="{esc(t['id'])}">
    <label><span>transaction hash / signature</span><input name="tx_hash" placeholder="paste it after you send" data-testid="tx-input"></label>
    <button class="btn" type="submit" style="margin-top:12px" data-testid="confirm-submit">I sent it — confirm</button>
  </form></div>""")


@router.post("/fragment/confirm", response_class=HTMLResponse)
async def fragment_confirm(platform: str = Form(""), identity: str = Form(""), topup_id: str = Form(""), tx_hash: str = Form("")):
    try:
        out = await sc.confirm_topup(topup_id, sc.ConfirmRequest(tx_hash=tx_hash))
    except Exception as e:
        return HTMLResponse(f'<div class="panel stop flash" data-testid="confirm-error"><div class="big">Not confirmed</div><p class="hint">{err_text(e)}</p></div>')
    if out.get("card"):
        card_html = await _card_html(out["card"], platform, identity)
        return HTMLResponse(f'<div class="panel go flash" data-testid="funded"><div class="big">Card funded ✓</div>'
                             f'<p class="hint">Your card is live. Add it to Apple/Google Pay below, or reveal the number to spend online.</p>'
                             f'<div style="margin-top:14px">{card_html}</div></div>')
    return HTMLResponse(f'<div class="panel warn flash" data-testid="awaiting"><div class="big">Awaiting confirmation</div>'
                         f'<p class="hint">{esc(out.get("note", "still checking — try again shortly"))}</p></div>')


@router.post("/fragment/card-action", response_class=HTMLResponse)
async def fragment_card_action(platform: str = Form(""), identity: str = Form(""), issuer_card_id: str = Form(""), action: str = Form("")):
    try:
        if action == "reveal":
            secret = await sc.reveal_card(issuer_card_id, sc.IdentityOnly(platform=platform, identity=identity))
            return HTMLResponse(f'<div class="panel warn flash" data-testid="reveal-out"><div class="big">One-time reveal</div>'
                                 f'<pre>PAN  {esc(secret.get("pan"))}\nCVV  {esc(secret.get("cvv"))}\nEXP  {esc(secret.get("expiry"))}</pre>'
                                 f'<p class="hint">{esc(secret.get("note", "Shown once — not stored. Refresh to hide it."))}</p></div>')
        if action in ("freeze", "unfreeze"):
            r = await (sc.freeze_card(issuer_card_id, sc.IdentityOnly(platform=platform, identity=identity)) if action == "freeze"
                       else sc.unfreeze_card(issuer_card_id, sc.IdentityOnly(platform=platform, identity=identity)))
            return HTMLResponse(f'<div class="panel go flash"><div class="big">Card {esc(r["status"])}</div></div>')
        if action in ("apple-pay", "google-pay"):
            r = await (sc.apple_pay(issuer_card_id, platform, identity) if action == "apple-pay" else sc.google_pay(issuer_card_id, platform, identity))
            return HTMLResponse(f'<div class="panel {"go" if r.get("provisioned") else "warn"} flash">'
                                 f'<div class="big">{"Provisioned" if r.get("provisioned") else "Not available yet"}</div>'
                                 f'<p class="hint">{esc(r.get("note", "Check your wallet app to finish adding the card."))}</p></div>')
    except Exception as e:
        return HTMLResponse(f'<div class="panel stop flash"><div class="big">Failed</div><p class="hint">{err_text(e)}</p></div>')
    return HTMLResponse('<div class="panel stop flash"><div class="big">Unknown action</div></div>')
