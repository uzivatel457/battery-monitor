"""Relativní cesty od složky aplikace — fungují po přesunu kamkoli."""

from __future__ import annotations

from pathlib import Path


def app_root() -> Path:
    return Path(__file__).resolve().parent


def rel(*parts: str) -> Path:
    """Cesta relativní ke kořeni aplikace (např. logs, grafy)."""
    return app_root().joinpath(*parts)


def ensure_dir(*parts: str) -> Path:
    path = rel(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    return ensure_dir("logs")


def graphs_dir() -> Path:
    return ensure_dir("grafy")


def as_app_relative(path: Path) -> str:
    """Zobrazitelná relativní cesta, pokud leží uvnitř aplikace."""
    try:
        return path.resolve().relative_to(app_root()).as_posix()
    except ValueError:
        return path.name
