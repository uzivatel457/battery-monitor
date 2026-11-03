"""Vytvoří ZIP nové verze do složky _install (tento skript do ZIP nepatří)."""

from __future__ import annotations

import zipfile
from pathlib import Path

from version import APP_NAME, VERSION, ZIP_NAME


ROOT = Path(__file__).resolve().parent
INSTALL_DIR = ROOT / "_install"
PACK_SCRIPT = Path(__file__).name

# Soubory a složky, které do archivu nepatří
EXCLUDE_NAMES = {
    PACK_SCRIPT,
    "_install",
    ".git",
    ".gitignore",
    ".cursor",
    "__pycache__",
    ".portable",
    "update_state.json",
    "_update_apply.bat",
    "_wrap_i18n.py",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".zip"}
EXCLUDE_DIR_NAMES = {"__pycache__", ".git", "_install", "logs", "grafy", ".cursor"}


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if parts and parts[0] in EXCLUDE_DIR_NAMES:
        return True
    if path.name in EXCLUDE_NAMES:
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if path.is_file() and path.name.startswith("."):
        return True
    return False


def collect_files() -> list:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path):
            continue
        files.append(path)
    return sorted(files)


def build_zip() -> Path:
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    out = INSTALL_DIR / ZIP_NAME
    folder_in_zip = f"{APP_NAME}{VERSION}"
    files = collect_files()
    if not files:
        raise RuntimeError("Není co zabalit.")

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            arcname = f"{folder_in_zip}/{path.relative_to(ROOT).as_posix()}"
            zf.write(path, arcname)
        # Prázdné runtime složky
        for empty in ("logs", "grafy"):
            zf.writestr(f"{folder_in_zip}/{empty}/.gitkeep", "")

    return out


def main() -> int:
    print(f"{APP_NAME} {VERSION} — tvorba ZIP archivu")
    print(f"Zdroj: {ROOT}")
    out = build_zip()
    size_kb = out.stat().st_size / 1024.0
    print(f"Vytvořeno: {out.relative_to(ROOT)} ({size_kb:.1f} KB)")
    print(f"Skript {PACK_SCRIPT} do archivu nepatří.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
