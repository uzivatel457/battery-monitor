"""Vytížení CPU (GetSystemTimes) a GPU (čitače Windows PDH + názvy z DXGI)."""

from __future__ import annotations

import ctypes
import re
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional


PDH_FMT_DOUBLE = 0x00000200
PDH_MORE_DATA = 0x800007D2
SKIP_NAME_PARTS = (
    "basic render",
    "parsec",
    "virtual display",
    "remote display",
    "spacedesk",
    "idd sample",
    "indirect display",
)
_LUID_ENGINE = re.compile(
    r"luid_(0x[0-9A-Fa-f]+)_(0x[0-9A-Fa-f]+)_phys_\d+_eng_\d+_engtype_(.*)$",
    re.IGNORECASE,
)


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class DXGI_ADAPTER_DESC(ctypes.Structure):
    _fields_ = [
        ("Description", wintypes.WCHAR * 128),
        ("VendorId", wintypes.UINT),
        ("DeviceId", wintypes.UINT),
        ("SubSysId", wintypes.UINT),
        ("Revision", wintypes.UINT),
        ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t),
        ("AdapterLuid", LUID),
    ]


class PDH_FMT_COUNTERVALUE(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", PDH_FMT_COUNTERVALUE)]


def _guid(text: str) -> GUID:
    parsed = uuid.UUID(text)
    item = GUID()
    item.Data1, item.Data2, item.Data3 = parsed.fields[0], parsed.fields[1], parsed.fields[2]
    item.Data4 = (wintypes.BYTE * 8).from_buffer_copy(parsed.bytes[8:])
    return item


def _filetime(value: FILETIME) -> int:
    return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)


def _keep_gpu(name: str) -> bool:
    lowered = name.lower()
    return not any(part in lowered for part in SKIP_NAME_PARTS)


@dataclass
class LoadReading:
    cpu: Optional[float]
    gpus: tuple


