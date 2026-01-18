# tools/web_smoke.py
"""
Web smoke tester for tg-shop-ai (Flask web part).

Why this exists:
- Provides reproducible evidence that the web interface works end-to-end.
- Produces a machine-readable report (JSON) and optional HTML snapshots.
- Adds meaningful Python LOC (counts by tools/loc_count.py), not filler.

Typical usage:
  # 1) Start web in another terminal:
  #    python main.py web
  # 2) Run smoke tests:
  python tools/web_smoke.py

More examples:
  python tools/web_smoke.py --base http://127.0.0.1:5000
  python tools/web_smoke.py --tg-id 360433158
  python tools/web_smoke.py --snapshots data/smoke_snapshots
  python tools/web_smoke.py --out data/web_smoke_report.json
  python tools/web_smoke.py --only /catalog /admin/products
  python tools/web_smoke.py --timeout 5 --retries 2
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


# ---------------------------
# Data models
# ---------------------------

@dataclass
class CheckSpec:
    """
    Defines one HTTP check:
    - path: endpoint path, may include query string
    - method: GET by default
    - expect_status: expected HTTP status code (usually 200)
    - must_contain: list of substrings (any language) expected to be present in response body
    - must_match: list of regex patterns expected to match response body
    - allow_empty_body: if True, doesn't fail when body is empty
    """
    name: str
    path: str
    method: str = "GET"
    expect_status: int = 200
    must_contain: Optional[List[str]] = None
    must_match: Optional[List[str]] = None
    allow_empty_body: bool = False


@dataclass
class CheckResult:
    name: str
    url: str
    method: str
    ok: bool
    status: Optional[int]
    elapsed_ms: int
    error: str = ""
    notes: Optional[List[str]] = None
    snapshot: str = ""  # saved file name (optional)


@dataclass
class SmokeReport:
    tool: str
    created_at: str
    base_url: str
    passed: int
    failed: int
    total: int
    results: List[CheckResult]


# ---------------------------
# Helpers
# ---------------------------

def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def safe_filename(s: str) -> str:
    """
    Convert string to safe filename chunk.
    """
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_\-\.]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_") or "snapshot"


def read_text(resp_bytes: bytes, encoding_hint: str = "utf-8") -> str:
    """
    Decode response bytes safely.
    """
    try:
        return resp_bytes.decode(encoding_hint)
    except Exception:
        # fallback
        return resp_bytes.decode("utf-8", errors="replace")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def print_line(msg: str = "") -> None:
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def human_ms(ms: int) -> str:
    if ms < 1000:
        return f"{ms} ms"
    return f"{ms/1000:.2f} s"


# ---------------------------
# HTTP client (urllib only)
# ---------------------------

class HttpClient:
    def __init__(self, timeout_s: float = 6.0, retries: int = 1, retry_sleep_s: float = 0.6):
        self.timeout_s = timeout_s
        self.retries = retries
        self.retry_sleep_s = retry_sleep_s

    def fetch(self, url: str, method: str = "GET") -> Tuple[int, bytes, Dict[str, str]]:
        """
        Returns: (status_code, body_bytes, headers_dict)
        Raises: URLError / HTTPError
        """
        req = Request(url=url, method=method)
        # minimal headers to avoid some servers refusing
        req.add_header("User-Agent", "tg-shop-ai-web-smoke/1.0")
        req.add_header("Accept", "text/html,application/json;q=0.9,*/*;q=0.8")

        with urlopen(req, timeout=self.timeout_s) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read()  # bytes
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return int(status), body, headers

    def fetch_with_retries(self, url: str, method: str = "GET") -> Tuple[int, bytes, Dict[str, str], str]:
        """
        Like fetch(), but returns an error string instead of raising after retries.
        """
        last_err = ""
        attempts = max(1, self.retries + 1)
        for i in range(attempts):
            try:
                status, body, headers = self.fetch(url=url, method=method)
                return status, body, headers, ""
            except HTTPError as e:
                # HTTPError is also a response; read its body to include in diagnostics
                try:
                    body = e.read()  # type: ignore[attr-defined]
                except Exception:
                    body = b""
                last_err = f"HTTPError: {e.code} {e.reason}"
                return int(e.code), body, {}, last_err
            except URLError as e:
                last_err = f"URLError: {e.reason}"
            except Exception as e:
                last_err = f"Exception: {e}"

            if i < attempts - 1:
                time.sleep(self.retry_sleep_s)

        # unreachable usually, but keep contract
        return 0, b"", {}, last_err


# ---------------------------
# Check logic
# ---------------------------

def build_default_checks(tg_id: Optional[str]) -> List[CheckSpec]:
    """
    Default endpoints for tg-shop-ai web.
    We check:
    - /            (index)
    - /catalog     (catalog)
    - /admin/products (admin products page)
    - /orders      (help text when no tg_id)
    - /orders?tg_id=<num> (positive)
    - /orders?tg_id=abc   (negative)
    """
    checks: List[CheckSpec] = []

    checks.append(CheckSpec(
        name="index",
        path="/",
        expect_status=200,
        must_contain=["tg-shop", "catalog", "каталог"],
        allow_empty_body=False
    ))

    checks.append(CheckSpec(
        name="catalog",
        path="/catalog",
        expect_status=200,
        must_contain=["Каталог", "SKU", "Цена"],
        allow_empty_body=False
    ))

    checks.append(CheckSpec(
        name="admin_products",
        path="/admin/products",
        expect_status=200,
        must_contain=["Добавить", "Список товаров", "SKU"],
        allow_empty_body=False
    ))

    checks.append(CheckSpec(
        name="orders_help",
        path="/orders",
        expect_status=200,
        must_contain=["tg_id", "например", "/orders?tg_id="],
        allow_empty_body=False
    ))

    # Positive orders listing (if tg_id known)
    if tg_id:
        checks.append(CheckSpec(
            name="orders_by_tg_id",
            path=f"/orders?tg_id={tg_id}",
            expect_status=200,
            must_contain=["Мои заказы", "ID", "Статус"],
            allow_empty_body=False
        ))

    # Negative: non-numeric tg_id
    checks.append(CheckSpec(
        name="orders_invalid_tg_id",
        path="/orders?tg_id=abc",
        expect_status=200,
        must_contain=["tg_id", "числом", "например"],
        allow_empty_body=False
    ))

    return checks


def validate_body(spec: CheckSpec, text: str) -> Tuple[bool, List[str]]:
    """
    Returns ok + notes.
    """
    notes: List[str] = []
    if not text and not spec.allow_empty_body:
        return False, ["Empty response body"]

    ok = True

    if spec.must_contain:
        for s in spec.must_contain:
            if s and (s not in text):
                ok = False
                notes.append(f"Missing substring: {s}")

    if spec.must_match:
        for pat in spec.must_match:
            if pat and (re.search(pat, text) is None):
                ok = False
                notes.append(f"Regex not matched: {pat}")

    return ok, notes


def save_snapshot(snap_dir: Path, spec: CheckSpec, url: str, status: int, body: str) -> str:
    """
    Save HTML snapshot to file, return filename.
    """
    ensure_dir(snap_dir)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = safe_filename(f"{spec.name}_{status}_{ts}")
    filename = f"{name}.html"
    path = snap_dir / filename

    header = f"<!-- web_smoke snapshot\nurl: {url}\nstatus: {status}\ncreated_at: {now_iso()}\n-->\n"
    path.write_text(header + body, encoding="utf-8", errors="ignore")
    return str(path)


def run_checks(
    base_url: str,
    checks: List[CheckSpec],
    client: HttpClient,
    snapshots_dir: Optional[Path],
    only_paths: Optional[List[str]],
) -> SmokeReport:
    results: List[CheckResult] = []

    # Normalize base URL
    if not base_url.endswith("/"):
        base_url = base_url + "/"

    for spec in checks:
        # Filter by --only
        if only_paths:
            if spec.path not in only_paths and spec.name not in only_paths:
                continue

        full_url = urljoin(base_url, spec.path.lstrip("/"))
        start = time.time()
        status, body_bytes, headers, fetch_err = client.fetch_with_retries(full_url, method=spec.method)
        elapsed_ms = int((time.time() - start) * 1000)

        body_text = ""
        if body_bytes:
            # detect encoding from headers if possible
            enc = "utf-8"
            ct = headers.get("content-type", "")
            m = re.search(r"charset=([a-zA-Z0-9_\-]+)", ct)
            if m:
                enc = m.group(1).strip()
            body_text = read_text(body_bytes, enc)

        ok = True
        notes: List[str] = []

        if status != spec.expect_status:
            ok = False
            notes.append(f"Expected status {spec.expect_status}, got {status}")

        # Validate body
        body_ok, body_notes = validate_body(spec, body_text)
        if not body_ok:
            ok = False
            notes.extend(body_notes)

        snapshot_path = ""
        if snapshots_dir is not None:
            # Save snapshot for every check (useful for evidence)
            try:
                snapshot_path = save_snapshot(snapshots_dir, spec, full_url, status, body_text)
            except Exception as e:
                ok = False
                notes.append(f"Snapshot save failed: {e}")

        err_text = fetch_err
        # If status is 0, it usually means connection failed after retries
        if status == 0 and not err_text:
            err_text = "Connection failed"

        results.append(CheckResult(
            name=spec.name,
            url=full_url,
            method=spec.method,
            ok=ok,
            status=status if status else None,
            elapsed_ms=elapsed_ms,
            error=err_text,
            notes=notes if notes else None,
            snapshot=snapshot_path
        ))

    passed = sum(1 for r in results if r.ok)
    failed = sum(1 for r in results if not r.ok)

    return SmokeReport(
        tool="tools/web_smoke.py",
        created_at=now_iso(),
        base_url=base_url.rstrip("/"),
        passed=passed,
        failed=failed,
        total=len(results),
        results=results
    )


def save_report(report: SmokeReport, out_path: Path) -> None:
    ensure_dir(out_path.parent)
    payload = asdict(report)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def print_summary(report: SmokeReport) -> None:
    print_line("")
    print_line("WEB SMOKE SUMMARY")
    print_line(f"Base URL: {report.base_url}")
    print_line(f"Created : {report.created_at}")
    print_line(f"Passed  : {report.passed}/{report.total}")
    print_line(f"Failed  : {report.failed}/{report.total}")
    print_line("")

    for r in report.results:
        status = r.status if r.status is not None else "-"
        flag = "OK " if r.ok else "FAIL"
        print_line(f"[{flag}] {r.name:20} {status:4} {human_ms(r.elapsed_ms):>8}  {r.url}")
        if r.error:
            print_line(f"       error: {r.error}")
        if r.notes:
            for n in r.notes:
                print_line(f"       note : {n}")
        if r.snapshot:
            print_line(f"       snap : {r.snapshot}")
    print_line("")


# ---------------------------
# CLI
# ---------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="web_smoke.py",
        description="Web smoke tester for tg-shop-ai Flask app.",
    )
    p.add_argument(
        "--base",
        default=os.environ.get("WEB_BASE_URL", "http://127.0.0.1:5000"),
        help="Base URL of running web app (default: http://127.0.0.1:5000).",
    )
    p.add_argument(
        "--tg-id",
        default=os.environ.get("TG_ID", ""),
        help="Telegram tg_id (numeric) to test /orders?tg_id=... (optional).",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("WEB_SMOKE_TIMEOUT", "6")),
        help="HTTP timeout in seconds (default: 6).",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=int(os.environ.get("WEB_SMOKE_RETRIES", "1")),
        help="Retries for network errors (default: 1).",
    )
    p.add_argument(
        "--snapshots",
        default="data/smoke_snapshots",
        help="Directory to store HTML snapshots (default: data/smoke_snapshots). Use '-' to disable.",
    )
    p.add_argument(
        "--out",
        default="data/web_smoke_report.json",
        help="Report JSON output path (default: data/web_smoke_report.json). Then can be attached as appendix evidence.",
    )
    p.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Run only specified checks by name or exact path (e.g. --only catalog /admin/products).",
    )
    return p


def main(argv: Sequence[str]) -> int:
    args = build_parser().parse_args(argv)

    tg_id = args.tg_id.strip() or None
    base = args.base.strip()

    snapshots: Optional[Path]
    if args.snapshots.strip() == "-":
        snapshots = None
    else:
        snapshots = Path(args.snapshots).resolve()

    out_path = Path(args.out).resolve()

    client = HttpClient(timeout_s=args.timeout, retries=args.retries)
    checks = build_default_checks(tg_id=tg_id)

    report = run_checks(
        base_url=base,
        checks=checks,
        client=client,
        snapshots_dir=snapshots,
        only_paths=args.only,
    )

    save_report(report, out_path)
    print_summary(report)
    print_line(f"Report saved: {out_path}")

    return 0 if report.failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
