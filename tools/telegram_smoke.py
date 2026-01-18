# tools/telegram_smoke.py
"""
Telegram smoke tester for tg-shop-ai bot.

What it checks:
- Network access to api.telegram.org:443
- BOT_TOKEN presence in env or .env
- Telegram Bot API availability via getMe
- Optional: getWebhookInfo, getUpdates (non-destructive)
- Produces a JSON report to attach as evidence if needed

Usage:
  python tools/telegram_smoke.py
  python tools/telegram_smoke.py --token YOUR_TOKEN
  python tools/telegram_smoke.py --out data/telegram_smoke_report.json
  python tools/telegram_smoke.py --updates --limit 5

Notes:
- This does NOT send messages to users.
- It only calls read-only Bot API methods.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
import ssl
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ---------------------------
# Minimal dotenv reader
# ---------------------------

def read_dotenv(dotenv_path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not dotenv_path.exists():
        return data
    for raw in dotenv_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            data[k] = v
    return data


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


# ---------------------------
# Networking checks
# ---------------------------

def tcp_check(host: str, port: int, timeout_s: float = 4.0) -> Tuple[bool, str]:
    """
    Tries to connect to host:port with TCP.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True, "ok"
    except Exception as e:
        return False, str(e)


def tls_check(host: str, port: int, timeout_s: float = 4.0) -> Tuple[bool, str]:
    """
    Tries to establish a TLS handshake (useful when TCP is ok but SSL is blocked).
    """
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout_s) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                return True, "ok"
    except Exception as e:
        return False, str(e)


# ---------------------------
# Telegram Bot API client
# ---------------------------

class TgApi:
    def __init__(self, token: str, timeout_s: float = 6.0, retries: int = 1, retry_sleep_s: float = 0.6):
        self.token = token.strip()
        self.timeout_s = timeout_s
        self.retries = retries
        self.retry_sleep_s = retry_sleep_s
        self.base = f"https://api.telegram.org/bot{self.token}/"

    def _call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Optional[int], Dict[str, Any], str]:
        """
        Returns: (status_code, json_payload, error_string)
        """
        url = self.base + method
        if params:
            url = url + "?" + urlencode(params, doseq=True)

        req = Request(url=url, method="GET")
        req.add_header("User-Agent", "tg-shop-ai-telegram-smoke/1.0")
        req.add_header("Accept", "application/json")

        attempts = max(1, self.retries + 1)
        last_err = ""
        for i in range(attempts):
            try:
                start = time.time()
                with urlopen(req, timeout=self.timeout_s) as resp:
                    status = getattr(resp, "status", 200)
                    body = resp.read()
                elapsed_ms = int((time.time() - start) * 1000)

                try:
                    payload = json.loads(body.decode("utf-8", errors="replace"))
                except Exception as e:
                    return int(status), {}, f"JSON decode error: {e}"

                # Attach elapsed for debugging
                if isinstance(payload, dict):
                    payload["_elapsed_ms"] = elapsed_ms

                return int(status), payload if isinstance(payload, dict) else {}, ""
            except HTTPError as e:
                # HTTPError can have JSON body
                try:
                    body = e.read()
                    payload = json.loads(body.decode("utf-8", errors="replace"))
                    if isinstance(payload, dict):
                        return int(e.code), payload, f"HTTPError: {e.code} {e.reason}"
                except Exception:
                    pass
                return int(e.code), {}, f"HTTPError: {e.code} {e.reason}"
            except URLError as e:
                last_err = f"URLError: {getattr(e, 'reason', e)}"
            except Exception as e:
                last_err = f"Exception: {e}"

            if i < attempts - 1:
                time.sleep(self.retry_sleep_s)

        return None, {}, last_err or "Unknown error"


# ---------------------------
# Report model
# ---------------------------

@dataclass
class TelegramSmokeReport:
    tool: str
    created_at: str
    ok: bool
    token_present: bool
    network_tcp_ok: bool
    network_tls_ok: bool
    getme_ok: bool
    getme_username: str
    getme_id: str
    webhook_ok: bool
    updates_ok: bool
    errors: Dict[str, str]
    raw: Dict[str, Any]


def mask_token(token: str) -> str:
    token = token.strip()
    if len(token) < 10:
        return "***"
    return token[:6] + "..." + token[-4:]


