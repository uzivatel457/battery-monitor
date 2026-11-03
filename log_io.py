"""Načítání a zápis CSV logů BatteryMonitoru."""


from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from i18n import tr


TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H-%M-%S",
    "%d.%m.%Y %H:%M:%S",
)


@dataclass
class LoadedLog:
    path: Path
    samples: list
    manufacturer: Optional[str] = None
    device_name: Optional[str] = None
    chemistry: Optional[str] = None
    serial: Optional[str] = None
    designed_mwh: Optional[int] = None
    full_charged_mwh: Optional[int] = None
    health_percent: Optional[float] = None


def _empty(value) -> bool:
    return value is None or str(value).strip() == ""


def _parse_float(value) -> Optional[float]:
    if _empty(value):
        return None
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value) -> Optional[int]:
    number = _parse_float(value)
    if number is None:
        return None
    return int(round(number))


def _parse_time(value) -> Optional[float]:
    if _empty(value):
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1]
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def load_log_csv(path: Path, sample_cls) -> LoadedLog:
    """Načte CSV a vrátí LoadedLog se Sample objekty (sample_cls)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(tr("Soubor neexistuje: {path}", path=path))

    samples = []
    manufacturer = None
    device_name = None
    chemistry = None
    serial = None
    designed_mwh = None
    full_charged_mwh = None
    health_percent = None

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if not reader.fieldnames:
            raise ValueError(tr("Soubor nemá hlavičku CSV."))
        fields = {name.strip().lower(): name for name in reader.fieldnames if name}

        def cell(row, *names):
            for name in names:
                key = fields.get(name.lower())
                if key is not None and key in row:
                    return row.get(key)
            return None

        for row in reader:
            stamp = _parse_time(cell(row, "cas", "čas", "time", "timestamp"))
            if stamp is None:
                continue
            state = (cell(row, "stav", "state") or "").strip().lower()
            charging = state in ("nabijeni", "nabíjení", "charging", "charge")
            discharging = state in ("vybijeni", "vybíjení", "discharging", "discharge")
            gpus = []
            for index in range(1, 4):
                name = cell(row, f"gpu{index}_nazev", f"gpu{index}_name")
                value = _parse_float(cell(row, f"gpu{index}_pct", f"gpu{index}"))
                if not _empty(name) and value is not None:
                    gpus.append((str(name).strip(), value))
            sample = sample_cls(
                t=stamp,
                percent=_parse_float(cell(row, "procenta", "percent", "nabiti")),
                current_ma=_parse_float(cell(row, "proud_mA", "proud_ma", "current_ma")),
                voltage_mv=_parse_int(cell(row, "napeti_mV", "napeti_mv", "voltage_mv")),
                rate_mw=_parse_int(cell(row, "vykon_mW", "vykon_mw", "rate_mw")),
                remaining_mwh=_parse_int(cell(row, "zbyvajici_mWh", "zbyvajici_mwh", "remaining_mwh")),
                charging=charging,
                discharging=discharging,
                cpu=_parse_float(cell(row, "cpu_pct", "cpu")),
                gpus=tuple(gpus),
            )
            samples.append(sample)

            if manufacturer is None and not _empty(cell(row, "vyrobce", "manufacturer")):
                manufacturer = str(cell(row, "vyrobce", "manufacturer")).strip()
            if device_name is None and not _empty(cell(row, "nazev", "name", "device")):
                device_name = str(cell(row, "nazev", "name", "device")).strip()
            if chemistry is None and not _empty(cell(row, "chemie", "chemistry")):
                chemistry = str(cell(row, "chemie", "chemistry")).strip()
            if serial is None and not _empty(cell(row, "serial")):
                serial = str(cell(row, "serial")).strip()
            if designed_mwh is None:
                designed_mwh = _parse_int(cell(row, "navrhova_mWh", "navrhova_mwh"))
            if full_charged_mwh is None:
                full_charged_mwh = _parse_int(cell(row, "plna_mWh", "plna_mwh"))
            if health_percent is None:
                health_percent = _parse_float(cell(row, "kondice_pct", "health"))

    if not samples:
        raise ValueError(tr("V souboru nejsou žádné použitelné vzorky."))

    return LoadedLog(
        path=path,
        samples=samples,
        manufacturer=manufacturer,
        device_name=device_name,
        chemistry=chemistry,
        serial=serial,
        designed_mwh=designed_mwh,
        full_charged_mwh=full_charged_mwh,
        health_percent=health_percent,
    )


def list_log_files(directory: Path) -> list:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    files = [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".csv"]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return files
