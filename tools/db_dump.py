import sqlite3
from pathlib import Path

db_path = Path("data/app.db")
if not db_path.exists():
    raise SystemExit(f"DB not found: {db_path.resolve()}")

con = sqlite3.connect(str(db_path))
cur = con.cursor()

tables = cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
print("TABLES:", tables)

for (tname,) in tables:
    cols = cur.execute(f"PRAGMA table_info('{tname}')").fetchall()
    print(f"\n== {tname} ==")
    # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
    for cid, name, ctype, notnull, dflt, pk in cols:
        flags = []
        if pk:
            flags.append("PK")
        if notnull:
            flags.append("NOT NULL")
        print(f"- {name}: {ctype}" + (f" ({', '.join(flags)})" if flags else ""))

con.close()
