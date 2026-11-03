"""BatteryMonitor — okno se živým grafem, proudem a úplnými údaji o baterii."""

from __future__ import annotations

import csv
import ctypes
import os
import struct
import threading
import time
import tkinter as tk
import zlib
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from battery_reader import Battery, Snapshot, SystemPower, read_snapshot
from i18n import comma_decimal, language, tr
from load_reader import LoadSampler
from log_analysis import analyze_measurement
from log_io import load_log_csv
from paths import as_app_relative, graphs_dir, logs_dir
from updater import download_and_stage, launch_apply, schedule_update_check, skip_version
from version import APP_NAME, APP_TITLE, VERSION

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

APP_DIR = Path(__file__).resolve().parent
LOG_DIR = logs_dir()
GRAPH_DIR = graphs_dir()

BG = "#10141b"
PANEL = "#171d27"
CARD = "#1e2633"
LINE = "#313c50"
TEXT = "#e8eef6"
MUTED = "#93a0b5"
TEAL = "#2fdfb3"
TEAL_INK = "#06281c"
RED = "#ff6d7a"
RED_INK = "#2a0d12"
AMBER = "#f0b429"
BLUE = "#79b8ff"
GRID = "#2a3446"
FILL = "#14352e"

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0

CSV_HEADER = [
    "cas",
    "baterie",
    "nazev",
    "vyrobce",
    "stav",
    "procenta",
    "napeti_mV",
    "proud_mA",
    "vykon_mW",
    "zbyvajici_mWh",
    "plna_mWh",
    "navrhova_mWh",
    "kondice_pct",
    "teplota_C",
    "cykly",
    "chemie",
    "serial",
    "cpu_pct",
    "gpu1_nazev",
    "gpu1_pct",
    "gpu2_nazev",
    "gpu2_pct",
    "gpu3_nazev",
    "gpu3_pct",
]

GPU_COLORS = (BLUE, TEAL, "#c084fc", AMBER)
GPU_FILLS = ("#14283a", "#12352e", "#2a1840", "#3a2e12")


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_png(path: Path, width: int, height: int, bgra: bytes) -> None:
    raw = bytearray()
    stride = width * 4
    view = memoryview(bgra)
    for y in range(height):
        raw.append(0)
        row = view[y * stride : (y + 1) * stride]
        for x in range(width):
            i = x * 4
            raw.append(row[i + 2])
            raw.append(row[i + 1])
            raw.append(row[i])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + _png_chunk(b"IEND", b"")
    path.write_bytes(png)


def capture_widget_bgra(widget):
    """Vrátí (šířka, výška, BGRA) viditelné oblasti widgetu."""
    widget.update_idletasks()
    width = int(widget.winfo_width())
    height = int(widget.winfo_height())
    if width < 20 or height < 20:
        raise RuntimeError(tr("Graf nemá rozměr ke uložení. Nechte ho chvíli zobrazený a zkuste to znovu."))
    origin_x = int(widget.winfo_rootx())
    origin_y = int(widget.winfo_rooty())

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int

    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        raise RuntimeError(tr("Nelze získat plochu obrazovky."))
    hdc_mem = None
    bitmap = None
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        bitmap = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
        if not hdc_mem or not bitmap:
            raise RuntimeError(tr("Nelze připravit snímek grafu."))
        gdi32.SelectObject(hdc_mem, bitmap)
        if not gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, origin_x, origin_y, SRCCOPY):
            raise RuntimeError(tr("Snímek grafu se nepodařilo sejmout."))
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        buffer = ctypes.create_string_buffer(width * height * 4)
        rows = gdi32.GetDIBits(hdc_mem, bitmap, 0, height, buffer, ctypes.byref(info), DIB_RGB_COLORS)
        if rows == 0:
            info.bmiHeader.biHeight = height
            rows = gdi32.GetDIBits(hdc_mem, bitmap, 0, height, buffer, ctypes.byref(info), DIB_RGB_COLORS)
            if rows == 0:
                raise RuntimeError(tr("Body snímku se nepodařilo přečíst."))
            raw = bytearray(buffer.raw)
            stride = width * 4
            flipped = bytearray(len(raw))
            for y in range(height):
                src = (height - 1 - y) * stride
                flipped[y * stride : (y + 1) * stride] = raw[src : src + stride]
            raw = flipped
        else:
            raw = buffer.raw
        if not any(raw):
            raise RuntimeError(tr("Snímek je prázdný. Graf musí být vidět na obrazovce."))
        return width, height, bytes(raw)
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if hdc_mem:
            gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)


def save_widget_png(widget, path: Path) -> None:
    width, height, raw = capture_widget_bgra(widget)
    write_png(path, width, height, raw)


def stack_bgra(images: list, gap: int = 8) -> tuple:
    width = max(item[0] for item in images)
    gap_color = bytes((0x1B, 0x14, 0x10, 0xFF))
    height = sum(item[1] for item in images) + gap * (len(images) - 1)
    canvas = bytearray(gap_color * (width * height))
    y = 0
    for item_w, item_h, raw in images:
        view = memoryview(raw)
        stride = item_w * 4
        for row in range(item_h):
            start = (y + row) * width * 4
            canvas[start : start + stride] = view[row * stride : (row + 1) * stride]
        y += item_h + gap
    return width, height, bytes(canvas)


WINDOWS = (
    ("5 min", 5 * 60),
    ("15 min", 15 * 60),
    ("1 hod", 60 * 60),
    ("4 hod", 4 * 60 * 60),
    ("Vše", None),
)
INTERVALS = {"1 s": 1.0, "2 s": 2.0, "5 s": 5.0, "10 s": 10.0}


def fmt_num(value: Optional[float], decimals: int = 0) -> str:
    if value is None:
        return "—"
    neg = value < 0
    number = abs(float(value))
    text = f"{number:.{decimals}f}" if decimals else str(int(round(number)))
    whole, dot, frac = text.partition(".")
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    if comma_decimal():
        body = " ".join(reversed(groups))
        if frac:
            body = body + "," + frac
    else:
        body = ",".join(reversed(groups))
        if frac:
            body = body + "." + frac
    return ("−" if neg else "") + body


def fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0 or seconds >= 0xFFFFFFFE:
        return "—"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours} h {minutes:02d} min"
    if minutes:
        return f"{minutes} min {secs:02d} s"
    return f"{secs} s"


def fmt_mwh(value: Optional[int]) -> str:
    if value is None:
        return "—"
    wh = value / 1000.0
    return f"{fmt_num(wh, 2)} Wh ({fmt_num(value)} mWh)"