class LoadSampler:
    def __init__(self) -> None:
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._pdh = ctypes.WinDLL("pdh", use_last_error=True)
        for name in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData", "PdhGetFormattedCounterArrayW"):
            getattr(self._pdh, name).restype = ctypes.c_uint32
        self._names = {}
        self._query = wintypes.HANDLE()
        self._counter = wintypes.HANDLE()
        self._cpu_prev = self._cpu_times()
        self._pdh_ok = False
        try:
            self._names = self._adapter_names()
        except Exception:
            self._names = {}
        try:
            self._open_gpu_query()
            self._pdh_ok = True
        except Exception:
            self._pdh_ok = False

    def read(self) -> LoadReading:
        cpu = self._cpu_percent()
        gpus = ()
        if self._pdh_ok:
            try:
                gpus = self._gpu_loads()
            except Exception:
                gpus = ()
        return LoadReading(cpu=cpu, gpus=gpus)

    def _cpu_times(self):
        idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
        ok = self._kernel.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
        if not ok:
            return None
        return _filetime(idle), _filetime(kernel), _filetime(user)

    def _cpu_percent(self) -> float | None:
        now = self._cpu_times()
        prev = self._cpu_prev
        self._cpu_prev = now
        if not now or not prev:
            return None
        idle = now[0] - prev[0]
        kernel = now[1] - prev[1]
        user = now[2] - prev[2]
        total = kernel + user
        if total <= 0:
            return None
        busy = total - idle
        return max(0.0, min(100.0, 100.0 * busy / total))

    def _open_gpu_query(self) -> None:
        status = self._pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query))
        if status != 0:
            raise OSError("PdhOpenQueryW selhalo")
        status = self._pdh.PdhAddEnglishCounterW(
            self._query,
            "\\GPU Engine(*)\\Utilization Percentage",
            0,
            ctypes.byref(self._counter),
        )
        if status != 0:
            raise OSError("Čitač GPU Engine není dostupný")
        self._pdh.PdhCollectQueryData(self._query)

    def _gpu_loads(self) -> tuple:
        status = self._pdh.PdhCollectQueryData(self._query)
        if status != 0:
            return ()
        size = wintypes.DWORD(0)
        count = wintypes.DWORD(0)
        status = self._pdh.PdhGetFormattedCounterArrayW(
            self._counter,
            PDH_FMT_DOUBLE,
            ctypes.byref(size),
            ctypes.byref(count),
            None,
        )
        if status not in (0, PDH_MORE_DATA) or size.value <= 0:
            return ()
        buffer = ctypes.create_string_buffer(size.value)
        status = self._pdh.PdhGetFormattedCounterArrayW(
            self._counter,
            PDH_FMT_DOUBLE,
            ctypes.byref(size),
            ctypes.byref(count),
            buffer,
        )
        if status != 0 or count.value <= 0:
            return ()
        items = ctypes.cast(buffer, ctypes.POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
        per_luid = {}
        for index in range(count.value):
            code = int(items[index].FmtValue.CStatus)
            if code not in (0, 1):
                continue
            name = items[index].szName or ""
            match = _LUID_ENGINE.search(name)
            if not match:
                continue
            high = int(match.group(1), 16)
            low = int(match.group(2), 16)
            engine = match.group(3) or "other"
            value = float(items[index].FmtValue.doubleValue)
            if value < 0:
                continue
            bucket = per_luid.setdefault((high, low), {})
            bucket[engine] = bucket.get(engine, 0.0) + value
        ranked = []
        for luid, engines in per_luid.items():
            if not engines:
                continue
            percent = max(0.0, min(100.0, max(engines.values())))
            label, vram = self._names.get(luid, (None, 0))
            if label and not _keep_gpu(label):
                continue
            if label is None:
                label = f"GPU {luid[1]:X}"
            ranked.append((vram, label, percent, luid))
        if not ranked and per_luid:
            for luid, engines in per_luid.items():
                percent = max(0.0, min(100.0, max(engines.values()))) if engines else 0.0
                label, vram = self._names.get(luid, (f"GPU {luid[1]:X}", 0))
                ranked.append((vram, label, percent, luid))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        seen = {}
        ordered = []
        for _vram, label, percent, _luid in ranked:
            title = label
            if title in seen:
                seen[title] += 1
                title = f"{label} ({seen[title]})"
            else:
                seen[title] = 1
            ordered.append((title, percent))
        return tuple(ordered)

    def _adapter_names(self) -> dict:
        ole32 = ctypes.WinDLL("ole32")
        dxgi = ctypes.WinDLL("dxgi")
        ole32.CoInitializeEx(None, 2)
        factory = ctypes.c_void_p()
        iid = _guid("770aae78-f26f-4dba-a829-253c83d1b387")
        hr = dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory))
        if hr != 0 or not factory:
            return {}
        names = {}
        try:
            vtable = ctypes.cast(factory, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            enum_adapters = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.POINTER(ctypes.c_void_p),
            )(vtable[7])
            release_factory = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
            index = 0
            while index < 16:
                adapter = ctypes.c_void_p()
                result = enum_adapters(factory, index, ctypes.byref(adapter))
                if result != 0 or not adapter:
                    break
                adapter_vt = ctypes.cast(adapter, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                get_desc = ctypes.WINFUNCTYPE(
                    ctypes.c_long,
                    ctypes.c_void_p,
                    ctypes.POINTER(DXGI_ADAPTER_DESC),
                )(adapter_vt[8])
                release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(adapter_vt[2])
                desc = DXGI_ADAPTER_DESC()
                if get_desc(adapter, ctypes.byref(desc)) == 0:
                    luid = (int(desc.AdapterLuid.HighPart) & 0xFFFFFFFF, int(desc.AdapterLuid.LowPart))
                    text = desc.Description.strip() or f"GPU {index + 1}"
                    names[luid] = (text, int(desc.DedicatedVideoMemory))
                release(adapter)
                index += 1
            release_factory(factory)
        finally:
            ole32.CoUninitialize()
        return names
