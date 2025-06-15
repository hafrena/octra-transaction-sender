#!/usr/bin/env python3

import os, sys, json, base64, hashlib, time, re, random, string, requests, datetime
import nacl.signing
from dotenv import load_dotenv
from requests.exceptions import HTTPError

# ---------------------------------------------------------------------------
# Config & env
# ---------------------------------------------------------------------------

load_dotenv()
priv_b64  = os.getenv("PRIVATE_KEY")  # base64‑encoded signing key
from_addr = os.getenv("FROM_ADDRESS") # oct… address
api_url   = "https://octra.network"
scan_url  = "https://octrascan.io/tx"

b58   = re.compile(r"^oct[1-9A-HJ-NP-Za-km-z]{44}$")
micro = 1_000_000
rand  = lambda n=6: ''.join(random.choices(string.ascii_letters+string.digits,k=n))
line  = lambda tag="": print("-"*40, tag or rand(), "-"*40)

ts_iso = lambda ts: datetime.datetime.utcfromtimestamp(float(ts)).isoformat()+"Z" if ts else "-"

okaddr = lambda a: b58.fullmatch(a) is not None
okamt  = lambda x: re.fullmatch(r"\d+(\.\d+)?", x) and float(x) > 0

# ---------------------------------------------------------------------------
# Signing key (только в send‑mode)
# ---------------------------------------------------------------------------
if len(sys.argv) == 1:
    assert priv_b64 and from_addr, "PRIVATE_KEY / FROM_ADDRESS отсутствуют в .env"
    sk      = nacl.signing.SigningKey(base64.b64decode(priv_b64))
    pub_b64 = base64.b64encode(sk.verify_key.encode()).decode()

# ---------------------------------------------------------------------------
# RPC helpers
# ---------------------------------------------------------------------------

def get_state():
    r = requests.get(f"{api_url}/balance/{from_addr}", timeout=10)
    r.raise_for_status()
    j = r.json()
    return j["nonce"], float(j["balance"])


def craft_tx(to: str, amt: float, nonce: int):
    tx = {
        "from": from_addr,
        "to_":  to,
        "amount": str(int(amt*micro)),
        "nonce":  nonce,
        "ou":     "1" if amt < 1000 else "3",
        "timestamp": time.time(),
    }
    blob = json.dumps(tx, separators=(",", ":"))
    sig  = base64.b64encode(sk.sign(blob.encode()).signature).decode()
    tx.update(signature=sig, public_key=pub_b64)
    return tx


def send_tx(tx: dict):
    """POST /send-tx. Возвращает (True, response_dict, dt) или (False, err, dt)."""
    t0 = time.time()
    try:
        r = requests.post(f"{api_url}/send-tx", json=tx, timeout=10)
    except Exception as e:
        return False, str(e), 0.0
    dt = time.time() - t0
    if r.status_code != 200:
        return False, r.text.strip(), dt

    # Пытаемся декодировать
    try:
        j = r.json()
        return True, j, dt
    except ValueError:
        # ответ вида "ok <hash>"
        raw = r.text.strip().lower()
        if raw.startswith("ok"):
            return True, {"tx_hash": raw.split()[-1]}, dt
        return False, raw, dt


def fetch_tx(hash_: str, pending_ok: bool = True):
    """Пробует получить JSON транзы. Если 403 и pending_ok=True — вторая попытка через source=epoch_search."""
    headers = {"accept": "application/json", "user-agent": "octra-cli/1.3"}
    url = f"{api_url}/tx/{hash_}"
    try:
        r = requests.get(url, timeout=10, headers=headers)
        r.raise_for_status()
        return r.json(), False  # not pending
    except HTTPError as he:
        if r.status_code == 403 and pending_ok:
            # пытаемся достать из текущей эпохи
            url2 = url + "?source=epoch_search"
            r2 = requests.get(url2, timeout=10, headers=headers)
            r2.raise_for_status()
            j2 = r2.json()
            return j2, True  # pending (epoch‑search)
        raise


# ---------------------------------------------------------------------------
# Pretty log
# ---------------------------------------------------------------------------

def pretty_log(tx_json: dict, pending: bool = False):
    pt = tx_json.get("parsed_tx", {})
    pad = 11
    def ln(k,v):
        print(f"{k.ljust(pad)}: {v}")

    ln("tx_hash",   tx_json.get("tx_hash","-"))
    ln("from",      pt.get("from","-"))
    ln("to",        pt.get("to","-"))
    ln("amount",    f"{pt.get('amount','-')} OCT")
    ln("nonce",     pt.get("nonce","-"))
    ln("epoch",     tx_json.get("epoch", "-"))
    ln("validator", tx_json.get("validator","-"))
    ln("timestamp", ts_iso(pt.get("timestamp")))
    ln("block_ts",  ts_iso(tx_json.get("block_timestamp")))
    ln("status",    "⏳ pending" if pending else "✔ finalised")
    ln("link",      f"{scan_url}/{tx_json.get('tx_hash','-')}")

# ---------------------------------------------------------------------------
# CLI modes
# ---------------------------------------------------------------------------

def view_mode(hash_: str):
    try:
        tx_json, pending = fetch_tx(hash_)
        pretty_log(tx_json, pending)
    except Exception as e:
        print("error:", e)


def send_mode():
    line("SEND")
    to = input("to: ").strip()
    if not okaddr(to):
        sys.exit("bad addr")
    amt_s = input("amt: ").strip()
    if not okamt(amt_s):
        sys.exit("bad amt")
    amt = float(amt_s)

    nonce, bal = get_state()
    if bal < amt:
        sys.exit("insufficient bal")

    print(f"bal: {bal:.6f}  nonce: {nonce}")
    if input("send? y/n ").lower().strip() != "y":
        sys.exit(0)

    tx = craft_tx(to, amt, nonce+1)
    ok, resp, dt = send_tx(tx)
    if not ok:
        print("fail", resp)
        return

    tx_hash = resp.get("tx_hash")
    epoch    = resp.get("epoch")

    print(f"ok {tx_hash} ({dt:.2f}s)")
    if epoch:
        print(f"epoch: {epoch} (unsealed)")
    print(f"view: {scan_url}/{tx_hash}")

    # Пытаемся подтянуть детали (может вернуть 403)
    try:
        tx_json, pending = fetch_tx(tx_hash)
        pretty_log(tx_json, pending)
    except HTTPError as he:
        if he.response.status_code == 403:
            print("\n⏳ pending: tx ещё не в финальном дереве. Дождитесь конца эпохи.")
        else:
            print("error:", he)
    except Exception as e:
        print("error:", e)
    line()

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) == 2:
        view_mode(sys.argv[1])
    else:
        try:
            send_mode()
        except KeyboardInterrupt:
            print("\naborted")