def fmt_clock(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def power_state_code(battery: Optional[Battery], system: SystemPower) -> str:
    if battery is None or not battery.present:
        if system.battery_present is False:
            return "absent"
        return "waiting"
    if battery.critical and battery.discharging:
        return "critical"
    if battery.charging:
        return "charging"
    if battery.discharging:
        return "discharging"
    if battery.on_line or system.ac_online:
        if battery.percent is not None and battery.percent >= 99:
            return "full"
        return "ac"
    return "unknown"


def power_state_text(battery: Optional[Battery], system: SystemPower) -> str:
    return {
        "absent": tr("Baterie není přítomna"),
        "waiting": tr("Čekám na data"),
        "critical": tr("Kritické vybíjení"),
        "charging": tr("Nabíjení"),
        "discharging": tr("Vybíjení"),
        "full": tr("Plně nabito"),
        "ac": tr("Ze sítě"),
        "unknown": tr("Neznámý stav"),
    }[power_state_code(battery, system)]


def state_color(code: str) -> str:
    if code in ("critical", "discharging"):
        return RED
    if code == "charging":
        return BLUE
    if code in ("full", "ac"):
        return TEAL
    return AMBER


def flag_text(flag: Optional[int]) -> str:
    if flag is None:
        return "—"
    if flag == 255:
        return tr("neznámé ({flag})", flag="255")
    if flag == 128:
        return tr("bez baterie")
    names = []
    if flag & 8:
        names.append(tr("nabíjení"))
    if flag & 4:
        names.append(tr("kritické"))
    if flag & 2:
        names.append(tr("nízké"))
    if flag & 1:
        names.append(tr("vysoké"))
    body = ", ".join(names) if names else tr("žádný příznak")
    return tr("{body} ({flag})", body=body, flag=f"0x{flag:02X}")


def cooling_text(mode: Optional[int]) -> str:
    if mode is None:
        return "—"
    if mode == 0:
        return tr("aktivní (ventilátor)")
    if mode == 1:
        return tr("pasivní")
    return str(mode)


@dataclass
class Sample:
    t: float
    percent: Optional[float]
    current_ma: Optional[float]
    voltage_mv: Optional[int]
    rate_mw: Optional[int]
    remaining_mwh: Optional[int]
    charging: bool
    discharging: bool
    cpu: Optional[float] = None
    gpus: tuple = ()


def _mean(values: list) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _average_chunk(chunk: list) -> Sample:
    if len(chunk) == 1:
        return chunk[0]

    def avg(attr: str) -> Optional[float]:
        values = [getattr(sample, attr) for sample in chunk if getattr(sample, attr) is not None]
        return _mean(values)

    gpu_sums = {}
    gpu_counts = {}
    for sample in chunk:
        for name, value in sample.gpus:
            gpu_sums[name] = gpu_sums.get(name, 0.0) + float(value)
            gpu_counts[name] = gpu_counts.get(name, 0) + 1
    gpus = tuple((name, gpu_sums[name] / gpu_counts[name]) for name in gpu_sums)
    voltage = avg("voltage_mv")
    rate = avg("rate_mw")
    remaining = avg("remaining_mwh")
    return Sample(
        t=(chunk[0].t + chunk[-1].t) / 2.0,
        percent=avg("percent"),
        current_ma=avg("current_ma"),
        voltage_mv=None if voltage is None else int(round(voltage)),
        rate_mw=None if rate is None else int(round(rate)),
        remaining_mwh=None if remaining is None else int(round(remaining)),
        charging=sum(1 for sample in chunk if sample.charging) * 2 >= len(chunk),
        discharging=sum(1 for sample in chunk if sample.discharging) * 2 >= len(chunk),
        cpu=avg("cpu"),
        gpus=gpus,
    )


def average_samples(samples: list, max_points: int) -> list:
    """Sníží počet bodů průměrováním úseků — vhodné pro dlouhé logy."""
    if max_points < 2 or len(samples) <= max_points:
        return list(samples)
    total = len(samples)
    result = []
    for index in range(max_points):
        start = int(index * total / max_points)
        end = int((index + 1) * total / max_points)
        if end <= start:
            end = min(total, start + 1)
        chunk = samples[start:end]
        if chunk:
            result.append(_average_chunk(chunk))
    return result


def linear_trend(samples: list) -> Optional[tuple]:
    pts = [(s.t, s.percent) for s in samples if s.percent is not None]
    if len(pts) < 4 or pts[-1][0] - pts[0][0] < 15:
        return None
    t0 = pts[0][0]
    xs = [t - t0 for t, _ in pts]
    ys = [p for _, p in pts]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den <= 0:
        return None
    slope = num / den
    intercept = my - slope * mx
    return t0, slope, intercept


def trend_badge(samples: list) -> str:
    fit = linear_trend(samples)
    if fit is None:
        return ""
    _t0, slope, intercept = fit
    last = [s for s in samples if s.percent is not None][-1]
    now_y = slope * (last.t - _t0) + intercept
    per_hour = slope * 3600.0
    rate = fmt_num(per_hour, 1)
    if abs(per_hour) < 0.15:
        return tr("Trend je téměř plochý")
    if slope < 0:
        dt = (0.0 - now_y) / slope
        if dt <= 0:
            return tr("Trend {rate} %/h", rate=rate)
        return tr("Trend vybíjení {rate} %/h · 0 % za {duration}", rate=rate, duration=fmt_duration(dt))
    dt = (100.0 - now_y) / slope
    if dt <= 0:
        return tr("Trend +{rate} %/h", rate=rate)
    return tr("Trend nabíjení +{rate} %/h · 100 % za {duration}", rate=rate, duration=fmt_duration(dt))


def gpu_reader(name: str):
    def read(sample, gpu_name=name):
        for title, value in sample.gpus:
            if title == gpu_name:
                return value
        return None

    return read


def load_badge(series: list, reader) -> str:
    values = [reader(sample) for sample in series if reader(sample) is not None]
    if not values:
        return ""
    return f"{fmt_num(values[-1], 1)} %"


def eta_seconds(battery: Battery) -> tuple:
    """Vrátí (sekundy, popisek)."""
    if battery.discharging and battery.remaining_mwh and battery.rate_mw and battery.rate_mw < 0:
        hours = battery.remaining_mwh / abs(battery.rate_mw)
        return hours * 3600.0, tr("podle kapacity a odběru")
    if battery.charging and battery.full_charged_mwh and battery.remaining_mwh is not None and battery.rate_mw and battery.rate_mw > 0:
        missing = battery.full_charged_mwh - battery.remaining_mwh
        if missing > 0:
            return missing / battery.rate_mw * 3600.0, tr("do plného nabití")
    if battery.estimated_seconds:
        return float(battery.estimated_seconds), tr("odhad Windows")
    if battery.percent is not None and battery.percent >= 99 and (battery.on_line or not battery.discharging):
        return None, tr("baterie je plná")
    return None, tr("nelze spočítat")


class TimeGraph(tk.Canvas):
    def __init__(self, master, title: str, mode: str, color: Optional[str] = None, fill: Optional[str] = None, value_fn=None, graph_height: int = 150):
        super().__init__(
            master,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=LINE,
            height=graph_height,
            bd=0,
        )
        self.title = title
        self.mode = mode
        self.color = color
        self.fill = fill or FILL
        self.value_fn = value_fn
        self.samples: list = []
        self.ref_hours: Optional[float] = None
        self.gap = 15.0
        self.badge = ""
        self.hover_x = None
        self._scale = 20.0 if mode == "power" else 800.0
        self._scale_t = 0.0
        self._mapped: list = []
        self.range_start = None
        self.range_end = None
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)

    def reset_scale(self) -> None:
        self._scale = 20.0 if self.mode == "power" else 800.0
        self._scale_t = 0.0

    def set_series(
        self,
        samples: list,
        ref_hours: Optional[float],
        gap: float,
        badge: str,
        range_start: Optional[float] = None,
        range_end: Optional[float] = None,
    ) -> None:
        self.samples = samples
        self.ref_hours = ref_hours
        self.gap = gap
        self.badge = badge
        self.range_start = range_start
        self.range_end = range_end
        self.redraw()

    def _motion(self, event) -> None:
        self.hover_x = event.x
        self.redraw()

    def _leave(self, _event) -> None:
        self.hover_x = None
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 80 or height < 60:
            return
        left, top, right, bottom = 62, 30, width - 16, height - 26
        self.create_text(12, 8, anchor="nw", text=self.title, fill=TEXT, font=("Segoe UI", 10, "bold"))

        if self.mode in ("percent", "load"):
            y_min, y_max = 0.0, 100.0
            y_labels = [0, 25, 50, 75, 100]
            y_fmt = lambda v: f"{int(v)} %"
        else:
            if self.mode == "power":
                values = [abs(s.rate_mw) / 1000.0 for s in self.samples if s.rate_mw is not None]
                unit_div = 1.0
                unit = "W"
                peak = max(values) if values else 0.0
                target = max(5.0, peak * 1.25)
            else:
                values = [abs(s.current_ma) for s in self.samples if s.current_ma is not None]
                unit_div = 1000.0 if True else 1.0
                unit = "A"
                peak = max(values) if values else 0.0
                target = max(500.0, peak * 1.25)
            stamp = self.samples[-1].t if self.samples else 0.0
            if target > self._scale:
                self._scale = target
                self._scale_t = stamp
            elif stamp - self._scale_t >= 1.0:
                self._scale = max(target, self._scale * 0.9)
                self._scale_t = stamp
            y_max = self._scale
            y_min = -self._scale
            if self.mode == "power":
                y_fmt = lambda v: f"{fmt_num(v, 1)} W"
            elif y_max >= 2000:
                y_fmt = lambda v: f"{fmt_num(v / 1000.0, 2)} A"
            else:
                y_fmt = lambda v: f"{fmt_num(v, 0)} mA"
            y_labels = [y_min, y_min / 2, 0, y_max / 2, y_max]

        for value in y_labels:
            y = self._y(value, y_min, y_max, top, bottom)
            self.create_line(left, y, right, y, fill=GRID)
            self.create_text(left - 8, y, anchor="e", text=y_fmt(value), fill=MUTED, font=("Segoe UI", 8))

        usable = [s for s in self.samples if self._value(s) is not None]
        if self.range_start is not None and self.range_end is not None:
            t0 = float(self.range_start)
            t1 = max(float(self.range_end), t0 + 1.0)
        elif usable:
            t0 = usable[0].t
            t1 = usable[-1].t
            if t1 - t0 < 30:
                t1 = t0 + 30
        else:
            self.create_text(
                (left + right) / 2,
                (top + bottom) / 2,
                text=tr("Čekám na první vzorky…"),
                fill=MUTED,
                font=("Segoe UI", 11),
            )
            return

        if not usable:
            self._time_axis(t0, t1, left, right, bottom, height)
            self.create_text(
                (left + right) / 2,
                (top + bottom) / 2,
                text=tr("Čekám na první vzorky…"),
                fill=MUTED,
                font=("Segoe UI", 11),
            )
            return

        plot_width = max(80, int(right - left))
        max_points = max(80, min(plot_width, 1500))
        raw_count = len(usable)
        usable = average_samples(usable, max_points)
        if len(usable) >= 2:
            spacing = (usable[-1].t - usable[0].t) / max(len(usable) - 1, 1)
            self.gap = max(self.gap, spacing * 4.0)

        badge = self.badge
        if raw_count > len(usable):
            note = tr("průměr {shown} / {total} bodů", shown=len(usable), total=raw_count)
            badge = f"{badge}    {note}".strip() if badge else note
        if badge:
            self.create_text(width - 12, 8, anchor="ne", text=badge, fill=MUTED, font=("Segoe UI", 9))

        self._time_axis(t0, t1, left, right, bottom, height)

        if self.mode in ("percent", "load"):
            self._draw_percent(usable, t0, t1, y_min, y_max, left, top, right, bottom)
        else:
            self._draw_signed(usable, t0, t1, y_min, y_max, left, top, right, bottom)
        self._hover(t0, t1, y_min, y_max, left, top, right, bottom)

    def _value(self, sample: Sample) -> Optional[float]:
        if self.value_fn is not None:
            return self.value_fn(sample)
        if self.mode == "percent":
            return sample.percent
        if self.mode == "load":
            return sample.cpu
        if self.mode == "power":
            if sample.rate_mw is None:
                return None
            return sample.rate_mw / 1000.0
        return sample.current_ma

    def _x(self, t, t0, t1, left, right) -> float:
        span = max(t1 - t0, 1e-6)
        return left + (t - t0) / span * (right - left)

    def _y(self, value, y_min, y_max, top, bottom) -> float:
        span = max(y_max - y_min, 1e-6)
        return bottom - (value - y_min) / span * (bottom - top)

    def _time_axis(self, t0, t1, left, right, bottom, height) -> None:
        span = t1 - t0
        ticks = 4
        for i in range(ticks + 1):
            t = t0 + span * i / ticks
            x = self._x(t, t0, t1, left, right)
            self.create_line(x, bottom, x, bottom + 4, fill=GRID)
            label = datetime.fromtimestamp(t).strftime("%H:%M:%S" if span < 180 else "%H:%M")
            if i == 0:
                anchor = "sw"
            elif i == ticks:
                anchor = "se"
            else:
                anchor = "s"
            self.create_text(x, height - 4, anchor=anchor, text=label, fill=MUTED, font=("Segoe UI", 8))

    def _groups(self, samples: list) -> list:
        groups = []
        current = []
        prev = None
        for sample in samples:
            if prev is not None and sample.t - prev > self.gap:
                if current:
                    groups.append(current)
                current = []
            current.append(sample)
            prev = sample.t
        if current:
            groups.append(current)
        return groups

    def _draw_percent(self, samples, t0, t1, y_min, y_max, left, top, right, bottom) -> None:
        if self.mode == "load" and self.color:
            color = self.color
        elif samples[-1].discharging:
            color = RED
        elif samples[-1].charging:
            color = BLUE
        else:
            color = TEAL
        self._mapped = []
        for group in self._groups(samples):
            coords = []
            base = []
            for sample in group:
                amount = self._value(sample)
                x = self._x(sample.t, t0, t1, left, right)
                y = self._y(amount, y_min, y_max, top, bottom)
                coords.extend((x, y))
                base.append((x, y))
                self._mapped.append((x, y, sample))
            if len(base) >= 2:
                poly = []
                for x, y in base:
                    poly.extend((x, y))
                poly.extend((base[-1][0], bottom, base[0][0], bottom))
                self.create_polygon(*poly, fill=self.fill if self.mode == "load" else FILL, outline="")
                self.create_line(*coords, fill=color, width=2.4, capstyle=tk.ROUND, joinstyle=tk.ROUND)
            elif base:
                self.create_oval(base[0][0] - 3, base[0][1] - 3, base[0][0] + 3, base[0][1] + 3, fill=color, outline="")

        fit = linear_trend(samples) if self.mode == "percent" else None
        if fit is not None:
            origin, slope, intercept = fit
            per_hour = slope * 3600.0
            if abs(per_hour) >= 0.15:
                x0 = self._x(samples[0].t, t0, t1, left, right)
                y0 = self._y(intercept, y_min, y_max, top, bottom)
                y_end = slope * (samples[-1].t - origin) + intercept
                x1 = self._x(samples[-1].t, t0, t1, left, right)
                y1 = self._y(y_end, y_min, y_max, top, bottom)
                self.create_line(x0, y0, x1, y1, fill=AMBER, width=1.4, dash=(5, 4))

        if self.mode == "percent" and self.ref_hours and samples[0].percent is not None:
            p0 = samples[0].percent
            start = samples[0].t
            slope = -(100.0 / self.ref_hours) / 3600.0
            end_t = samples[-1].t
            p1 = p0 + slope * (end_t - start)
            x0 = self._x(start, t0, t1, left, right)
            x1 = self._x(end_t, t0, t1, left, right)
            y0 = self._y(p0, y_min, y_max, top, bottom)
            y1 = self._y(p1, y_min, y_max, top, bottom)
            self.create_line(x0, y0, x1, y1, fill=MUTED, width=1.2, dash=(2, 3))

    def _draw_signed(self, samples, t0, t1, y_min, y_max, left, top, right, bottom) -> None:
        zero = self._y(0, y_min, y_max, top, bottom)
        self.create_line(left, zero, right, zero, fill="#415068", dash=(3, 3))
        self._mapped = []
        prev = None
        for sample in samples:
            amount = self._value(sample)
            if amount is None:
                prev = None
                continue
            x = self._x(sample.t, t0, t1, left, right)
            y = self._y(amount, y_min, y_max, top, bottom)
            self._mapped.append((x, y, sample))
            if prev is not None and sample.t - prev[2].t <= self.gap:
                if amount > 0.05:
                    color = BLUE
                elif amount < -0.05:
                    color = RED
                else:
                    color = TEAL
                self.create_line(prev[0], prev[1], x, y, fill=color, width=2.2, capstyle=tk.ROUND)
            prev = (x, y, sample)
        if len(self._mapped) == 1:
            x, y, _s = self._mapped[0]
            self.create_oval(x - 3, y - 3, x + 3, y + 3, fill=TEAL, outline="")

    def _draw_current(self, samples, t0, t1, y_min, y_max, left, top, right, bottom) -> None:
        self._draw_signed(samples, t0, t1, y_min, y_max, left, top, right, bottom)

    def _hover(self, t0, t1, y_min, y_max, left, top, right, bottom) -> None:
        if self.hover_x is None or not self._mapped:
            return
        if not (left <= self.hover_x <= right):
            return
        nearest = min(self._mapped, key=lambda item: abs(item[0] - self.hover_x))
        x, y, sample = nearest
        self.create_line(x, top, x, bottom, fill="#5c6b82")
        self.create_oval(x - 3.5, y - 3.5, x + 3.5, y + 3.5, fill=TEXT, outline=BG)
        if self.mode in ("percent", "load"):
            value = f"{fmt_num(self._value(sample), 1)} %"
        elif self.mode == "power":
            value = f"{fmt_num(self._value(sample), 2)} W"
        else:
            value = f"{fmt_num(sample.current_ma, 0)} mA"
        label = f"{fmt_clock(sample.t)}   {value}"
        anchor = "nw" if x < (left + right) / 2 else "ne"
        tx = x + 8 if anchor == "nw" else x - 8
        self.create_rectangle(tx if anchor == "nw" else tx - 150, top + 4, (tx + 150) if anchor == "nw" else tx, top + 24, fill="#0d1218", outline="")
        self.create_text(tx, top + 8, anchor=anchor, text=label, fill=TEXT, font=("Segoe UI", 9))


