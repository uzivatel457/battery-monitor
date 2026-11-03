"""Kontrola a instalace novější verze z GitHub Releases."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from paths import app_root
from version import APP_NAME, GITHUB_OWNER, GITHUB_REPO, VERSION


STATE_NAME = "update_state.json"
USER_AGENT = f"{APP_NAME}/{VERSION}"


def updates_enabled() -> bool:
    if os.environ.get("BATTERY_MONITOR_NO_UPDATE") == "1":
        return False
    return bool(GITHUB_OWNER and GITHUB_REPO)


def parse_version(text: str) -> tuple:
    cleaned = (text or "").strip().lstrip("vV")
    parts = []
    for piece in cleaned.split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    if not parts:
        return (0, 0, 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def state_path() -> Path:
    return app_root() / STATE_NAME


def load_state() -> dict:
    path = state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(data: dict) -> None:
    state_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def skipped_version() -> str:
    value = load_state().get("skip")
    return value.strip() if isinstance(value, str) else ""


def skip_version(version: str) -> None:
    data = load_state()
    data["skip"] = version
    save_state(data)


def _request(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def check_latest() -> dict | None:
    """Vrátí novější vydání, které uživatel ještě nepřeskočil."""
    if not updates_enabled():
        return None
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    try:
        payload = json.loads(_request(url).decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    version = str(payload.get("tag_name") or "").strip().lstrip("vV")
    if not version or not is_newer(version, VERSION):
        return None
    if skipped_version() == version:
        return None
    asset_url = ""
    asset_name = ""
    assets = payload.get("assets") or []
    if isinstance(assets, list):
        chosen = None
        for item in assets:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            if name.lower().endswith(".zip"):
                chosen = item
                if name.startswith(APP_NAME):
                    break
        if chosen is not None:
            asset_url = str(chosen.get("browser_download_url") or "")
            asset_name = str(chosen.get("name") or "update.zip")
    if not asset_url:
        asset_url = str(payload.get("zipball_url") or "")
        asset_name = f"{APP_NAME}-{version}.zip"
    if not asset_url:
        return None
    notes = str(payload.get("body") or "").strip()
    if len(notes) > 1500:
        notes = notes[:1500].rstrip() + "…"
    return {
        "version": version,
        "notes": notes,
        "url": asset_url,
        "asset_name": asset_name,
        "html_url": str(payload.get("html_url") or ""),
    }


def schedule_update_check(root, on_update) -> None:
    if not updates_enabled():
        return

    def work() -> None:
        info = check_latest()
        if not info:
            return
        try:
            root.after(0, lambda: on_update(info))
        except Exception:
            return

    threading.Thread(target=work, name="update-check", daemon=True).start()


def download_and_stage(info: dict) -> Path:
    """Stáhne vydání a vrátí složku s novými soubory aplikace."""
    raw = _request(info["url"])
    temp_root = Path(tempfile.mkdtemp(prefix="bmon-update-"))
    archive = temp_root / (info.get("asset_name") or "update.zip")
    archive.write_bytes(raw)
    unpack = temp_root / "unpack"
    unpack.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(unpack)
    source = _find_app_dir(unpack)
    if source is None:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError("archive")
    return source


def _find_app_dir(unpack: Path) -> Path | None:
    if (unpack / "main.py").is_file():
        return unpack
    for path in unpack.rglob("main.py"):
        if path.is_file() and path.parent != unpack:
            return path.parent
        if path.is_file():
            return path.parent
    return None


def launch_apply(source: Path) -> Path:
    """Zapíše skript, který po ukončení aplikace překopíruje nové soubory a znovu ji spustí."""
    destination = app_root()
    script = destination / "_update_apply.bat"
    src = str(source)
    dst = str(destination)
    temp_root = source
    while temp_root.name and not temp_root.name.startswith("bmon-update-"):
        if temp_root.parent == temp_root:
            temp_root = None
            break
        temp_root = temp_root.parent
    cleanup = ""
    if temp_root is not None:
        cleanup = f'rmdir /s /q "{temp_root}"'
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "ping 127.0.0.1 -n 3 >nul",
        f'robocopy "{src}" "{dst}" /E /NFL /NDL /NJH /NJS /nc /ns /np /XD logs grafy __pycache__ .git /XF update_state.json .portable _update_apply.bat',
        "set RC=%ERRORLEVEL%",
        "if %RC% GEQ 8 exit /b %RC%",
        cleanup,
        f'start "" /D "{dst}" "{dst}\\run.bat"',
        'del "%~f0"',
        "",
    ]
    script.write_text("\r\n".join(lines), encoding="utf-8")
    return script
