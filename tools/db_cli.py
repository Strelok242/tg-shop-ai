# tools/db_cli.py
"""
SQLite DB helper CLI for tg-shop-ai.

Goals:
- Be independent from internal app code (works via sqlite3 directly)
- Provide useful maintenance / reporting capabilities for the diploma demo:
  schema/tables/count/tail/export/backup/integrity/vacuum
- Increase real, meaningful Python LOC (counts in tools/loc_count.py)

Usage examples:
  python tools/db_cli.py tables
  python tools/db_cli.py schema
  python tools/db_cli.py schema --table products
  python tools/db_cli.py count
  python tools/db_cli.py tail --table orders --limit 10
  python tools/db_cli.py export --table products --format csv --out data/products.csv
  python tools/db_cli.py export --table ai_logs --format json --out data/ai_logs.json
  python tools/db_cli.py backup --out data/backup_2026-01-18.db
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# ----------------------------
# DB path discovery
# ----------------------------

ENV_KEYS = ("DB_PATH", "DATABASE_PATH", "SQLITE_PATH", "DATABASE_URL", "DB_URL")


def _read_dotenv(dotenv_path: Path) -> Dict[str, str]:
    """
    Minimal .env reader: KEY=VALUE lines, ignores comments.
    Does not support multiline values (not needed here).
    """
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


def _parse_sqlite_url(url: str) -> Optional[Path]:
    """
    Supports:
      sqlite:///relative/path.db
      sqlite:////abs/path.db
    """
    if not url:
        return None
    m = re.match(r"^sqlite:(?P<slashes>/{2,4})(?P<path>.+)$", url)
    if not m:
        return None
    path_part = m.group("path")
    # If it starts with / after sqlite://// it's absolute on *nix.
    # On Windows, user may store something like sqlite:///data/app.db (relative) - we handle both.
    p = Path(path_part)
    return p


def _candidate_db_files(root: Path) -> List[Path]:
    """
    Generate candidate db file paths in order of preference.
    """
    candidates: List[Path] = []

    # Common places in this project
    candidates += [
        root / "data" / "app.db",
        root / "data" / "tg_shop.db",
        root / "data" / "tg-shop-ai.db",
        root / "data" / "shop.db",
        root / "data" / "database.db",
        root / "app.db",
        root / "tg_shop.db",
        root / "shop.db",
    ]

    # Any *.db under data/ first
    data_dir = root / "data"
    if data_dir.exists():
        candidates += sorted(data_dir.glob("*.db"))

    # Any *.db in root
    candidates += sorted(root.glob("*.db"))

    # Deduplicate while keeping order
    seen = set()
    uniq: List[Path] = []
    for p in candidates:
        rp = p.resolve() if p.exists() else p
        key = str(rp)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def discover_db_path(project_root: Path) -> Path:
    """
    Discover DB path using:
    1) OS env vars
    2) .env file
    3) scanning common locations
    """
    # 1) OS env
    for k in ENV_KEYS:
        val = os.environ.get(k)
        if not val:
            continue
        if k in ("DATABASE_URL", "DB_URL"):
            p = _parse_sqlite_url(val)
            if p:
                # relative to root if relative path
                if not p.is_absolute():
                    p = (project_root / p).resolve()
                if p.exists():
                    return p
        else:
            p = Path(val)
            if not p.is_absolute():
                p = (project_root / p).resolve()
            if p.exists():
                return p

    # 2) .env file
    env_map = _read_dotenv(project_root / ".env")
    for k in ENV_KEYS:
        val = env_map.get(k)
        if not val:
            continue
        if k in ("DATABASE_URL", "DB_URL"):
            p = _parse_sqlite_url(val)
            if p:
                if not p.is_absolute():
                    p = (project_root / p).resolve()
                if p.exists():
                    return p
        else:
            p = Path(val)
            if not p.is_absolute():
                p = (project_root / p).resolve()
            if p.exists():
                return p

    # 3) scan
    for p in _candidate_db_files(project_root):
        if p.exists() and p.is_file():
            return p.resolve()

    raise FileNotFoundError(
        "SQLite DB file not found. Set DB_PATH or DATABASE_URL in environment/.env, "
        "or place *.db under ./data/."
    )


# ----------------------------
# SQLite helpers
# ----------------------------

def connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def q(con: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
    cur = con.execute(sql, params)
    rows = cur.fetchall()
    return rows


def scalar(con: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> Any:
    cur = con.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def list_tables(con: sqlite3.Connection) -> List[str]:
    rows = q(con, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    return [r["name"] for r in rows]


def table_schema(con: sqlite3.Connection, table: str) -> str:
    rows = q(con, "SELECT sql FROM sqlite_master WHERE type='table' AND name=?;", (table,))
    if not rows or not rows[0]["sql"]:
        raise ValueError(f"Table '{table}' not found.")
    return str(rows[0]["sql"])


def pretty_table(rows: List[sqlite3.Row], max_width: int = 38) -> str:
    """
    Render rows as a simple table without external dependencies.
    """
    if not rows:
        return "(no rows)"

    cols = rows[0].keys()
    data = [[str(r[c]) if r[c] is not None else "" for c in cols] for r in rows]

    # truncate long cells
    def trunc(s: str) -> str:
        if len(s) <= max_width:
            return s
        return s[: max_width - 3] + "..."

    data = [[trunc(cell) for cell in row] for row in data]

    widths = [len(str(c)) for c in cols]
    for row in data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    sep = " | "
    header = sep.join(str(c).ljust(widths[i]) for i, c in enumerate(cols))
    line = "-+-".join("-" * widths[i] for i in range(len(widths)))
    body = "\n".join(sep.join(row[i].ljust(widths[i]) for i in range(len(widths))) for row in data)
    return f"{header}\n{line}\n{body}"


def export_csv(rows: List[sqlite3.Row], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        # still write header? unknown -> write empty file
        out_path.write_text("", encoding="utf-8")
        return
    cols = list(rows[0].keys())
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=",")
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])


def export_json(rows: List[sqlite3.Row], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [dict(r) for r in rows]
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_table_exists(con: sqlite3.Connection, table: str) -> None:
    tables = set(list_tables(con))
    if table not in tables:
        raise ValueError(f"Unknown table '{table}'. Available: {', '.join(sorted(tables))}")


def infer_order_by(con: sqlite3.Connection, table: str) -> str:
    """
    Try to infer a reasonable ORDER BY for tail() and export().
    Prefers created_at, id, or rowid.
    """
    info = q(con, f"PRAGMA table_info({table});")
    cols = [r["name"] for r in info]
    for c in ("created_at", "createdAt", "created", "id"):
        if c in cols:
            return c
    return "rowid"


# ----------------------------
# Commands
# ----------------------------

def cmd_tables(con: sqlite3.Connection, _args: argparse.Namespace) -> int:
    tables = list_tables(con)
    if not tables:
        print("(no user tables found)")
        return 0
    print("Tables:")
    for t in tables:
        print(f" - {t}")
    return 0


def cmd_schema(con: sqlite3.Connection, args: argparse.Namespace) -> int:
    tables = list_tables(con)
    if args.table:
        ensure_table_exists(con, args.table)
        print(table_schema(con, args.table))
        return 0

    print("Schema (tables):")
    for t in tables:
        print("\n" + "=" * 80)
        print(f"{t}")
        print("-" * 80)
        print(table_schema(con, t))
    return 0


def cmd_count(con: sqlite3.Connection, _args: argparse.Namespace) -> int:
    tables = list_tables(con)
    if not tables:
        print("(no user tables found)")
        return 0

    rows: List[sqlite3.Row] = []
    for t in tables:
        n = scalar(con, f"SELECT COUNT(*) FROM {t};")
        rows.append(sqlite3.Row(con.cursor(), [("table", t), ("rows", n)]))  # type: ignore

    # Workaround: sqlite3.Row is not directly constructible nicely; print manually instead.
    print("Row counts:")
    for t in tables:
        n = scalar(con, f"SELECT COUNT(*) FROM {t};")
        print(f" - {t}: {n}")
    return 0


def cmd_tail(con: sqlite3.Connection, args: argparse.Namespace) -> int:
    ensure_table_exists(con, args.table)
    limit = int(args.limit)
    order_col = infer_order_by(con, args.table)
    sql = f"SELECT * FROM {args.table} ORDER BY {order_col} DESC LIMIT ?;"
    rows = q(con, sql, (limit,))
    print(pretty_table(rows))
    return 0


def cmd_export(con: sqlite3.Connection, args: argparse.Namespace) -> int:
    ensure_table_exists(con, args.table)
    fmt = args.format.lower().strip()
    out = Path(args.out)
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()

    order_col = infer_order_by(con, args.table)
    sql = f"SELECT * FROM {args.table} ORDER BY {order_col} DESC;"
    rows = q(con, sql)

    if fmt == "csv":
        export_csv(rows, out)
    elif fmt == "json":
        export_json(rows, out)
    else:
        raise ValueError("Unsupported format. Use: csv or json")

    print(f"Exported {len(rows)} rows from '{args.table}' to: {out}")
    return 0


def cmd_backup(_con: sqlite3.Connection, args: argparse.Namespace, db_path: Path) -> int:
    out = Path(args.out)
    if out.is_dir():
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = out / f"backup_{ts}.db"
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()

    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, out)
    print(f"Backup created: {out}")
    return 0


def cmd_integrity(con: sqlite3.Connection, _args: argparse.Namespace) -> int:
    # PRAGMA integrity_check returns 'ok' if fine
    rows = q(con, "PRAGMA integrity_check;")
    # It may return multiple rows if issues
    messages = [str(r[0]) for r in rows]
    print("Integrity check:")
    for m in messages:
        print(f" - {m}")
    # Non-ok => exit code 2
    return 0 if messages == ["ok"] else 2


def cmd_vacuum(con: sqlite3.Connection, _args: argparse.Namespace) -> int:
    con.execute("VACUUM;")
    con.commit()
    print("VACUUM completed.")
    return 0


# ----------------------------
# CLI
# ----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="db_cli.py",
        description="SQLite DB helper CLI for tg-shop-ai (independent from app code).",
    )
    p.add_argument(
        "--db",
        dest="db",
        default="",
        help="Path to SQLite db file. If omitted, auto-discovery is used (env/.env/data/*.db).",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("tables", help="List user tables.")
    sp.set_defaults(_handler="tables")

    sp = sub.add_parser("schema", help="Print schema for all tables or one table.")
    sp.add_argument("--table", default="", help="Table name.")
    sp.set_defaults(_handler="schema")

    sp = sub.add_parser("count", help="Print row counts for all tables.")
    sp.set_defaults(_handler="count")

    sp = sub.add_parser("tail", help="Show last N rows from a table.")
    sp.add_argument("--table", required=True, help="Table name.")
    sp.add_argument("--limit", default=10, help="Number of rows (default: 10).")
    sp.set_defaults(_handler="tail")

    sp = sub.add_parser("export", help="Export a table to CSV/JSON.")
    sp.add_argument("--table", required=True, help="Table name.")
    sp.add_argument("--format", required=True, choices=("csv", "json"), help="Export format.")
    sp.add_argument("--out", required=True, help="Output file path.")
    sp.set_defaults(_handler="export")

    sp = sub.add_parser("backup", help="Copy DB file to a backup.")
    sp.add_argument("--out", required=True, help="Output path (file or directory).")
    sp.set_defaults(_handler="backup")

    sp = sub.add_parser("integrity", help="Run PRAGMA integrity_check.")
    sp.set_defaults(_handler="integrity")

    sp = sub.add_parser("vacuum", help="Run VACUUM to compact DB.")
    sp.set_defaults(_handler="vacuum")

    return p


def main(argv: Sequence[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[1]
    if args.db:
        db_path = Path(args.db)
        if not db_path.is_absolute():
            db_path = (project_root / db_path).resolve()
        if not db_path.exists():
            print(f"ERROR: DB file not found: {db_path}", file=sys.stderr)
            return 2
    else:
        try:
            db_path = discover_db_path(project_root)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2

    try:
        con = connect(db_path)
    except Exception as e:
        print(f"ERROR: can't open db '{db_path}': {e}", file=sys.stderr)
        return 2

    try:
        handler = getattr(args, "_handler", "")
        if handler == "tables":
            return cmd_tables(con, args)
        if handler == "schema":
            return cmd_schema(con, args)
        if handler == "count":
            return cmd_count(con, args)
        if handler == "tail":
            return cmd_tail(con, args)
        if handler == "export":
            return cmd_export(con, args)
        if handler == "backup":
            return cmd_backup(con, args, db_path)
        if handler == "integrity":
            return cmd_integrity(con, args)
        if handler == "vacuum":
            return cmd_vacuum(con, args)

        print("ERROR: unknown command handler", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    finally:
        try:
            con.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
