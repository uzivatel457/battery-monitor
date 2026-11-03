"""Kontrola a příprava přenositelné instalace BatteryMonitoru."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

from i18n import tr
from version import APP_NAME, APP_TITLE, VERSION


REQUIRED_FILES = (
    "main.py",
    "app.py",
    "battery_reader.py",
    "load_reader.py",
    "paths.py",
    "log_io.py",
    "log_analysis.py",
    "version.py",
    "i18n.py",
    "i18n_more.py",
    "updater.py",
    "CHANGELOG.md",
    "run.bat",
    "BatteryMonitor.vbs",
)

REQUIRED_MODULES = (
    "tkinter",
    "ctypes",
    "csv",
    "threading",
    "pathlib",
)


def root() -> Path:
    return Path(__file__).resolve().parent


def check_python() -> list:
    problems = []
    if sys.version_info < (3, 8):
        problems.append(tr("Python 3.8+ je nutný, teď běží {version}.", version=sys.version.split()[0]))
    return problems


def check_modules() -> list:
    problems = []
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            problems.append(tr("Modul {name} chybí: {error}", name=name, error=exc))
    return problems


def check_files() -> list:
    problems = []
    base = root()
    for name in REQUIRED_FILES:
        if not (base / name).is_file():
            problems.append(tr("Chybí soubor {name}", name=name))
    return problems


def prepare_folders() -> list:
    created = []
    for name in ("logs", "grafy"):
        path = root() / name
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(name)
        elif not path.is_dir():
            raise RuntimeError(tr("{name} existuje, ale není složka.", name=name))
    return created


def write_marker() -> Path:
    marker = root() / ".portable"
    marker.write_text(
        f"{APP_NAME} portable\n"
        f"version={VERSION}\n"
        f"python={sys.version.split()[0]}\n"
        f"root=.\n"
        f"logs=logs\n"
        f"grafy=grafy\n",
        encoding="utf-8",
    )
    return marker


def unblock_downloaded_files() -> None:
    """Odstraní Zone.Identifier (Mark of the Web) ze souborů ve složce aplikace."""
    base = str(root()).replace("'", "''")
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f"Get-ChildItem -LiteralPath '{base}' -Recurse -Force -File "
                "-ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def main() -> int:
    print(tr("{title} — příprava přenositelné instalace", title=APP_TITLE))
    print(tr("Složka aplikace: {path}", path=root()))

    try:
        unblock_downloaded_files()
        print(tr("Odblokování souborů (Zone.Identifier): hotovo."))
    except Exception as exc:
        print(tr("Odblokování souborů přeskočeno: {error}", error=exc))

    problems = []
    problems.extend(check_python())
    problems.extend(check_modules())
    problems.extend(check_files())
    if problems:
        print(tr("Instalace selhala:"))
        for item in problems:
            print(f"  - {item}")
        if any("tkinter" in item for item in problems):
            print(tr("Nainstalujte Python z python.org a zaškrtněte tcl/tk (tkinter)."))
        return 1
    created = prepare_folders()
    marker = write_marker()
    if created:
        print(tr("Vytvořeno: {names}", names=", ".join(created)))
    else:
        print(tr("Složky logs a grafy jsou připravené."))
    print(tr("Značka přenositelnosti: {name}", name=marker.name))
    print(tr("Hotovo. Spusťte run.bat nebo BatteryMonitor.vbs"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
