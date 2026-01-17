from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__", "venv", ".venv",
    "node_modules", "dist", "build", ".pytest_cache", ".mypy_cache",
}
EXCLUDE_FILES = {"app.db"}  # если БД лежит в data/

EXTS = {".py", ".html", ".htm", ".css", ".js"}

def count_logical_lines(path: Path) -> int:
    ext = path.suffix.lower()
    txt = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    total = 0
    in_block = False  # для /* */ и <!-- -->

    for line in txt:
        s = line.strip()
        if not s:
            continue

        # HTML comments <!-- ... -->
        if ext in {".html", ".htm"}:
            if in_block:
                if "-->" in s:
                    in_block = False
                continue
            if s.startswith("<!--"):
                if "-->" not in s:
                    in_block = True
                continue
            total += 1
            continue

        # JS/CSS block comments /* ... */
        if ext in {".js", ".css"}:
            if in_block:
                if "*/" in s:
                    in_block = False
                continue
            if s.startswith("/*"):
                if "*/" not in s:
                    in_block = True
                continue
            if s.startswith("//"):
                continue
            # inline // comment
            code = s.split("//", 1)[0].strip()
            if code:
                total += 1
            continue

        # Python comments #
        if ext == ".py":
            if s.startswith("#"):
                continue
            code = s.split("#", 1)[0].strip()
            if code:
                total += 1
            continue

        # прочее (на всякий)
        total += 1

    return total

def main() -> None:
    by_ext: dict[str, int] = {}
    total = 0

    for p in ROOT.rglob("*"):
        if p.is_dir():
            continue
        if p.name in EXCLUDE_FILES:
            continue
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in EXTS:
            continue

        n = count_logical_lines(p)
        by_ext[p.suffix.lower()] = by_ext.get(p.suffix.lower(), 0) + n
        total += n

    print("ROOT:", ROOT)
    print("Logical LOC (approx, no blanks/comments):", total)
    for k in sorted(by_ext):
        print(f"  {k}: {by_ext[k]}")

if __name__ == "__main__":
    main()