def find_token(cli_token: str) -> Tuple[str, bool, str]:
    """
    Returns: (token, present, source)
    """
    if cli_token:
        return cli_token.strip(), True, "cli"

    # env
    for k in ("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TG_BOT_TOKEN"):
        v = os.environ.get(k, "").strip()
        if v:
            return v, True, f"env:{k}"

    # .env
    root = Path(__file__).resolve().parents[1]
    env_map = read_dotenv(root / ".env")
    for k in ("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TG_BOT_TOKEN"):
        v = env_map.get(k, "").strip()
        if v:
            return v, True, f".env:{k}"

    return "", False, "not_found"


# ---------------------------
# Main
# ---------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="telegram_smoke.py",
        description="Telegram smoke tester for tg-shop-ai bot (read-only API calls).",
    )
    p.add_argument("--token", default="", help="Bot token (optional; otherwise uses env/.env BOT_TOKEN).")
    p.add_argument("--timeout", type=float, default=6.0, help="HTTP timeout (seconds).")
    p.add_argument("--retries", type=int, default=1, help="Retries for URLError/Exceptions.")
    p.add_argument("--updates", action="store_true", help="Also call getUpdates (read-only).")
    p.add_argument("--limit", type=int, default=5, help="getUpdates limit (default 5).")
    p.add_argument("--out", default="data/telegram_smoke_report.json", help="Output report path (JSON).")
    return p


def main(argv: Sequence[str]) -> int:
    args = build_parser().parse_args(argv)

    token, present, source = find_token(args.token)

    errors: Dict[str, str] = {}
    raw: Dict[str, Any] = {"token_source": source, "token_masked": mask_token(token) if token else ""}

    # Network checks
    tcp_ok, tcp_msg = tcp_check("api.telegram.org", 443, timeout_s=4.0)
    tls_ok, tls_msg = tls_check("api.telegram.org", 443, timeout_s=4.0)

    if not tcp_ok:
        errors["tcp"] = tcp_msg
    if not tls_ok:
        errors["tls"] = tls_msg

    getme_ok = False
    getme_username = ""
    getme_id = ""
    webhook_ok = False
    updates_ok = False

    if not present:
        errors["token"] = "BOT_TOKEN not found in cli/env/.env"
    else:
        api = TgApi(token=token, timeout_s=args.timeout, retries=args.retries)

        # getMe
        st, payload, err = api._call("getMe")
        raw["getMe"] = {"status": st, "payload": payload}
        if err:
            errors["getMe"] = err
        else:
            if payload.get("ok") is True and isinstance(payload.get("result"), dict):
                getme_ok = True
                getme_username = str(payload["result"].get("username", ""))
                getme_id = str(payload["result"].get("id", ""))
            else:
                errors["getMe"] = f"Unexpected response: {payload}"

        # webhook info (read-only)
        st, payload, err = api._call("getWebhookInfo")
        raw["getWebhookInfo"] = {"status": st, "payload": payload}
        if err:
            errors["getWebhookInfo"] = err
        else:
            if payload.get("ok") is True:
                webhook_ok = True
            else:
                errors["getWebhookInfo"] = f"Unexpected response: {payload}"

        # updates (read-only), optional
        if args.updates:
            st, payload, err = api._call("getUpdates", params={"limit": args.limit})
            raw["getUpdates"] = {"status": st, "payload": payload}
            if err:
                errors["getUpdates"] = err
            else:
                if payload.get("ok") is True:
                    updates_ok = True
                else:
                    errors["getUpdates"] = f"Unexpected response: {payload}"

    report = TelegramSmokeReport(
        tool="tools/telegram_smoke.py",
        created_at=now_iso(),
        ok=(present and tcp_ok and tls_ok and getme_ok),
        token_present=present,
        network_tcp_ok=tcp_ok,
        network_tls_ok=tls_ok,
        getme_ok=getme_ok,
        getme_username=getme_username,
        getme_id=getme_id,
        webhook_ok=webhook_ok,
        updates_ok=updates_ok if args.updates else True,
        errors=errors,
        raw=raw,
    )

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")

    # Console summary
    print(f"Telegram smoke: {'OK' if report.ok else 'FAIL'}")
    print(f"Token present: {report.token_present} (source: {source})")
    print(f"Network TCP  : {report.network_tcp_ok}")
    print(f"Network TLS  : {report.network_tls_ok}")
    print(f"getMe        : {report.getme_ok} (username={report.getme_username}, id={report.getme_id})")
    print(f"Report saved : {out_path}")
    if report.errors:
        print("Errors:")
        for k, v in report.errors.items():
            print(f" - {k}: {v}")

    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