class StatCard(tk.Frame):
    def __init__(self, master, title: str, accent: str):
        super().__init__(master, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        tk.Frame(self, bg=accent, width=3).pack(side="left", fill="y")
        body = tk.Frame(self, bg=CARD)
        body.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        self.title_label = tk.Label(body, text=title, bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.title_label.pack(fill="x")
        self.value_label = tk.Label(body, text="—", bg=CARD, fg=TEXT, font=("Segoe UI", 20, "bold"), anchor="w")
        self.value_label.pack(fill="x", pady=(2, 0))
        self.sub_label = tk.Label(body, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.sub_label.pack(fill="x")
        self._default_title = title

    def set(self, value: str, sub: str = "", color: str = TEXT) -> None:
        self.value_label.configure(text=value, fg=color)
        self.sub_label.configure(text=sub)

    def set_title(self, title: str) -> None:
        self.title_label.configure(text=title)


class MonitorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self.root.minsize(1020, 700)
        self._place_window()
        self._style()

        self.stop = threading.Event()
        self.pause = threading.Event()
        self.queue = []
        self.lock = threading.Lock()
        self.history = {}
        self.selected_key = None
        self.latest: Optional[Snapshot] = None
        self.latest_load = None
        self.started = time.time()
        self.interval = 1.0
        self.window_seconds = None
        self.ref_hours = None
        self.csv_path = None
        self._csv_ready = False
        self.recording = False
        self.graphs_visible = True
        self.lower_visible = True
        self._stamp_override = None
        self._normal_geometry = None
        self.mini = False
        self.alive = True
        self.view_mode = "live"
        self.loaded_log = None
        self.loaded_path = None
        self.loaded_report = None
        self._live_key = None
        self._last_axis_redraw = 0.0
        self.discharge_started = None
        self.charge_started = None
        self.last_discharge_seconds = None
        self.last_charge_seconds = None
        self._record_led_on = False

        self._build()
        self._blink_record_led()
        self._start_recording_session()
        self._start_worker()
        self._poll()
        self._clock()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(1200, lambda: schedule_update_check(self.root, self._offer_update))

    def _place_window(self) -> None:
        self.root.update_idletasks()
        width, height = 1180, min(1040, max(800, self.root.winfo_screenheight() - 80))
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
        style.configure("TNotebook.Tab", background=CARD, foreground=MUTED, padding=(14, 6), font=("Segoe UI", 10))
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", TEXT)])
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            borderwidth=0,
            rowheight=26,
            font=("Segoe UI", 9),
        )
        style.configure("Treeview.Heading", background=CARD, foreground=MUTED, relief="flat", font=("Segoe UI", 9))
        style.map("Treeview", background=[("selected", "#24344a")], foreground=[("selected", TEXT)])
        style.configure(
            "TCombobox",
            fieldbackground=CARD,
            background=CARD,
            foreground=TEXT,
            arrowcolor=TEXT,
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
            padding=4,
        )
        style.configure("Vertical.TScrollbar", background=CARD, troughcolor=BG, bordercolor=BG, arrowcolor=TEXT)
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)

    def _build(self) -> None:
        self.header = tk.Frame(self.root, bg=BG)
        self.header.pack(fill="x", padx=16, pady=(14, 6))
        self.icon = tk.Canvas(self.header, width=36, height=22, bg=BG, highlightthickness=0)
        self.icon.pack(side="left", padx=(0, 10))
        titles = tk.Frame(self.header, bg=BG)
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(titles, text=APP_TITLE, bg=BG, fg=TEXT, font=("Segoe UI", 18, "bold"), anchor="w").pack(fill="x")
        self.header_clock = tk.Label(titles, text="", bg=BG, fg=MUTED, font=("Segoe UI", 10), anchor="w")
        self.header_clock.pack(fill="x")

        side = tk.Frame(self.header, bg=BG)
        side.pack(side="right")
        self.pill = tk.Label(side, text=tr("Připojuji…"), bg=CARD, fg=TEXT, font=("Segoe UI", 10, "bold"), padx=12, pady=5)
        self.pill.pack(side="left", padx=(0, 12))
        timers = tk.Frame(side, bg=BG)
        timers.pack(side="left")
        tk.Label(timers, text=tr("Vybíjení"), bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="e").grid(row=0, column=0, sticky="e", padx=(0, 8))
        tk.Label(timers, text=tr("Nabíjení"), bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="e").grid(row=0, column=1, sticky="e")
        self.discharge_clock = tk.Label(timers, text="—", bg=BG, fg=RED, font=("Segoe UI", 12, "bold"), anchor="e")
        self.discharge_clock.grid(row=1, column=0, sticky="e", padx=(0, 8))
        self.charge_clock = tk.Label(timers, text="—", bg=BG, fg=BLUE, font=("Segoe UI", 12, "bold"), anchor="e")
        self.charge_clock.grid(row=1, column=1, sticky="e")

        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        cards = tk.Frame(self.body, bg=BG)
        cards.pack(fill="x", pady=(4, 8))
        specs = (
            ("percent", tr("Nabití"), TEAL),
            ("voltage", tr("Napětí"), BLUE),
            ("current", tr("Proud"), AMBER),
            ("power", tr("Výkon"), RED),
            ("eta", tr("Zbývající čas"), TEAL),
            ("health", tr("Kondice"), BLUE),
        )
        self.cards = {}
        for col, (key, title, accent) in enumerate(specs):
            cards.columnconfigure(col, weight=1, uniform="cards")
            card = StatCard(cards, title, accent)
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0))
            self.cards[key] = card

        actions = tk.Frame(self.body, bg=BG)
        actions.pack(fill="x", pady=(0, 8))
        self.battery_var = tk.StringVar()
        self.battery_box = ttk.Combobox(actions, textvariable=self.battery_var, state="readonly", width=22)
        self.info_btn = self._button(
            actions,
            tr("Info baterie"),
            self._show_battery_dialog,
            bg="#24384a",
            fg=BLUE,
            hover="#2f4a60",
            border=BLUE,
        )
        self.info_btn.pack(side="left", padx=(0, 8))
        self.graph_btn = self._button(actions, tr("Skrýt graf"), self._toggle_graphs)
        self.graph_btn.pack(side="left")
        self._style_toggle(self.graph_btn, True, tr("Skrýt graf"), tr("Zobrazit graf"))
        self._button(actions, tr("Uložit grafy"), self._save_graph).pack(side="left", padx=(4, 0))
        self._button(actions, tr("Uložit data"), self._save_data).pack(side="left", padx=(4, 0))
        self._button(actions, tr("Načíst log"), self._load_log).pack(side="left", padx=(4, 0))
        self.live_btn = self._button(actions, tr("Živá data"), self._return_live)
        self.record_btn = self._button(actions, tr("Záznam vypnut"), self._toggle_recording)
        self.record_btn.pack(side="left", padx=(4, 0))
        self._style_toggle(self.record_btn, False, tr("Záznam zapnut"), tr("Záznam vypnut"))
        self.record_led = tk.Canvas(actions, width=16, height=16, bg=BG, highlightthickness=0)
        self.record_led.pack(side="left", padx=(6, 0))
        self._draw_record_led(False)
        self.pause_btn = self._button(actions, tr("Pauza"), self._toggle_pause)
        self.pause_btn.pack(side="right", padx=(4, 0))
        self._button(actions, tr("Mini"), self._enter_mini).pack(side="right", padx=(4, 0))
        self._button(actions, tr("Vymazat graf"), self._clear).pack(side="right", padx=(4, 0))
        self._button(actions, tr("Složka logů"), self._open_logs).pack(side="right", padx=(4, 0))

        self.middle = tk.Frame(self.body, bg=BG)
        self.middle.pack(fill="both", expand=True)
        self.lower = tk.Frame(self.middle, bg=BG, height=200)
        self.lower.pack(side="bottom", fill="x", pady=(8, 0))
        self.lower.pack_propagate(False)
        self.graphs_wrap = tk.Frame(self.middle, bg=BG)
        self.graphs_wrap.pack(fill="both", expand=True)
        graph_row = tk.Frame(self.graphs_wrap, bg=BG)
        graph_row.pack(fill="both", expand=True)
        self.graph_canvas = tk.Canvas(graph_row, bg=BG, highlightthickness=0)
        graph_scroll = ttk.Scrollbar(graph_row, orient="vertical", command=self.graph_canvas.yview)
        self.graph_canvas.configure(yscrollcommand=graph_scroll.set)
        self.graphs = tk.Frame(self.graph_canvas, bg=BG)
        self._graph_window = self.graph_canvas.create_window((0, 0), window=self.graphs, anchor="nw")
        self.graphs.bind("<Configure>", lambda _e: self.graph_canvas.configure(scrollregion=self.graph_canvas.bbox("all")))
        self.graph_canvas.bind("<Configure>", lambda e: self.graph_canvas.itemconfigure(self._graph_window, width=e.width))
        self.graph_canvas.pack(side="left", fill="both", expand=True)
        graph_scroll.pack(side="right", fill="y")
        self.charge_graph = TimeGraph(self.graphs, tr("Nabití"), "percent")
        self.power_graph = TimeGraph(self.graphs, tr("Výkon  ·  kladný nabíjí, záporný odebírá"), "power")
        self.current_graph = self.power_graph
        self.cpu_graph = TimeGraph(
            self.graphs,
            tr("Vytížení CPU"),
            "load",
            color=AMBER,
            fill="#3a2e12",
            value_fn=lambda sample: sample.cpu,
        )
        self.gpu_graphs = {}
        for graph in (self.charge_graph, self.power_graph, self.cpu_graph):
            graph.pack(fill="x", pady=(0, 8))
            self._hook_wheel(graph)
        self._hook_wheel(self.graph_canvas)
        self._hook_wheel(self.graphs)
        self._sync_gpu_graphs(())

        self.notebook = ttk.Notebook(self.lower)
        self.notebook.pack(fill="both", expand=True)

        # Informace o baterii jen v dialogu — hodnoty se drží v skrytém frame.
        self.info_labels = {}
        self._info_store = tk.Frame(self.root, bg=PANEL)
        self._build_info(self._info_store)

        summary = self._scroll_tab()
        self.notebook.add(summary["outer"], text=tr("Souhrn měření"))
        self.summary_labels = {}
        self._build_summary(summary["inner"])

        self.footer = tk.Frame(self.root, bg=PANEL)
        self.footer.pack(fill="x", side="bottom")
        foot_left = tk.Frame(self.footer, bg=PANEL)
        foot_left.pack(side="left", fill="x", expand=True)
        foot_center = tk.Frame(self.footer, bg=PANEL)
        foot_center.pack(side="left")
        foot_right = tk.Frame(self.footer, bg=PANEL)
        foot_right.pack(side="left", fill="x", expand=True)
        self.footer_file = tk.Label(
            foot_left,
            text=tr("záznam vypnut"),
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
            padx=16,
            pady=6,
        )
        self.footer_file.pack(side="left", fill="x")
        self.panel_btn = self._button(foot_center, tr("Skrýt panel"), self._toggle_lower)
        self.panel_btn.pack(pady=4, padx=8)
        self._update_stamp()

        self.mini_frame = tk.Frame(self.root, bg=BG)
        self._build_mini()
        self.subtitle = None
        self.graph_stamp = None
        self.clock = self.discharge_clock
        self.win_buttons = {}
        self.tree = None
        self.interval_var = tk.StringVar(value="1 s")
        self.ref_var = tk.StringVar()

    def _build_mini(self) -> None:
        row = tk.Frame(self.mini_frame, bg=BG)
        row.pack(fill="both", expand=True, padx=12, pady=10)
        self.mini_icon = tk.Canvas(row, width=36, height=22, bg=BG, highlightthickness=0)
        self.mini_icon.pack(side="left", padx=(0, 8))
        self.mini_percent = tk.Label(row, text="—", bg=BG, fg=TEXT, font=("Segoe UI", 22, "bold"))
        self.mini_percent.pack(side="left")
        self.mini_state = tk.Label(row, text="", bg=BG, fg=MUTED, font=("Segoe UI", 10))
        self.mini_state.pack(side="left", padx=(10, 0))
        self._button(row, tr("Zpět"), self._leave_mini).pack(side="right")
        self.mini_eta = tk.Label(row, text="", bg=BG, fg=TEXT, font=("Segoe UI", 11))
        self.mini_eta.pack(side="right", padx=12)
        self.mini_current = tk.Label(row, text="", bg=BG, fg=AMBER, font=("Segoe UI", 12, "bold"))
        self.mini_current.pack(side="right", padx=8)

    def _scroll_tab(self) -> dict:
        outer = tk.Frame(self.notebook, bg=PANEL)
        canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PANEL)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas(event):
            canvas.itemconfigure(window, width=event.width)

        def _wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")

        inner.bind("<Configure>", _on_inner)
        canvas.bind("<Configure>", _on_canvas)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scroll.set)
        return {"outer": outer, "inner": inner}

    def _build_info(self, parent) -> None:
        fields = [
            ("state", tr("Stav")),
            ("feed", tr("Napájení")),
            ("percent", tr("Nabití podle kapacity")),
            ("win_percent", tr("Nabití podle Windows")),
            ("voltage", tr("Napětí")),
            ("current", tr("Proud baterie")),
            ("power", tr("Výkon")),
            ("rate", tr("Rychlost")),
            ("remain", tr("Zbývající kapacita")),
            ("full", tr("Plná nabitá kapacita")),
            ("design", tr("Návrhová kapacita")),
            ("health", tr("Kondice")),
            ("wear", tr("Opotřebení")),
            ("drop", tr("Úbytek od startu měření")),
            ("chem", tr("Chemie")),
            ("tech", tr("Technologie")),
            ("cycles", tr("Počet cyklů")),
            ("temp", tr("Teplota")),
            ("maker", tr("Výrobce")),
            ("name", tr("Název")),
            ("serial", tr("Sériové číslo")),
            ("uid", tr("Unikátní ID")),
            ("made", tr("Datum výroby")),
            ("eta", tr("Odhad času")),
            ("alert1", tr("Výchozí upozornění 1")),
            ("alert2", tr("Výchozí upozornění 2")),
            ("bias", tr("Kritická odchylka")),
            ("gran", tr("Granularita měření")),
            ("caps", tr("Vlastnosti")),
            ("tag", tr("Tag baterie")),
            ("flags", tr("Příznaky Windows")),
            ("saver", tr("Šetření baterie")),
            ("idle", tr("Nečinnost systému")),
            ("cool", tr("Režim chlazení")),
            ("life", tr("Zbývající čas Windows")),
            ("full_life", tr("Plná výdrž Windows")),
            ("source", tr("Zdroj dat")),
            ("note", tr("Poznámka")),
            ("path", tr("Cesta zařízení")),
        ]
        self.info_field_titles = {}
        for row, (key, label) in enumerate(fields):
            self.info_field_titles[key] = label
            tk.Label(parent, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w", width=28).grid(
                row=row, column=0, sticky="nw", padx=(12, 8), pady=2
            )
            value = tk.Label(parent, text="—", bg=PANEL, fg=TEXT, font=("Segoe UI", 10), anchor="w", justify="left", wraplength=680)
            value.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=2)
            self.info_labels[key] = value
        parent.columnconfigure(1, weight=1)

    def _build_summary(self, parent) -> None:
        fields = [
            ("battery", tr("Baterie")),
            ("elapsed", tr("Doba celého záznamu")),
            ("discharge_time", tr("Doba vybíjení")),
            ("charge_time", tr("Doba nabíjení")),
            ("count", tr("Počet vzorků")),
            ("start_p", tr("Nabití na začátku")),
            ("now_p", tr("Nabití na konci")),
            ("consumed_pct", tr("Spotřebovaná kapacita")),
            ("consumed_cap", tr("Spotřebovaná energie (kapacita)")),
            ("drawn", tr("Odebraná energie (z výkonu)")),
            ("stored", tr("Dodaná energie (nabíjení)")),
            ("avg_p", tr("Průměrný výkon odběru")),
            ("peak_p", tr("Špičkový výkon odběru")),
            ("avg_rate", tr("Průměrná rychlost vybíjení")),
            ("projected", tr("Odhad plné výdrže")),
            ("avg_v", tr("Průměrné napětí")),
            ("span_v", tr("Rozsah napětí")),
            ("health", tr("Kondice / opotřebení")),
            ("errors", tr("Počet chyb / varování")),
            ("errors_detail", tr("Nalezené problémy")),
            ("cpu", tr("Vytížení CPU")),
            ("gpu", tr("Vytížení GPU")),
        ]
        self.summary_field_titles = {}
        for row, (key, label) in enumerate(fields):
            self.summary_field_titles[key] = label
            tk.Label(parent, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w", width=32).grid(
                row=row, column=0, sticky="nw", padx=(12, 8), pady=2
            )
            value = tk.Label(parent, text="—", bg=PANEL, fg=TEXT, font=("Segoe UI", 10), anchor="w", justify="left", wraplength=700)
            value.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=2)
            self.summary_labels[key] = value
        parent.columnconfigure(1, weight=1)

    def _button(self, parent, text: str, command, bg=None, fg=None, hover=None, border=None) -> tk.Button:
        normal_bg = bg or CARD
        normal_fg = fg or TEXT
        hover_bg = hover or "#283246"
        border_color = border or LINE
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=normal_bg,
            fg=normal_fg,
            activebackground=hover_bg,
            activeforeground=normal_fg,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            font=("Segoe UI", 9),
            highlightthickness=1,
            highlightbackground=border_color,
            highlightcolor=TEAL,
        )
        button._normal_bg = normal_bg
        button._normal_fg = normal_fg
        button._hover_bg = hover_bg
        button.bind(
            "<Enter>",
            lambda _e, b=button: None if getattr(b, "selected", False) else b.configure(bg=b._hover_bg),
        )
        button.bind(
            "<Leave>",
            lambda _e, b=button: b.configure(bg=TEAL, fg=TEAL_INK)
            if getattr(b, "selected", False)
            else b.configure(bg=b._normal_bg, fg=b._normal_fg),
        )
        return button

    def _mark_window_buttons(self, selected: str) -> None:
        return

    def _select_window(self, name: str, seconds: Optional[int]) -> None:
        self.window_seconds = seconds
        self._redraw()

    def _on_interval(self, _event=None) -> None:
        self.interval = INTERVALS.get(self.interval_var.get(), 1.0)

    def _apply_ref(self) -> None:
        self.ref_hours = None
        self._redraw()

    def _style_toggle(self, button, on: bool, on_text: str, off_text: str) -> None:
        button.selected = on
        button.configure(text=on_text if on else off_text, bg=TEAL if on else CARD, fg=TEAL_INK if on else TEXT)

    def _toggle_graphs(self) -> None:
        self._set_graphs_visible(not self.graphs_visible)

    def _set_graphs_visible(self, visible: bool) -> None:
        self.graphs_visible = visible
        self._style_toggle(self.graph_btn, visible, tr("Skrýt graf"), tr("Zobrazit graf"))
        if visible:
            self.graphs_wrap.pack(fill="both", expand=True)
            if self.lower_visible:
                self.lower.pack(side="bottom", fill="x", pady=(8, 0))
                self.lower.configure(height=200)
                self.lower.pack_propagate(False)
            self._redraw()
            self._update_stamp()
        else:
            self.graphs_wrap.pack_forget()
            self.lower.pack(side="bottom", fill="both", expand=True)
            self.lower.pack_propagate(True)
            self.lower_visible = True
            self.panel_btn.configure(text=tr("Skrýt panel"))

    def _toggle_lower(self) -> None:
        if not self.graphs_visible:
            # Když jsou skryté grafy, panel je hlavní oblast — neschovávat.
            return
        self.lower_visible = not self.lower_visible
        if self.lower_visible:
            self.lower.configure(height=200)
            self.lower.pack_propagate(False)
            self.lower.pack(side="bottom", fill="x", pady=(8, 0))
            self.panel_btn.configure(text=tr("Skrýt panel"))
        else:
            self.lower.pack_forget()
            self.panel_btn.configure(text=tr("Zobrazit panel"))
        self.root.update_idletasks()

    def _draw_record_led(self, on: bool) -> None:
        if not hasattr(self, "record_led"):
            return
        self.record_led.delete("all")
        color = RED if on else "#3a2228"
        self.record_led.create_oval(2, 2, 14, 14, fill=color, outline="")

    def _blink_record_led(self) -> None:
        if not self.alive:
            return
        if self.recording:
            self._record_led_on = not self._record_led_on
            self._draw_record_led(self._record_led_on)
        else:
            self._record_led_on = False
            self._draw_record_led(False)
        self.root.after(500, self._blink_record_led)

    def _track_phase(self, charging: bool, discharging: bool) -> None:
        now = time.time()
        if discharging:
            if self.charge_started is not None:
                self.last_charge_seconds = now - self.charge_started
                self.charge_started = None
            if self.discharge_started is None:
                self.discharge_started = now
        elif charging:
            if self.discharge_started is not None:
                self.last_discharge_seconds = now - self.discharge_started
                self.discharge_started = None
            if self.charge_started is None:
                self.charge_started = now
        else:
            if self.discharge_started is not None:
                self.last_discharge_seconds = now - self.discharge_started
                self.discharge_started = None
            if self.charge_started is not None:
                self.last_charge_seconds = now - self.charge_started
                self.charge_started = None

    def _phase_text(self, started, last_seconds) -> str:
        if started is not None:
            return fmt_duration(time.time() - started)
        if last_seconds is not None:
            return fmt_duration(last_seconds)
        return "—"

    def _update_phase_clocks(self) -> None:
        if hasattr(self, "discharge_clock"):
            self.discharge_clock.configure(
                text=self._phase_text(self.discharge_started, self.last_discharge_seconds)
            )
        if hasattr(self, "charge_clock"):
            self.charge_clock.configure(
                text=self._phase_text(self.charge_started, self.last_charge_seconds)
            )

    def _show_battery_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(tr("Informace o baterii"))
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("640x520")
        frame = tk.Frame(dialog, bg=PANEL)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        canvas = tk.Canvas(frame, bg=PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PANEL)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scroll.set)
        if self.info_labels:
            row = 0
            for key, label in self.info_labels.items():
                title = self.info_field_titles.get(key, key)
                tk.Label(inner, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w", width=28).grid(
                    row=row, column=0, sticky="nw", padx=(4, 8), pady=2
                )
                tk.Label(
                    inner,
                    text=label.cget("text"),
                    bg=PANEL,
                    fg=TEXT,
                    font=("Segoe UI", 10),
                    anchor="w",
                    justify="left",
                    wraplength=380,
                ).grid(row=row, column=1, sticky="ew", pady=2)
                row += 1
            inner.columnconfigure(1, weight=1)
        else:
            tk.Label(inner, text=tr("Zatím nejsou k dispozici žádné údaje."), bg=PANEL, fg=MUTED).pack()
        self._button(dialog, tr("Zavřít"), dialog.destroy).pack(pady=(0, 12))

    def _recording_filename(self, when: Optional[datetime] = None) -> str:
        stamp = (when or datetime.now()).strftime("%Y-%m-%d %H-%M-%S")
        return f"{stamp}.csv"

    def _start_recording_session(self) -> None:
        folder = logs_dir()
        when = datetime.now()
        path = folder / self._recording_filename(when)
        while path.exists():
            when = when + timedelta(seconds=1)
            path = folder / self._recording_filename(when)
        self.csv_path = path
        self._csv_ready = False
        self.recording = True
        if hasattr(self, "record_btn"):
            self._style_toggle(self.record_btn, True, tr("Záznam zapnut"), tr("Záznam vypnut"))
        self._update_stamp()

    def _stop_recording_session(self) -> None:
        self.recording = False
        if hasattr(self, "record_btn"):
            self._style_toggle(self.record_btn, False, tr("Záznam zapnut"), tr("Záznam vypnut"))
        self._draw_record_led(False)
        self._update_stamp()

    def _toggle_recording(self) -> None:
        if self.recording:
            self._stop_recording_session()
        else:
            self._start_recording_session()

    def _update_stamp(self) -> None:
        when = self._stamp_override or datetime.now()
        if hasattr(self, "header_clock") and self.header_clock is not None:
            stamp_fmt = "%Y-%m-%d    %H:%M:%S" if language() == "en" else "%d. %m. %Y    %H:%M:%S"
            self.header_clock.configure(text=when.strftime(stamp_fmt))
        if hasattr(self, "footer_file") and self.footer_file is not None:
            if self.view_mode == "log" and self.loaded_path is not None:
                text = tr("prohlížení: {path}", path=as_app_relative(self.loaded_path))
            elif self.recording and self.csv_path is not None:
                text = tr("záznam: {path}", path=as_app_relative(self.csv_path))
            else:
                text = tr("průběžný záznam vypnut")
            self.footer_file.configure(text=text)

    def _hook_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._graph_wheel)

    def _graph_wheel(self, event) -> None:
        self.graph_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _sync_gpu_graphs(self, names) -> None:
        wanted = tuple(names) if names else ("",)
        if tuple(self.gpu_graphs.keys()) == wanted:
            return
        for graph in self.gpu_graphs.values():
            graph.destroy()
        self.gpu_graphs = {}
        for index, name in enumerate(wanted):
            if name:
                title = tr("Vytížení GPU · {name}", name=name)
                reader = gpu_reader(name)
            else:
                title = tr("Vytížení GPU")
                reader = lambda _sample: None
            graph = TimeGraph(
                self.graphs,
                title,
                "load",
                color=GPU_COLORS[index % len(GPU_COLORS)],
                fill=GPU_FILLS[index % len(GPU_FILLS)],
                value_fn=reader,
            )
            graph.pack(fill="x", pady=(0, 8))
            self._hook_wheel(graph)
            self.gpu_graphs[name] = graph

    def _load_log(self) -> None:
        folder = logs_dir()
        path = filedialog.askopenfilename(
            parent=self.root,
            title=tr("Načíst log"),
            initialdir=str(folder),
            filetypes=[(tr("Tabulka CSV"), "*.csv"), (tr("Všechny soubory"), "*.*")],
        )
        if not path:
            return
        try:
            loaded = load_log_csv(Path(path), Sample)
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("Log se nepodařilo načíst.\n{error}", error=exc))
            return
        self._enter_log_view(loaded)

    def _enter_log_view(self, loaded) -> None:
        if self.selected_key:
            self._live_key = self.selected_key
        self.loaded_log = loaded
        self.loaded_path = Path(loaded.path)
        self.view_mode = "log"
        self.history["__log__"] = list(loaded.samples)
        self.selected_key = "__log__"
        if not self.live_btn.winfo_ismapped():
            self.live_btn.pack(side="left", padx=(4, 0), after=self.record_btn)
        self.window_seconds = None
        self._paint_log(loaded)
        self._update_stamp()
        try:
            self.notebook.select(0)
        except tk.TclError:
            pass
        report = self.loaded_report or analyze_measurement(loaded.samples, loaded)
        self._show_measurement_report(report, loaded)


    def _return_live(self) -> None:
        self.view_mode = "live"
        self.loaded_log = None
        self.loaded_path = None
        self.loaded_report = None
        if self.live_btn.winfo_ismapped():
            self.live_btn.pack_forget()
        if self._live_key and self._live_key in self.history:
            self.selected_key = self._live_key
        elif self.history:
            keys = [key for key in self.history.keys() if key != "__log__"]
            self.selected_key = keys[0] if keys else None
        else:
            self.selected_key = None
        self.history.pop("__log__", None)
        series = self._selected_samples()
        if self.latest and self.selected_key:
            battery = self._selected_battery()
            if battery is not None:
                self._paint(self.latest, battery, series)
            else:
                self._redraw()
        else:
            self._redraw()
        self._update_stamp()

    def _paint_log(self, loaded) -> None:
        series = list(loaded.samples)
        last = series[-1]
        report = analyze_measurement(series, loaded)
        self.loaded_report = report
        percent_color = TEAL if last.percent is None or last.percent >= 50 else AMBER if last.percent >= 20 else RED

        if last.voltage_mv:
            self.cards["voltage"].set(f"{fmt_num(last.voltage_mv / 1000.0, 2)} V", f"{fmt_num(last.voltage_mv)} mV")
        else:
            self.cards["voltage"].set("—", "")
        if last.current_ma is None:
            self.cards["current"].set("—", "")
        else:
            col = RED if last.current_ma < 0 else BLUE if last.current_ma > 0 else TEXT
            self.cards["current"].set(f"{fmt_num(last.current_ma / 1000.0, 2)} A", tr("poslední vzorek logu"), col)
        if last.rate_mw is None:
            self.cards["power"].set("—", "")
        else:
            self.cards["power"].set(f"{fmt_num(last.rate_mw / 1000.0, 2)} W", f"{fmt_num(last.rate_mw)} mW")

        if report.discharge_seconds > 0:
            self.cards["eta"].set_title(tr("Doba vybíjení"))
            self.cards["eta"].set(fmt_duration(report.discharge_seconds), tr("v načteném logu"))
        elif report.charge_seconds > 0:
            self.cards["eta"].set_title(tr("Doba nabíjení"))
            self.cards["eta"].set(fmt_duration(report.charge_seconds), tr("v načteném logu"))
        else:
            self.cards["eta"].set_title(tr("Doba vybíjení"))
            self.cards["eta"].set("—", tr("bez fáze vybíjení/nabíjení"))
        self.cards["percent"].set_title(tr("Spotřeba / nabití"))
        if loaded.health_percent is None:
            self.cards["health"].set("—", "")
        else:
            wear = max(0.0, 100.0 - loaded.health_percent)
            hcol = TEAL if loaded.health_percent >= 80 else AMBER if loaded.health_percent >= 60 else RED
            self.cards["health"].set(
                f"{fmt_num(loaded.health_percent, 1)} %",
                tr("opotřebení {wear} %", wear=fmt_num(wear, 1)),
                hcol,
            )

        if report.consumed_percent is not None:
            cap_sub = fmt_mwh(report.consumed_mwh) if report.consumed_mwh is not None else tr("spotřeba z logu")
            self.cards["percent"].set(
                f"−{fmt_num(report.consumed_percent, 1)} %",
                cap_sub,
                RED if report.consumed_percent >= 5 else AMBER,
            )
        elif report.gained_percent is not None:
            cap_sub = fmt_mwh(report.gained_mwh) if report.gained_mwh is not None else tr("nárůst z logu")
            self.cards["percent"].set(f"+{fmt_num(report.gained_percent, 1)} %", cap_sub, TEAL)
        elif last.percent is not None:
            self.cards["percent"].set(
                f"{fmt_num(last.percent, 1)} %",
                tr("{count} vzorků v logu", count=len(series)),
                percent_color,
            )
        else:
            self.cards["percent"].set("—", tr("{count} vzorků v logu", count=len(series)))

        err_color = RED if report.critical_count else AMBER if report.error_count else TEAL
        err_fg = RED_INK if err_color == RED else ("#2a2108" if err_color == AMBER else TEAL_INK)
        self.pill.configure(
            text=tr("Log · {count} chyb", count=report.error_count) if report.error_count else tr("Prohlížení logu"),
            bg=err_color,
            fg=err_fg,
        )

        self._draw_icon(self.icon, last.percent, last.charging, True)
        self._draw_icon(self.mini_icon, last.percent, last.charging, True)
        self.mini_percent.configure(
            text="—" if last.percent is None else f"{fmt_num(last.percent, 0)} %",
            fg=percent_color,
        )
        self.mini_state.configure(text=tr("Log"))
        self.mini_current.configure(
            text="" if last.current_ma is None else f"{fmt_num(last.current_ma / 1000.0, 2)} A"
        )
        self.mini_eta.configure(text=as_app_relative(loaded.path))
        if "note" in self.info_labels:
            self.info_labels["note"].configure(
                text=tr(
                    "Prohlížení {path}. Vybíjení {discharge}, chyb {errors}.",
                    path=as_app_relative(loaded.path),
                    discharge=fmt_duration(report.discharge_seconds),
                    errors=report.error_count,
                )
            )
        drop_text = "—"
        if report.consumed_percent is not None:
            drop_text = f"−{fmt_num(report.consumed_percent, 2)} %"
            if report.consumed_mwh is not None:
                drop_text += f" / {fmt_mwh(report.consumed_mwh)}"
        elif report.gained_percent is not None:
            drop_text = f"+{fmt_num(report.gained_percent, 2)} %"
            if report.gained_mwh is not None:
                drop_text += f" / {fmt_mwh(report.gained_mwh)}"
        for key, label in (
            ("maker", loaded.manufacturer),
            ("name", loaded.device_name),
            ("chem", loaded.chemistry),
            ("serial", loaded.serial),
            ("design", None if loaded.designed_mwh is None else fmt_mwh(loaded.designed_mwh)),
            ("full", None if loaded.full_charged_mwh is None else fmt_mwh(loaded.full_charged_mwh)),
            ("health", None if loaded.health_percent is None else f"{fmt_num(loaded.health_percent, 2)} %"),
            ("source", tr("log · {path}", path=as_app_relative(loaded.path))),
            ("drop", drop_text),
        ):
            if key in self.info_labels and label:
                self.info_labels[key].configure(text=label)
        self._fill_log_summary(report, series)
        self._redraw()

    def _fill_log_summary(self, report, series: list) -> None:
        if report.consumed_percent is not None:
            consumed_pct = f"−{fmt_num(report.consumed_percent, 2)} %"
        elif report.gained_percent is not None:
            consumed_pct = tr("+{value} % (nabití)", value=fmt_num(report.gained_percent, 2))
        else:
            consumed_pct = "—"

        if report.consumed_mwh is not None:
            consumed_cap = fmt_mwh(report.consumed_mwh)
        elif report.gained_mwh is not None:
            consumed_cap = tr("+{value} (nabití)", value=fmt_mwh(report.gained_mwh))
        else:
            consumed_cap = "—"

        if report.error_count:
            detail_lines = []
            for issue in report.issues[:12]:
                mark = "⚠" if issue.severity == "warning" else "✖" if issue.severity == "critical" else "·"
                detail_lines.append(f"{mark} {fmt_clock(issue.when)} — {issue.detail}")
            if len(report.issues) > 12:
                detail_lines.append(tr("… a dalších {count}", count=len(report.issues) - 12))
            errors_detail = "\n".join(detail_lines)
            errors_text = tr(
                "{count} ({critical} kritických)",
                count=report.error_count,
                critical=report.critical_count,
            )
        else:
            errors_detail = tr("Žádné anomálie v průběhu měření.")
            errors_text = "0"

        battery_name = " · ".join(
            part for part in (report.manufacturer, report.device_name, report.chemistry) if part
        ) or "—"

        values = {
            "battery": battery_name,
            "elapsed": fmt_duration(report.total_seconds),
            "discharge_time": fmt_duration(report.discharge_seconds) if report.discharge_seconds > 0 else "—",
            "charge_time": fmt_duration(report.charge_seconds) if report.charge_seconds > 0 else "—",
            "count": fmt_num(report.sample_count),
            "start_p": "—" if report.start_percent is None else f"{fmt_num(report.start_percent, 2)} %",
            "now_p": "—" if report.end_percent is None else f"{fmt_num(report.end_percent, 2)} %",
            "consumed_pct": consumed_pct,
            "consumed_cap": consumed_cap,
            "drawn": f"{fmt_num(report.drawn_wh, 3)} Wh",
            "stored": f"{fmt_num(report.stored_wh, 3)} Wh",
            "avg_p": "—" if report.avg_discharge_w is None else f"{fmt_num(report.avg_discharge_w, 2)} W",
            "peak_p": "—" if report.peak_discharge_w is None else f"{fmt_num(report.peak_discharge_w, 2)} W",
            "avg_rate": (
                "—"
                if report.avg_discharge_pct_per_hour is None
                else f"{fmt_num(report.avg_discharge_pct_per_hour, 1)} %/h"
            ),
            "projected": (
                "—"
                if report.projected_full_hours is None
                else tr("{hours} h (od 100 %)", hours=fmt_num(report.projected_full_hours, 2))
            ),
            "avg_v": "—" if report.avg_voltage_v is None else f"{fmt_num(report.avg_voltage_v, 3)} V",
            "span_v": (
                "—"
                if report.min_voltage_v is None or report.max_voltage_v is None
                else f"{fmt_num(report.min_voltage_v, 3)} – {fmt_num(report.max_voltage_v, 3)} V"
            ),
            "health": (
                "—"
                if report.health_percent is None
                else f"{fmt_num(report.health_percent, 1)} %"
            ),
            "errors": errors_text,
            "errors_detail": errors_detail,
            "cpu": self._cpu_summary(series),
            "gpu": self._gpu_summary(series),
        }
        for key, text in values.items():
            if key in self.summary_labels:
                color = TEXT
                if key == "errors" and report.critical_count:
                    color = RED
                elif key == "errors" and report.error_count:
                    color = AMBER
                self.summary_labels[key].configure(text=text, fg=color)

    def _show_measurement_report(self, report, loaded) -> None:
        path_text = as_app_relative(loaded.path)
        discharge = fmt_duration(report.discharge_seconds) if report.discharge_seconds > 0 else "—"
        charge = fmt_duration(report.charge_seconds) if report.charge_seconds > 0 else "—"
        lines = [
            tr("Soubor: {path}", path=path_text),
            tr(
                "Vzorků: {count} · celková doba {duration}",
                count=fmt_num(report.sample_count),
                duration=fmt_duration(report.total_seconds),
            ),
            "",
            tr("Doba vybíjení: {duration}", duration=discharge),
            tr("Doba nabíjení: {duration}", duration=charge),
            "",
        ]
        if report.consumed_percent is not None:
            lines.append(tr("Spotřebovaná kapacita: −{value} %", value=fmt_num(report.consumed_percent, 2)))
            if report.consumed_mwh is not None:
                lines.append(tr("Spotřebovaná energie: {value}", value=fmt_mwh(report.consumed_mwh)))
        elif report.gained_percent is not None:
            lines.append(tr("Nabitá kapacita: +{value} %", value=fmt_num(report.gained_percent, 2)))
            if report.gained_mwh is not None:
                lines.append(tr("Dodaná energie (kapacita): {value}", value=fmt_mwh(report.gained_mwh)))
        else:
            lines.append(tr("Spotřebovaná kapacita: —"))

        error_line = tr("Počet chyb / varování: {count}", count=report.error_count)
        if report.critical_count:
            error_line += tr(" (kritických {count})", count=report.critical_count)
        lines.extend(
            [
                tr("Odebraná energie (z výkonu): {value} Wh", value=fmt_num(report.drawn_wh, 3)),
                tr("Dodaná energie (z výkonu): {value} Wh", value=fmt_num(report.stored_wh, 3)),
                "",
                error_line,
            ]
        )
        if report.avg_discharge_pct_per_hour is not None:
            lines.append(
                tr("Průměrná rychlost vybíjení: {value} %/h", value=fmt_num(report.avg_discharge_pct_per_hour, 1))
            )
        if report.projected_full_hours is not None:
            lines.append(tr("Odhad plné výdrže: {value} h", value=fmt_num(report.projected_full_hours, 2)))
        if report.health_percent is not None:
            lines.append(tr("Kondice baterie: {value} %", value=fmt_num(report.health_percent, 1)))

        if report.issues:
            lines.append("")
            lines.append(tr("Nalezené problémy:"))
            for issue in report.issues[:15]:
                if issue.severity == "critical":
                    mark = tr("KRITICKÉ")
                elif issue.severity == "warning":
                    mark = tr("varování")
                else:
                    mark = tr("info")
                lines.append(f"  [{mark}] {fmt_clock(issue.when)} — {issue.detail}")
            if len(report.issues) > 15:
                lines.append(tr("  … a dalších {count} (viz Souhrn měření)", count=len(report.issues) - 15))
        else:
            lines.append("")
            lines.append(tr("V průběhu měření nebyly nalezeny anomálie baterie."))

        lines.append("")
        lines.append(tr("Podrobnosti jsou v záložce Souhrn měření."))
        messagebox.showinfo(tr("Analýza měření — {title}", title=APP_TITLE), "\n".join(lines))

    def _save_graph(self) -> None:
        ts = datetime.now()
        folder = graphs_dir()
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title=tr("Uložit všechny grafy"),
            defaultextension=".png",
            initialdir=str(folder),
            initialfile=f"grafy_{ts.strftime('%Y%m%d_%H%M%S')}.png",
            filetypes=[(tr("Obrázek PNG"), "*.png")],
        )
        if not path:
            return
        self._stamp_override = ts
        self._update_stamp()
        try:
            self._render_stacked_png(Path(path))
        except Exception as exc:
            messagebox.showerror(APP_NAME, tr("Grafy se nepodařilo uložit.\n{error}", error=exc))
        else:
            stamp = ts.strftime("%Y-%m-%d %H:%M:%S" if language() == "en" else "%d. %m. %Y %H:%M:%S")
            messagebox.showinfo(
                APP_NAME,
                tr(
                    "Všechny grafy jsou v jednom obrázku pod sebou,\ns časovým razítkem {stamp}:\n{path}",
                    stamp=stamp,
                    path=as_app_relative(Path(path)),
                ),
            )
        finally:
            self._stamp_override = None
            self._update_stamp()

    def _render_stacked_png(self, path: Path) -> None:
        series = self._visible(self._selected_samples())
        t_start, t_end = self._axis_range(series if series else self._selected_samples())
        gap = max(10.0, self.interval * 3)
        charge_badge = trend_badge(series)
        if self.ref_hours:
            charge_badge = f"{charge_badge}    {tr('šedá čára: {hours} h z 100 %', hours=fmt_num(self.ref_hours, 1))}".strip()
        specs = [
            (self.charge_graph.title, "percent", None, None, None, self.ref_hours, charge_badge),
            (self.power_graph.title, "power", None, None, None, None, ""),
            (tr("Vytížení CPU"), "load", lambda sample: sample.cpu, AMBER, "#3a2e12", None, load_badge(series, lambda sample: sample.cpu)),
        ]
        gpu_names = [name for name in self.gpu_graphs.keys() if name]
        if not gpu_names and series:
            for sample in reversed(series):
                if sample.gpus:
                    gpu_names = [name for name, _value in sample.gpus]
                    break
        if gpu_names:
            for index, name in enumerate(gpu_names):
                reader = gpu_reader(name)
                specs.append(
                    (
                        tr("Vytížení GPU · {name}", name=name),
                        "load",
                        reader,
                        GPU_COLORS[index % len(GPU_COLORS)],
                        GPU_FILLS[index % len(GPU_FILLS)],
                        None,
                        load_badge(series, reader),
                    )
                )
        else:
            specs.append((tr("Vytížení GPU"), "load", lambda _sample: None, BLUE, GPU_FILLS[0], None, ""))

        holder = tk.Toplevel(self.root)
        holder.overrideredirect(True)
        holder.configure(bg=BG)
        holder.attributes("-topmost", True)
        width = max(1000, self.graphs_wrap.winfo_width() or 1000)
        origin_x = max(0, self.root.winfo_rootx() + 16)
        origin_y = max(0, self.root.winfo_rooty() + 80)
        images = []
        try:
            stamp = tk.Label(
                holder,
                text=self.header_clock.cget("text") if hasattr(self, "header_clock") else "",
                bg=PANEL,
                fg=TEXT,
                font=("Segoe UI", 10),
                anchor="w",
                padx=10,
            )
            stamp.pack(fill="both", expand=True)
            images.append(self._shoot_export(holder, width, 36, origin_x, origin_y))
            stamp.destroy()
            for title, mode, reader, color, fill, ref_hours, badge in specs:
                graph = TimeGraph(
                    holder,
                    title,
                    mode,
                    color=color,
                    fill=fill,
                    value_fn=reader,
                    graph_height=200,
                )
                graph.pack(fill="both", expand=True)
                self._shoot_prepare(holder, width, 210, origin_x, origin_y)
                graph.set_series(series, ref_hours, gap, badge, t_start, t_end)
                holder.update()
                time.sleep(0.05)
                images.append(capture_widget_bgra(holder))
                graph.destroy()
            image_w, image_h, raw = stack_bgra(images, gap=8)
            write_png(path, image_w, image_h, raw)
        finally:
            holder.destroy()

    def _shoot_prepare(self, holder, width: int, height: int, origin_x: int, origin_y: int) -> None:
        holder.geometry(f"{width}x{height}+{origin_x}+{origin_y}")
        holder.update_idletasks()
        holder.update()
        time.sleep(0.05)
        holder.update()

    def _shoot_export(self, holder, width: int, height: int, origin_x: int, origin_y: int):
        self._shoot_prepare(holder, width, height, origin_x, origin_y)
        return capture_widget_bgra(holder)

    def _save_data(self) -> None:
        samples = self._selected_samples()
        if not samples:
            messagebox.showinfo(APP_NAME, tr("Zatím není co uložit. Počkejte na první vzorky."))
            return
        ts = datetime.now()
        folder = logs_dir()
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title=tr("Uložit data"),
            defaultextension=".csv",
            initialdir=str(folder),
            initialfile=f"data_{ts.strftime('%Y%m%d_%H%M%S')}.csv",
            filetypes=[(tr("Tabulka CSV"), "*.csv")],
        )
        if not path:
            return
        battery = None if self.view_mode == "log" else self._selected_battery()
        self._write_csv(Path(path), [self._csv_row(battery, sample) for sample in samples])
        messagebox.showinfo(
            APP_NAME,
            tr("Uloženo {count} vzorků:\n{path}", count=len(samples), path=as_app_relative(Path(path))),
        )

    def _toggle_pause(self) -> None:
        if self.pause.is_set():
            self.pause.clear()
            self.pause_btn.configure(text=tr("Pauza"))
        else:
            self.pause.set()
            self.pause_btn.configure(text=tr("Pokračovat"))

    def _clear(self) -> None:
        if self.view_mode == "log":
            messagebox.showinfo(APP_NAME, tr("V režimu prohlížení logu graf nemažte. Použijte Živá data."))
            return
        if self.selected_key:
            self.history[self.selected_key] = []
        self.started = time.time()
        self.charge_graph.reset_scale()
        self.power_graph.reset_scale()
        self.cpu_graph.reset_scale()
        for graph in self.gpu_graphs.values():
            graph.reset_scale()
        self._redraw()
        self._fill_summary(self._selected_battery(), self._selected_samples())

    def _open_logs(self) -> None:
        folder = logs_dir()
        os.startfile(folder)

    def _open_csv(self) -> None:
        if self.csv_path is None or not self.csv_path.exists():
            if not self.recording:
                messagebox.showinfo(
                    APP_NAME,
                    tr("Průběžný záznam je vypnutý. Zapněte Záznam, nebo uložte data tlačítkem Uložit data."),
                )
            else:
                messagebox.showinfo(APP_NAME, tr("Soubor vznikne s prvním vzorkem."))
            return
        os.startfile(self.csv_path)

    def _enter_mini(self) -> None:
        if self.mini:
            return
        self._normal_geometry = self.root.geometry()
        self.body.pack_forget()
        self.header.pack_forget()
        self.mini_frame.pack(fill="both", expand=True)
        self.root.geometry("560x78")
        self.root.attributes("-topmost", True)
        self.root.minsize(420, 70)
        self.mini = True

    def _leave_mini(self) -> None:
        if not self.mini:
            return
        self.mini_frame.pack_forget()
        self.header.pack(fill="x", padx=16, pady=(14, 6))
        self.body.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.root.attributes("-topmost", False)
        self.root.minsize(1020, 700)
        if self._normal_geometry:
            self.root.geometry(self._normal_geometry)
        self.mini = False

    def _start_worker(self) -> None:
        thread = threading.Thread(target=self._worker, name="battery-reader", daemon=True)
        thread.start()

    def _worker(self) -> None:
        try:
            sampler = LoadSampler()
        except Exception:
            sampler = None
        while not self.stop.is_set():
            started = time.perf_counter()
            if not self.pause.is_set():
                try:
                    snap = read_snapshot()
                    try:
                        load = sampler.read() if sampler is not None else None
                    except Exception:
                        load = None
                    with self.lock:
                        self.queue.append(("snap", (snap, load)))
                        if len(self.queue) > 5:
                            self.queue = self.queue[-5:]
                except Exception as exc:
                    with self.lock:
                        self.queue.append(("error", str(exc)))
            delay = self.interval - (time.perf_counter() - started)
            if delay > 0:
                self.stop.wait(delay)

    def _poll(self) -> None:
        if not self.alive:
            return
        batch = []
        with self.lock:
            batch = self.queue
            self.queue = []
        for kind, payload in batch:
            try:
                if kind == "error":
                    self.pill.configure(text=tr("Chyba čtení"), bg=RED, fg=RED_INK)
                    self.info_labels["note"].configure(text=payload)
                else:
                    self._ingest(payload)
            except Exception as exc:
                self.pill.configure(text=tr("Chyba zobrazení"), bg=RED, fg=RED_INK)
                self.info_labels["note"].configure(text=str(exc))
        self.root.after(200, self._poll)

    def _clock(self) -> None:
        if not self.alive:
            return
        self._update_phase_clocks()
        if self._stamp_override is None:
            self._update_stamp()
        now = time.time()
        growing = self.window_seconds is None or now >= self.started + self.window_seconds
        if (
            self.view_mode == "live"
            and self.graphs_visible
            and not self.mini
            and not self.pause.is_set()
            and growing
            and now - self._last_axis_redraw >= 1.0
        ):
            self._last_axis_redraw = now
            self._redraw()
        self.root.after(500, self._clock)

    def _ingest(self, payload) -> None:
        snap, load = payload if isinstance(payload, tuple) else (payload, None)
        self.latest = snap
        self.latest_load = load
        present = [b for b in snap.batteries if b.present and not b.error]
        usable = present or snap.batteries
        if not usable:
            self._show_empty(snap)
            return
        labels = []
        for battery in usable:
            title = battery.device_name or battery.manufacturer or tr("Baterie {index}", index=battery.index + 1)
            labels.append(f"{battery.index + 1}: {title}")
        keys = [b.key for b in usable]
        if self.view_mode != "log":
            if self.selected_key not in keys:
                self.selected_key = keys[0]
            if len(usable) > 1:
                if not self.battery_box.winfo_ismapped():
                    self.battery_box.pack(side="left", padx=(8, 0))
                self.battery_box.configure(values=labels)
                self.battery_box.current(keys.index(self.selected_key))
                self.battery_box.bind("<<ComboboxSelected>>", lambda _e: self._on_battery(keys))
            battery = usable[keys.index(self.selected_key)]
        else:
            battery = usable[0]
            self._live_key = battery.key
        sample = Sample(
            t=time.time(),
            percent=battery.percent,
            current_ma=battery.current_ma,
            voltage_mv=battery.voltage_mv,
            rate_mw=battery.rate_mw,
            remaining_mwh=battery.remaining_mwh,
            charging=battery.charging,
            discharging=battery.discharging,
            cpu=None if load is None else load.cpu,
            gpus=() if load is None else tuple(load.gpus),
        )
        series = self.history.setdefault(battery.key, [])
        series.append(sample)
        if len(series) > 100000:
            del series[:-100000]
        self._append_csv(battery, sample)
        if self.view_mode == "log":
            return
        self._paint(snap, battery, series)

    def _on_battery(self, keys: list) -> None:
        index = self.battery_box.current()
        if 0 <= index < len(keys):
            self.selected_key = keys[index]
            self._redraw()

    def _show_empty(self, snap: Snapshot) -> None:
        text = tr("Baterie není přítomna")
        self.pill.configure(text=text, bg=CARD, fg=TEXT)
        self._draw_icon(self.icon, None, False, False)
        for card in self.cards.values():
            card.set("—", "")
        note = " ".join(snap.errors) or tr("Windows nenašel ACPI baterii.")
        self.info_labels["note"].configure(text=note)
        self.info_labels["feed"].configure(text=tr("ze sítě") if snap.system.ac_online else tr("bez sítě"))
        self.info_labels["flags"].configure(text=flag_text(snap.system.battery_flag))

    def _paint(self, snap: Snapshot, battery: Battery, series: list) -> None:
        code = power_state_code(battery, snap.system)
        state = power_state_text(battery, snap.system)
        color = state_color(code)
        ink = RED_INK if color == RED else TEAL_INK if color == TEAL else "#102033"
        self.pill.configure(text=state, bg=color, fg=ink if color != AMBER else "#2a2108")
        self._track_phase(battery.charging, battery.discharging)
        self._update_phase_clocks()
        self._draw_icon(self.icon, battery.percent, battery.charging, battery.present)
        self._draw_icon(self.mini_icon, battery.percent, battery.charging, battery.present)

        percent_color = TEAL if battery.percent is None or battery.percent >= 50 else AMBER if battery.percent >= 20 else RED
        self.cards["percent"].set_title(tr("Nabití"))
        self.cards["eta"].set_title(tr("Zbývající čas"))
        self.cards["percent"].set(
            "—" if battery.percent is None else f"{fmt_num(battery.percent, 1)} %",
            tr("ze zbývající a plné kapacity") if battery.full_charged_mwh else tr("hlášení Windows"),
            percent_color,
        )
        if battery.voltage_mv:
            self.cards["voltage"].set(f"{fmt_num(battery.voltage_mv / 1000.0, 2)} V", f"{fmt_num(battery.voltage_mv)} mV")
        else:
            self.cards["voltage"].set("—", tr("napětí nedostupné"))

        if battery.current_ma is None:
            self.cards["current"].set("—", tr("nelze dopočítat"))
        else:
            amps = battery.current_ma / 1000.0
            if battery.discharging:
                sub = tr("odběr z baterie")
                col = RED
            elif battery.charging:
                sub = tr("nabíjecí proud")
                col = BLUE
            else:
                sub = tr("baterie právě nepřenáší proud")
                col = TEXT
            self.cards["current"].set(f"{fmt_num(amps, 2)} A", sub, col)

        if battery.rate_mw is None:
            self.cards["power"].set("—", "")
        else:
            self.cards["power"].set(f"{fmt_num(battery.rate_mw / 1000.0, 2)} W", f"{fmt_num(battery.rate_mw)} mW")

        seconds, why = eta_seconds(battery)
        self.cards["eta"].set(fmt_duration(seconds) if seconds else "—", why)

        health = battery.health_percent
        if health is None:
            self.cards["health"].set("—", tr("návrhová kapacita chybí"))
        else:
            wear = battery.wear_percent or 0
            hcol = TEAL if health >= 80 else AMBER if health >= 60 else RED
            self.cards["health"].set(
                f"{fmt_num(health, 1)} %",
                tr("opotřebení {wear} %", wear=fmt_num(wear, 1)),
                hcol,
            )

        self.mini_percent.configure(
            text="—" if battery.percent is None else f"{fmt_num(battery.percent, 0)} %",
            fg=percent_color,
        )
        self.mini_state.configure(text=state)
        if battery.current_ma is None:
            self.mini_current.configure(text="")
        else:
            self.mini_current.configure(text=f"{fmt_num(battery.current_ma / 1000.0, 2)} A")
        self.mini_eta.configure(text="" if not seconds else fmt_duration(seconds))

        self._fill_info(snap, battery, series)
        self._fill_summary(battery, series)
        self._redraw()

    def _axis_range(self, series: list) -> tuple:
        """Počátek = start měření, konec = konec měření (log) / teď (živé)."""
        if self.view_mode == "log":
            source = []
            if self.loaded_log is not None and self.loaded_log.samples:
                source = self.loaded_log.samples
            elif series:
                source = series
            if not source:
                now = time.time()
                return now, now + 30.0
            return source[0].t, max(source[-1].t, source[0].t + 1.0)

        t_start = self.started
        if self.pause.is_set() and series:
            t_now = series[-1].t
        else:
            t_now = time.time()
            if series:
                t_now = max(t_now, series[-1].t)
        if self.window_seconds is None:
            t_end = max(t_now, t_start + 30.0)
        else:
            t_end = max(t_now, t_start + float(self.window_seconds))
        return t_start, t_end

    def _visible(self, series: list) -> list:
        """Celý průběh od začátku do konce měření."""
        if not series:
            return []
        if self.view_mode == "log":
            return list(series)
        t_start, _t_end = self._axis_range(series)
        return [sample for sample in series if sample.t >= t_start - 0.5]

    def _redraw(self) -> None:
        full = self._selected_samples()
        series = self._visible(full)
        t_start, t_end = self._axis_range(full if full else series)
        badge = trend_badge(series)
        if self.ref_hours:
            ref = tr("šedá čára: {hours} h z 100 %", hours=fmt_num(self.ref_hours, 1))
            badge = f"{badge}    {ref}".strip()
        if series:
            span = max(series[-1].t - series[0].t, 1.0)
            gap = max(10.0, self.interval * 3, span / max(len(series), 1) * 5)
        else:
            gap = max(10.0, self.interval * 3)
        names = []
        for sample in reversed(series):
            if sample.gpus:
                names = [name for name, _value in sample.gpus]
                break
        self._sync_gpu_graphs(names)
        self.charge_graph.set_series(series, self.ref_hours, gap, badge, t_start, t_end)
        self.power_graph.set_series(series, None, gap, "", t_start, t_end)
        self.cpu_graph.set_series(
            series, None, gap, load_badge(series, lambda sample: sample.cpu), t_start, t_end
        )
        for name, graph in self.gpu_graphs.items():
            if not name:
                graph.set_series(series, None, gap, "", t_start, t_end)
            else:
                graph.set_series(series, None, gap, load_badge(series, graph.value_fn), t_start, t_end)

    def _selected_samples(self) -> list:
        if self.view_mode == "log" and self.loaded_log is not None:
            return list(self.loaded_log.samples)
        if not self.selected_key:
            return []
        return self.history.get(self.selected_key, [])

    def _selected_battery(self) -> Optional[Battery]:
        if self.view_mode == "log":
            return None
        if not self.latest or not self.selected_key:
            return None
        for battery in self.latest.batteries:
            if battery.key == self.selected_key:
                return battery
        return None

    def _fill_info(self, snap: Snapshot, battery: Battery, series: list) -> None:
        system = snap.system
        seconds, why = eta_seconds(battery)
        drop = self._capacity_drop(series)
        rate = self._instant_rate(battery)
        values = {
            "state": power_state_text(battery, system),
            "feed": self._feed_text(battery, system),
            "percent": "—" if battery.percent is None else f"{fmt_num(battery.percent, 2)} %",
            "win_percent": "—" if system.percent is None else f"{system.percent} %",
            "voltage": "—" if not battery.voltage_mv else f"{fmt_num(battery.voltage_mv / 1000.0, 3)} V ({fmt_num(battery.voltage_mv)} mV)",
            "current": self._current_detail(battery),
            "power": "—" if battery.rate_mw is None else f"{fmt_num(battery.rate_mw / 1000.0, 3)} W ({fmt_num(battery.rate_mw)} mW)",
            "rate": rate,
            "remain": fmt_mwh(battery.remaining_mwh),
            "full": fmt_mwh(battery.full_charged_mwh),
            "design": fmt_mwh(battery.designed_mwh),
            "health": "—"
            if battery.health_percent is None
            else tr("{value} %  (plná / návrhová kapacita)", value=fmt_num(battery.health_percent, 2)),
            "wear": "—" if battery.wear_percent is None else f"{fmt_num(battery.wear_percent, 2)} %",
            "drop": drop,
            "chem": battery.chemistry or tr("neuvedeno"),
            "tech": battery.technology or tr("neuvedeno"),
            "cycles": self._cycles(battery),
            "temp": tr("neuvedeno") if battery.temperature_c is None else f"{fmt_num(battery.temperature_c, 1)} °C",
            "maker": battery.manufacturer or tr("neuvedeno"),
            "name": battery.device_name or tr("neuvedeno"),
            "serial": battery.serial or tr("neuvedeno"),
            "uid": battery.unique_id or tr("neuvedeno"),
            "made": battery.manufacture_date or tr("neuvedeno"),
            "eta": "—" if not seconds else f"{fmt_duration(seconds)} ({why})",
            "alert1": fmt_mwh(battery.alert1),
            "alert2": fmt_mwh(battery.alert2),
            "bias": "0" if battery.critical_bias == 0 else fmt_mwh(battery.critical_bias),
            "gran": self._granularity(battery),
            "caps": ", ".join(battery.capabilities) if battery.capabilities else tr("neuvedeno"),
            "tag": "—" if battery.tag is None else str(battery.tag),
            "flags": flag_text(system.battery_flag),
            "saver": tr("zapnuto") if system.saver else tr("vypnuto") if system.saver is not None else "—",
            "idle": "—" if system.idleness is None else f"{system.idleness} %",
            "cool": cooling_text(system.cooling_mode),
            "life": fmt_duration(system.life_seconds),
            "full_life": fmt_duration(system.full_life_seconds),
            "source": battery.source,
            "note": battery.error or (tr("Kapacita je v relativních jednotkách, ne v mWh.") if battery.relative_capacity else tr("Řadič teplotu ani datum výroby nemusí předávat.")),
            "path": battery.device_path or "—",
        }
        for key, text in values.items():
            self.info_labels[key].configure(text=text)

    def _fill_summary(self, battery: Optional[Battery], series: list) -> None:
        report = analyze_measurement(series, battery)
        if report.consumed_percent is not None:
            consumed_pct = f"−{fmt_num(report.consumed_percent, 2)} %"
        elif report.gained_percent is not None:
            consumed_pct = tr("+{value} % (nabití)", value=fmt_num(report.gained_percent, 2))
        else:
            consumed_pct = "—"
        if report.consumed_mwh is not None:
            consumed_cap = fmt_mwh(report.consumed_mwh)
        elif report.gained_mwh is not None:
            consumed_cap = tr("+{value} (nabití)", value=fmt_mwh(report.gained_mwh))
        else:
            consumed_cap = "—"

        battery_name = "—"
        if battery is not None:
            battery_name = " · ".join(
                part for part in (battery.manufacturer, battery.device_name, battery.chemistry) if part
            ) or "—"

        if report.error_count:
            detail_lines = [
                f"{'⚠' if issue.severity == 'warning' else '✖' if issue.severity == 'critical' else '·'} "
                f"{fmt_clock(issue.when)} — {issue.detail}"
                for issue in report.issues[:8]
            ]
            errors_detail = "\n".join(detail_lines)
            errors_text = f"{report.error_count}"
        else:
            errors_detail = "—"
            errors_text = "0"

        values = {
            "battery": battery_name,
            "elapsed": fmt_duration(report.total_seconds if series else time.time() - self.started),
            "discharge_time": fmt_duration(report.discharge_seconds) if report.discharge_seconds > 0 else "—",
            "charge_time": fmt_duration(report.charge_seconds) if report.charge_seconds > 0 else "—",
            "count": fmt_num(len(series)),
            "start_p": "—" if report.start_percent is None else f"{fmt_num(report.start_percent, 2)} %",
            "now_p": "—" if report.end_percent is None else f"{fmt_num(report.end_percent, 2)} %",
            "consumed_pct": consumed_pct,
            "consumed_cap": consumed_cap,
            "drawn": f"{fmt_num(report.drawn_wh, 3)} Wh",
            "stored": f"{fmt_num(report.stored_wh, 3)} Wh",
            "avg_p": "—" if report.avg_discharge_w is None else f"{fmt_num(report.avg_discharge_w, 2)} W",
            "peak_p": "—" if report.peak_discharge_w is None else f"{fmt_num(report.peak_discharge_w, 2)} W",
            "avg_rate": (
                "—"
                if report.avg_discharge_pct_per_hour is None
                else f"{fmt_num(report.avg_discharge_pct_per_hour, 1)} %/h"
            ),
            "projected": (
                "—"
                if report.projected_full_hours is None
                else tr("{hours} h (od 100 %)", hours=fmt_num(report.projected_full_hours, 2))
            ),
            "avg_v": "—" if report.avg_voltage_v is None else f"{fmt_num(report.avg_voltage_v, 3)} V",
            "span_v": (
                "—"
                if report.min_voltage_v is None or report.max_voltage_v is None
                else f"{fmt_num(report.min_voltage_v, 3)} – {fmt_num(report.max_voltage_v, 3)} V"
            ),
            "health": "—",
            "errors": errors_text,
            "errors_detail": errors_detail,
            "cpu": self._cpu_summary(series),
            "gpu": self._gpu_summary(series),
        }
        if battery and battery.health_percent is not None:
            values["health"] = f"{fmt_num(battery.health_percent, 1)} % / {fmt_num(battery.wear_percent, 1)} %"
        for key, text in values.items():
            if key in self.summary_labels:
                self.summary_labels[key].configure(text=text, fg=TEXT)

    def _gpu_brief(self, sample: Sample) -> str:
        if not sample.gpus:
            return "—"
        return " · ".join(f"{name} {fmt_num(value, 0)} %" for name, value in sample.gpus)

    def _gpu_csv_cells(self, sample: Sample) -> list:
        cells = []
        gpus = list(sample.gpus)
        for index in range(3):
            if index < len(gpus):
                cells.append(gpus[index][0])
                cells.append(f"{gpus[index][1]:.1f}")
            else:
                cells.extend(["", ""])
        return cells

    def _cpu_summary(self, series: list) -> str:
        values = [sample.cpu for sample in series if sample.cpu is not None]
        if not values:
            return "—"
        return tr(
            "{value} %  (průměr {avg} %)",
            value=fmt_num(values[-1], 1),
            avg=fmt_num(_mean(values), 1),
        )

    def _gpu_summary(self, series: list) -> str:
        if not series:
            return "—"
        names = []
        for sample in reversed(series):
            if sample.gpus:
                names = [name for name, _value in sample.gpus]
                break
        if not names:
            return "—"
        parts = []
        for name in names:
            values = []
            for sample in series:
                for title, value in sample.gpus:
                    if title == name and value is not None:
                        values.append(value)
            if values:
                parts.append(
                    tr(
                        "{name}: {value} % (průměr {avg} %)",
                        name=name,
                        value=fmt_num(values[-1], 1),
                        avg=fmt_num(_mean(values), 1),
                    )
                )
        return " · ".join(parts) if parts else "—"

    def _feed_text(self, battery: Battery, system: SystemPower) -> str:
        parts = []
        if battery.on_line or system.ac_online:
            parts.append(tr("adaptér připojen"))
        else:
            parts.append(tr("běží z baterie"))
        if battery.power_state is not None:
            flags = []
            if battery.on_line:
                flags.append(tr("on-line"))
            if battery.discharging:
                flags.append(tr("discharging"))
            if battery.charging:
                flags.append(tr("charging"))
            if battery.critical:
                flags.append(tr("critical"))
            parts.append(f"ACPI 0x{battery.power_state:08X} ({', '.join(flags) or tr('bez příznaku')})")
        return " · ".join(parts)

    def _current_detail(self, battery: Battery) -> str:
        if battery.current_ma is None or battery.rate_mw is None or not battery.voltage_mv:
            return tr("nelze dopočítat (chybí výkon nebo napětí)")
        direction = tr("odběr") if battery.current_ma < 0 else tr("nabíjení") if battery.current_ma > 0 else tr("bez proudu")
        return tr(
            "{ma} mA ({amps} A), {direction}. Výpočet {mw} mW / {mv} mV.",
            ma=fmt_num(battery.current_ma, 1),
            amps=fmt_num(battery.current_ma / 1000.0, 3),
            direction=direction,
            mw=fmt_num(battery.rate_mw),
            mv=fmt_num(battery.voltage_mv),
        )

    def _instant_rate(self, battery: Optional[Battery]) -> str:
        if battery is None or battery.rate_mw is None or not battery.full_charged_mwh:
            return "—"
        per_hour = battery.rate_mw / battery.full_charged_mwh * 100.0
        return tr("{rate} %/h při aktuálním výkonu", rate=fmt_num(per_hour, 2))

    def _cycles(self, battery: Battery) -> str:
        if battery.cycle_count is None:
            return tr("neuvedeno")
        if battery.cycle_count == 0:
            return tr("0 (řadič počet cyklů často nehlásí)")
        return str(battery.cycle_count)

    def _granularity(self, battery: Battery) -> str:
        if not battery.granularity:
            return tr("neuvedeno")
        parts = []
        for gran, cap in battery.granularity:
            parts.append(tr("krok {step} mWh do {cap} mWh", step=fmt_num(gran), cap=fmt_num(cap)))
        return "; ".join(parts)

    def _capacity_drop(self, series: list) -> str:
        values = [s.remaining_mwh for s in series if s.remaining_mwh is not None]
        if len(values) < 2:
            return tr("zatím bez změny")
        delta = values[-1] - values[0]
        if delta == 0:
            return "0 mWh"
        direction = tr("úbytek") if delta < 0 else tr("přírůstek")
        return tr("{direction} {energy}", direction=direction, energy=fmt_mwh(abs(delta)))

    def _energy(self, series: list) -> tuple:
        drawn = 0.0
        stored = 0.0
        for prev, cur in zip(series, series[1:]):
            dt = cur.t - prev.t
            if not (0 < dt < 60) or cur.rate_mw is None:
                continue
            wh = abs(cur.rate_mw) / 1000.0 * dt / 3600.0
            if cur.discharging or cur.rate_mw < 0:
                drawn += wh
            elif cur.charging or cur.rate_mw > 0:
                stored += wh
        return drawn, stored

    def _avg_power(self, series: list) -> str:
        values = [abs(s.rate_mw) for s in series if s.rate_mw is not None and s.rate_mw < 0]
        if not values:
            return "—"
        return f"{fmt_num(_mean(values) / 1000.0, 2)} W"

    def _push_row(self, sample: Sample) -> None:
        return

    def _csv_row(self, battery: Optional[Battery], sample: Sample) -> list:
        if sample.charging:
            state = "nabijeni"
        elif sample.discharging:
            state = "vybijeni"
        else:
            state = "sit"
        return [
            datetime.fromtimestamp(sample.t).strftime("%Y-%m-%d %H:%M:%S"),
            "" if battery is None else battery.index + 1,
            "" if battery is None else (battery.device_name or ""),
            "" if battery is None else (battery.manufacturer or ""),
            state,
            "" if sample.percent is None else f"{sample.percent:.2f}",
            sample.voltage_mv or "",
            "" if sample.current_ma is None else f"{sample.current_ma:.1f}",
            "" if sample.rate_mw is None else sample.rate_mw,
            sample.remaining_mwh or "",
            "" if battery is None else (battery.full_charged_mwh or ""),
            "" if battery is None else (battery.designed_mwh or ""),
            "" if battery is None or battery.health_percent is None else f"{battery.health_percent:.2f}",
            "" if battery is None or battery.temperature_c is None else f"{battery.temperature_c:.1f}",
            "" if battery is None or battery.cycle_count is None else battery.cycle_count,
            "" if battery is None else (battery.chemistry or ""),
            "" if battery is None else (battery.serial or ""),
            "" if sample.cpu is None else f"{sample.cpu:.1f}",
            *self._gpu_csv_cells(sample),
        ]

    def _write_csv(self, path: Path, rows: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(CSV_HEADER)
            writer.writerows(rows)

    def _append_csv(self, battery: Battery, sample: Sample) -> None:
        if not self.recording or self.csv_path is None:
            return
        logs_dir()
        write_header = not self.csv_path.exists() or not self._csv_ready
        with self.csv_path.open("a", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle, delimiter=";")
            if write_header:
                writer.writerow(CSV_HEADER)
                self._csv_ready = True
            writer.writerow(self._csv_row(battery, sample))
            handle.flush()
            os.fsync(handle.fileno())

    def _draw_icon(self, canvas: tk.Canvas, percent: Optional[float], charging: bool, present: bool) -> None:
        canvas.delete("all")
        canvas.create_rectangle(1, 4, 30, 18, outline=MUTED, width=1)
        canvas.create_rectangle(30, 8, 34, 14, outline=MUTED, width=1)
        if not present or percent is None:
            return
        width = 26 * max(0.0, min(100.0, percent)) / 100.0
        if percent < 20 and not charging:
            color = RED
        elif percent < 50 and not charging:
            color = AMBER
        elif charging:
            color = BLUE
        else:
            color = TEAL
        if width >= 1:
            canvas.create_rectangle(3, 6, 3 + width, 16, outline="", fill=color)

    def _offer_update(self, info: dict) -> None:
        if not self.alive:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title(tr("Dostupná aktualizace"))
        dialog.configure(bg=PANEL)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.geometry("540x380")
        tk.Label(
            dialog,
            text=tr(
                "Je k dispozici verze {version}. Nyní používáte {current}.",
                version=info["version"],
                current=VERSION,
            ),
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 11),
            wraplength=500,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(16, 8))
        notes = (info.get("notes") or "").strip()
        if notes:
            tk.Label(dialog, text=tr("Poznámky k verzi"), bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=16)
            box = tk.Text(
                dialog,
                height=8,
                bg=CARD,
                fg=TEXT,
                insertbackground=TEXT,
                relief="flat",
                wrap="word",
                font=("Segoe UI", 9),
                padx=8,
                pady=6,
            )
            box.pack(fill="both", expand=True, padx=16, pady=(4, 8))
            box.insert("1.0", notes)
            box.configure(state="disabled")
        status = tk.Label(dialog, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        status.pack(fill="x", padx=16)
        actions = tk.Frame(dialog, bg=PANEL)
        actions.pack(fill="x", padx=16, pady=12)
        update_btn = self._button(actions, tr("Aktualizovat"), lambda: None)
        later_btn = self._button(actions, tr("Později"), dialog.destroy)
        skip_btn = self._button(actions, tr("Přeskočit tuto verzi"), lambda: None)
        update_btn.pack(side="left")
        later_btn.pack(side="left", padx=8)
        skip_btn.pack(side="left")
        buttons = (update_btn, later_btn, skip_btn)

        def skip() -> None:
            skip_version(info["version"])
            dialog.destroy()

        def fail(exc: Exception) -> None:
            for button in buttons:
                button.configure(state="normal")
            status.configure(text="")
            messagebox.showerror(APP_NAME, tr("Aktualizace se nepodařila.\n{error}", error=exc), parent=dialog)

        def finish(script) -> None:
            status.configure(text=tr("Nová verze se nainstaluje po zavření aplikace."))
            dialog.update()
            os.startfile(script)
            self.close()

        def start() -> None:
            for button in buttons:
                button.configure(state="disabled")
            status.configure(text=tr("Stahuji aktualizaci {version}…", version=info["version"]))

            def work() -> None:
                try:
                    source = download_and_stage(info)
                    script = launch_apply(source)
                except Exception as exc:
                    self.root.after(0, lambda: fail(exc))
                    return
                self.root.after(0, lambda: finish(script))

            threading.Thread(target=work, name="update-download", daemon=True).start()

        update_btn.configure(command=start)
        skip_btn.configure(command=skip)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    def close(self) -> None:
        self.alive = False
        self.stop.set()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    MonitorApp().run()


if __name__ == "__main__":
    main()
