"""Čtení stavu baterie přes Windows ACPI (SetupAPI + IOCTL) a systémové API."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Optional

from i18n import tr


FILE_DEVICE_BATTERY = 0x00000029
METHOD_BUFFERED = 0
FILE_READ_ACCESS = 0x0001

def _ctl_code(device_type: int, function: int, method: int, access: int) -> int:
    return (device_type << 16) | (access << 14) | (function << 2) | method


IOCTL_BATTERY_QUERY_TAG = _ctl_code(FILE_DEVICE_BATTERY, 0x10, METHOD_BUFFERED, FILE_READ_ACCESS)
IOCTL_BATTERY_QUERY_INFORMATION = _ctl_code(FILE_DEVICE_BATTERY, 0x11, METHOD_BUFFERED, FILE_READ_ACCESS)
IOCTL_BATTERY_QUERY_STATUS = _ctl_code(FILE_DEVICE_BATTERY, 0x13, METHOD_BUFFERED, FILE_READ_ACCESS)

BatteryInformation = 0
BatteryGranularityInformation = 1
BatteryTemperature = 2
BatteryEstimatedTime = 3
BatteryDeviceName = 4
BatteryManufactureDate = 5
BatteryManufactureName = 6
BatteryUniqueID = 7
BatterySerialNumber = 8

BATTERY_UNKNOWN_CAPACITY = 0xFFFFFFFF
BATTERY_UNKNOWN_VOLTAGE = 0xFFFFFFFF
BATTERY_UNKNOWN_RATE = 0x80000000
BATTERY_UNKNOWN_TIME = 0xFFFFFFFF

BATTERY_POWER_ON_LINE = 0x00000001
BATTERY_DISCHARGING = 0x00000002
BATTERY_CHARGING = 0x00000004
BATTERY_CRITICAL = 0x00000008

BATTERY_SET_CHARGE_SUPPORTED = 0x00000001
BATTERY_SET_DISCHARGE_SUPPORTED = 0x00000002
BATTERY_IS_SHORT_TERM = 0x20000000
BATTERY_CAPACITY_RELATIVE = 0x40000000
BATTERY_SYSTEM_BATTERY = 0x80000000

SystemBatteryState = 5
SystemPowerInformation = 12

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

ERROR_NO_MORE_ITEMS = 259
ERROR_INSUFFICIENT_BUFFER = 122

GUID_DEVINTERFACE_BATTERY = (
    0x72631E54,
    0x78A4,
    0x11D0,
    (0xBC, 0xF7, 0x00, 0xAA, 0x00, 0xB7, 0xB3, 0x2A),
)

CHEM_NAMES = {
    "LION": "Li-ion",
    "LI-I": "Li-ion",
    "LIION": "Li-ion",
    "LIPO": "Li-polymer",
    "LI-P": "Li-polymer",
    "LIP": "Li-polymer",
    "NIMH": "NiMH",
    "NICD": "NiCd",
    "PBAC": "Olověný akumulátor",  # přeloží se v _chemistry_text
    "RAM": "RAM",
}


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_size_t),
    ]


class BATTERY_QUERY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BatteryTag", wintypes.ULONG),
        ("InformationLevel", ctypes.c_int),
        ("AtRate", wintypes.LONG),
    ]


class BATTERY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Capabilities", wintypes.ULONG),
        ("Technology", wintypes.BYTE),
        ("Reserved", wintypes.BYTE * 3),
        ("Chemistry", wintypes.BYTE * 4),
        ("DesignedCapacity", wintypes.ULONG),
        ("FullChargedCapacity", wintypes.ULONG),
        ("DefaultAlert1", wintypes.ULONG),
        ("DefaultAlert2", wintypes.ULONG),
        ("CriticalBias", wintypes.ULONG),
        ("CycleCount", wintypes.ULONG),
    ]


class BATTERY_WAIT_STATUS(ctypes.Structure):
    _fields_ = [
        ("BatteryTag", wintypes.ULONG),
        ("Timeout", wintypes.ULONG),
        ("PowerState", wintypes.ULONG),
        ("LowCapacity", wintypes.ULONG),
        ("HighCapacity", wintypes.ULONG),
    ]


class BATTERY_STATUS(ctypes.Structure):
    _fields_ = [
        ("PowerState", wintypes.ULONG),
        ("Capacity", wintypes.ULONG),
        ("Voltage", wintypes.ULONG),
        ("Rate", wintypes.LONG),
    ]


class BATTERY_MANUFACTURE_DATE(ctypes.Structure):
    _fields_ = [
        ("Day", wintypes.BYTE),
        ("Month", wintypes.BYTE),
        ("Year", wintypes.USHORT),
    ]


class BATTERY_REPORTING_SCALE(ctypes.Structure):
    _fields_ = [
        ("Granularity", wintypes.ULONG),
        ("Capacity", wintypes.ULONG),
    ]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


class SYSTEM_BATTERY_STATE(ctypes.Structure):
    _fields_ = [
        ("AcOnLine", wintypes.BOOLEAN),
        ("BatteryPresent", wintypes.BOOLEAN),
        ("Charging", wintypes.BOOLEAN),
        ("Discharging", wintypes.BOOLEAN),
        ("Spare1", wintypes.BOOLEAN * 3),
        ("Tag", wintypes.BYTE),
        ("MaxCapacity", wintypes.DWORD),
        ("RemainingCapacity", wintypes.DWORD),
        ("Rate", wintypes.DWORD),
        ("EstimatedTime", wintypes.DWORD),
        ("DefaultAlert1", wintypes.DWORD),
        ("DefaultAlert2", wintypes.DWORD),
    ]


class SYSTEM_POWER_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("MaxIdlenessAllowed", wintypes.ULONG),
        ("Idleness", wintypes.ULONG),
        ("TimeRemaining", wintypes.ULONG),
        ("CoolingMode", wintypes.BYTE),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
powrprof = ctypes.WinDLL("powrprof", use_last_error=True)

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE

kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
]
kernel32.DeviceIoControl.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(SYSTEM_POWER_STATUS)]
kernel32.GetSystemPowerStatus.restype = wintypes.BOOL

setupapi.SetupDiGetClassDevsW.argtypes = [
    ctypes.POINTER(GUID),
    wintypes.LPCWSTR,
    wintypes.HWND,
    wintypes.DWORD,
]
setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE

setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE,
    wintypes.LPVOID,
    ctypes.POINTER(GUID),
    wintypes.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL

setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    wintypes.LPVOID,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL

setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

powrprof.CallNtPowerInformation.argtypes = [
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.ULONG,
    wintypes.LPVOID,
    wintypes.ULONG,
]
powrprof.CallNtPowerInformation.restype = wintypes.LONG  # NTSTATUS


def _guid() -> GUID:
    data1, data2, data3, data4 = GUID_DEVINTERFACE_BATTERY
    guid = GUID()
    guid.Data1 = data1
    guid.Data2 = data2
    guid.Data3 = data3
    guid.Data4 = (wintypes.BYTE * 8)(*data4)
    return guid


def _valid_u32(value: Optional[int]) -> Optional[int]:
    if value is None or value == BATTERY_UNKNOWN_CAPACITY or value == 0xFFFFFFFF:
        return None
    return int(value)


def _valid_rate(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if ctypes.c_uint32(value).value == BATTERY_UNKNOWN_RATE:
        return None
    if value == -2147483648:
        return None
    return int(value)


def _chemistry_text(raw: str) -> str:
    key = raw.strip().upper()
    pretty = CHEM_NAMES.get(key)
    if pretty == "Olověný akumulátor":
        pretty = tr("Olověný akumulátor")
    if pretty and pretty.upper() != key:
        return f"{pretty} ({raw.strip()})"
    return raw.strip() or tr("neuvedeno")


def _capability_names(caps: int) -> tuple:
    names = []
    if caps & BATTERY_SYSTEM_BATTERY:
        names.append(tr("Systémová baterie"))
    if caps & BATTERY_CAPACITY_RELATIVE:
        names.append(tr("Relativní kapacita (ne mWh)"))
    if caps & BATTERY_IS_SHORT_TERM:
        names.append(tr("Krátkodobá záloha"))
    if caps & BATTERY_SET_CHARGE_SUPPORTED:
        names.append(tr("Řadič dovoluje nastavit nabíjení"))
    if caps & BATTERY_SET_DISCHARGE_SUPPORTED:
        names.append(tr("Řadič dovoluje nastavit vybíjení"))
    return tuple(names)


@dataclass
class SystemPower:
    ac_online: Optional[bool] = None
    battery_present: Optional[bool] = None
    charging: Optional[bool] = None
    discharging: Optional[bool] = None
    percent: Optional[int] = None
    life_seconds: Optional[int] = None
    full_life_seconds: Optional[int] = None
    battery_flag: Optional[int] = None
    saver: Optional[bool] = None
    rate_mw: Optional[int] = None
    remaining_mwh: Optional[int] = None
    max_mwh: Optional[int] = None
    estimated_seconds: Optional[int] = None
    tag: Optional[int] = None
    idleness: Optional[int] = None
    cooling_mode: Optional[int] = None


@dataclass
class Battery:
    index: int
    device_path: str = ""
    tag: Optional[int] = None
    present: bool = True
    charging: bool = False
    discharging: bool = False
    on_line: bool = False
    critical: bool = False
    percent: Optional[float] = None
    voltage_mv: Optional[int] = None
    rate_mw: Optional[int] = None
    current_ma: Optional[float] = None
    remaining_mwh: Optional[int] = None
    designed_mwh: Optional[int] = None
    full_charged_mwh: Optional[int] = None
    cycle_count: Optional[int] = None
    chemistry: Optional[str] = None
    chemistry_raw: Optional[str] = None
    technology: Optional[str] = None
    manufacturer: Optional[str] = None
    device_name: Optional[str] = None
    serial: Optional[str] = None
    unique_id: Optional[str] = None
    manufacture_date: Optional[str] = None
    temperature_c: Optional[float] = None
    estimated_seconds: Optional[int] = None
    alert1: Optional[int] = None
    alert2: Optional[int] = None
    critical_bias: Optional[int] = None
    capabilities: tuple = ()
    relative_capacity: bool = False
    power_state: Optional[int] = None
    granularity: tuple = ()
    error: Optional[str] = None
    source: str = "ACPI IOCTL"

    @property
    def key(self) -> str:
        return self.unique_id or self.serial or self.device_path or f"battery-{self.index}"

    @property
    def health_percent(self) -> Optional[float]:
        if not self.designed_mwh or self.full_charged_mwh is None:
            return None
        if self.relative_capacity:
            return None
        return max(0.0, min(150.0, 100.0 * self.full_charged_mwh / self.designed_mwh))

    @property
    def wear_percent(self) -> Optional[float]:
        health = self.health_percent
        if health is None:
            return None
        return max(0.0, 100.0 - health)

    @property
    def power_w(self) -> Optional[float]:
        if self.rate_mw is None:
            return None
        return self.rate_mw / 1000.0


@dataclass
class Snapshot:
    system: SystemPower
    batteries: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def _device_io(handle, code: int, in_buf, out_size: int):
    out = ctypes.create_string_buffer(out_size)
    returned = wintypes.DWORD(0)
    if in_buf is None:
        in_ptr = None
        in_len = 0
    else:
        in_ptr = ctypes.byref(in_buf)
        in_len = ctypes.sizeof(in_buf)
    ok = kernel32.DeviceIoControl(
        handle,
        code,
        in_ptr,
        in_len,
        out,
        out_size,
        ctypes.byref(returned),
        None,
    )
    if not ok:
        return None, ctypes.get_last_error()
    return out, int(returned.value)


def _query_tag(handle) -> Optional[int]:
    timeout = wintypes.ULONG(100)
    out, _err = _device_io(handle, IOCTL_BATTERY_QUERY_TAG, timeout, 4)
    if out is None:
        timeout = wintypes.ULONG(0)
        out, _err = _device_io(handle, IOCTL_BATTERY_QUERY_TAG, timeout, 4)
    if out is None:
        return None
    return int(ctypes.cast(out, ctypes.POINTER(wintypes.ULONG)).contents.value)


def _query_info(handle, tag: int, level: int, out_size: int, at_rate: int = 0):
    query = BATTERY_QUERY_INFORMATION()
    query.BatteryTag = tag
    query.InformationLevel = level
    query.AtRate = at_rate
    out, err = _device_io(handle, IOCTL_BATTERY_QUERY_INFORMATION, query, out_size)
    return out, err


def _read_wstring(buf, nbytes: int) -> Optional[str]:
    if buf is None or nbytes < 2:
        return None
    raw = buf.raw[:nbytes]
    # Oříznout za prvním nulovým znakem.
    chars = []
    for i in range(0, len(raw) - 1, 2):
        code = raw[i] | (raw[i + 1] << 8)
        if code == 0:
            break
        chars.append(chr(code))
    text = "".join(chars).strip().strip("\x00")
    return text or None


def _open_battery(path: str):
    for access in (GENERIC_READ | GENERIC_WRITE, GENERIC_READ, 0):
        handle = kernel32.CreateFileW(
            path,
            access,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle and handle != INVALID_HANDLE_VALUE:
            return handle
    return None


def _battery_paths() -> list:
    guid = _guid()
    collection = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if not collection or collection == INVALID_HANDLE_VALUE:
        return []
    paths = []
    try:
        index = 0
        while index < 16:
            iface = SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            ok = setupapi.SetupDiEnumDeviceInterfaces(
                collection,
                None,
                ctypes.byref(guid),
                index,
                ctypes.byref(iface),
            )
            if not ok:
                err = ctypes.get_last_error()
                if err in (ERROR_NO_MORE_ITEMS, 0):
                    break
                break
            needed = wintypes.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                collection,
                ctypes.byref(iface),
                None,
                0,
                ctypes.byref(needed),
                None,
            )
            if needed.value < 8:
                index += 1
                continue
            buf = ctypes.create_string_buffer(needed.value)
            cb = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value = cb
            detail_ok = setupapi.SetupDiGetDeviceInterfaceDetailW(
                collection,
                ctypes.byref(iface),
                buf,
                needed.value,
                ctypes.byref(needed),
                None,
            )
            if detail_ok:
                path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                if path:
                    paths.append(path)
            index += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(collection)
    return paths


def _fill_static(battery: Battery, handle, tag: int) -> None:
    info_buf, _err = _query_info(handle, tag, BatteryInformation, ctypes.sizeof(BATTERY_INFORMATION))
    if info_buf is not None:
        info = ctypes.cast(info_buf, ctypes.POINTER(BATTERY_INFORMATION)).contents
        caps = int(info.Capabilities)
        battery.capabilities = _capability_names(caps)
        battery.relative_capacity = bool(caps & BATTERY_CAPACITY_RELATIVE)
        raw = bytes(info.Chemistry).decode("ascii", errors="ignore").strip("\x00 ").strip()
        battery.chemistry_raw = raw or None
        battery.chemistry = _chemistry_text(raw) if raw else None
        battery.technology = tr("Dobíjecí") if info.Technology == 1 else tr("Jednorázová")
        battery.designed_mwh = _valid_u32(info.DesignedCapacity)
        battery.full_charged_mwh = _valid_u32(info.FullChargedCapacity)
        battery.alert1 = _valid_u32(info.DefaultAlert1)
        battery.alert2 = _valid_u32(info.DefaultAlert2)
        battery.critical_bias = int(info.CriticalBias) if info.CriticalBias else 0
        cycles = int(info.CycleCount)
        battery.cycle_count = cycles
        if battery.designed_mwh == 0:
            battery.designed_mwh = None
        if battery.full_charged_mwh == 0:
            battery.full_charged_mwh = None

    name, _err = _query_info(handle, tag, BatteryDeviceName, 1024)
    if name is not None:
        battery.device_name = _read_wstring(name, 1024)
    manu, _err = _query_info(handle, tag, BatteryManufactureName, 1024)
    if manu is not None:
        battery.manufacturer = _read_wstring(manu, 1024)
    serial, _err = _query_info(handle, tag, BatterySerialNumber, 1024)
    if serial is not None:
        battery.serial = _read_wstring(serial, 1024)
    unique, _err = _query_info(handle, tag, BatteryUniqueID, 1024)
    if unique is not None:
        battery.unique_id = _read_wstring(unique, 1024)

    date_buf, _err = _query_info(handle, tag, BatteryManufactureDate, ctypes.sizeof(BATTERY_MANUFACTURE_DATE))
    if date_buf is not None:
        date = ctypes.cast(date_buf, ctypes.POINTER(BATTERY_MANUFACTURE_DATE)).contents
        if date.Year and date.Month and date.Day:
            battery.manufacture_date = f"{int(date.Day)}. {int(date.Month)}. {int(date.Year)}"

    temp_buf, _err = _query_info(handle, tag, BatteryTemperature, 4)
    if temp_buf is not None:
        tenth_k = int(ctypes.cast(temp_buf, ctypes.POINTER(wintypes.ULONG)).contents.value)
        if tenth_k and tenth_k != 0xFFFFFFFF:
            celsius = tenth_k / 10.0 - 273.15
            if -20.0 <= celsius <= 120.0:
                battery.temperature_c = celsius

    scales_buf, _err = _query_info(
        handle,
        tag,
        BatteryGranularityInformation,
        ctypes.sizeof(BATTERY_REPORTING_SCALE) * 4,
    )
    if scales_buf is not None:
        count = 4
        scales = []
        array = ctypes.cast(scales_buf, ctypes.POINTER(BATTERY_REPORTING_SCALE))
        for i in range(count):
            gran = int(array[i].Granularity)
            cap = int(array[i].Capacity)
            if gran or cap:
                scales.append((gran, cap))
        battery.granularity = tuple(scales)


def _fill_status(battery: Battery, handle, tag: int) -> None:
    wait = BATTERY_WAIT_STATUS()
    wait.BatteryTag = tag
    wait.Timeout = 0
    wait.PowerState = 0
    wait.LowCapacity = 0
    wait.HighCapacity = 0
    out, _err = _device_io(handle, IOCTL_BATTERY_QUERY_STATUS, wait, ctypes.sizeof(BATTERY_STATUS))
    if out is None:
        battery.error = tr("Stav baterie se nepodařilo přečíst.")
        return
    status = ctypes.cast(out, ctypes.POINTER(BATTERY_STATUS)).contents
    state = int(status.PowerState)
    battery.power_state = state
    battery.on_line = bool(state & BATTERY_POWER_ON_LINE)
    battery.discharging = bool(state & BATTERY_DISCHARGING)
    battery.charging = bool(state & BATTERY_CHARGING)
    battery.critical = bool(state & BATTERY_CRITICAL)

    remaining = _valid_u32(status.Capacity)
    battery.remaining_mwh = remaining
    voltage = int(status.Voltage)
    if voltage and voltage != BATTERY_UNKNOWN_VOLTAGE:
        battery.voltage_mv = voltage
    rate = _valid_rate(int(status.Rate))
    if rate is not None:
        # Kladný Rate = nabíjení, záporný = vybíjení. Některé řadiče hlásí
        # absolutní hodnotu a směr jen příznakem.
        if battery.discharging and rate > 0:
            rate = -rate
        elif battery.charging and rate < 0:
            rate = -rate
        battery.rate_mw = rate
    full = battery.full_charged_mwh
    if remaining is not None and full:
        battery.percent = max(0.0, min(100.0, 100.0 * remaining / full))
    if battery.rate_mw is not None and battery.voltage_mv:
        battery.current_ma = battery.rate_mw / battery.voltage_mv * 1000.0

    est, _err = _query_info(handle, tag, BatteryEstimatedTime, 4, 0)
    if est is not None:
        seconds = int(ctypes.cast(est, ctypes.POINTER(wintypes.ULONG)).contents.value)
        if seconds and seconds != BATTERY_UNKNOWN_TIME:
            battery.estimated_seconds = seconds


def _read_system() -> SystemPower:
    system = SystemPower()
    power = SYSTEM_POWER_STATUS()
    if kernel32.GetSystemPowerStatus(ctypes.byref(power)):
        ac = int(power.ACLineStatus)
        if ac in (0, 1):
            system.ac_online = bool(ac)
        flag = int(power.BatteryFlag)
        system.battery_flag = flag
        system.battery_present = flag != 128
        system.charging = bool(flag & 8)
        system.saver = bool(power.SystemStatusFlag)
        percent = int(power.BatteryLifePercent)
        if percent != 255:
            system.percent = percent
        life = int(power.BatteryLifeTime)
        if life != BATTERY_UNKNOWN_TIME:
            system.life_seconds = life
        full_life = int(power.BatteryFullLifeTime)
        if full_life != BATTERY_UNKNOWN_TIME:
            system.full_life_seconds = full_life

    state = SYSTEM_BATTERY_STATE()
    status = powrprof.CallNtPowerInformation(
        SystemBatteryState,
        None,
        0,
        ctypes.byref(state),
        ctypes.sizeof(state),
    )
    if status == 0:
        system.ac_online = bool(state.AcOnLine) if system.ac_online is None else system.ac_online
        system.battery_present = bool(state.BatteryPresent)
        system.charging = bool(state.Charging) or bool(system.charging)
        system.discharging = bool(state.Discharging)
        if system.ac_online is None:
            system.ac_online = bool(state.AcOnLine)
        else:
            system.ac_online = bool(state.AcOnLine) or system.ac_online
        system.tag = int(state.Tag) or None
        system.max_mwh = _valid_u32(state.MaxCapacity)
        system.remaining_mwh = _valid_u32(state.RemainingCapacity)
        rate = int(state.Rate)
        if rate != BATTERY_UNKNOWN_RATE and rate != 0xFFFFFFFF:
            signed = rate
            if system.discharging:
                signed = -abs(rate)
            elif system.charging:
                signed = abs(rate)
            system.rate_mw = signed
        est = int(state.EstimatedTime)
        if est and est != BATTERY_UNKNOWN_TIME:
            system.estimated_seconds = est

    info = SYSTEM_POWER_INFORMATION()
    st = powrprof.CallNtPowerInformation(
        SystemPowerInformation,
        None,
        0,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if st == 0:
        system.idleness = int(info.Idleness)
        system.cooling_mode = int(info.CoolingMode)
        if system.life_seconds is None:
            remaining = int(info.TimeRemaining)
            if remaining and remaining != BATTERY_UNKNOWN_TIME and remaining != 0xFFFFFFFF:
                system.life_seconds = remaining
    return system


def _synthetic_from_system(system: SystemPower) -> Optional[Battery]:
    if not system.battery_present:
        return None
    battery = Battery(index=0, source="GetSystemPowerStatus", present=True)
    battery.charging = bool(system.charging)
    battery.discharging = bool(system.discharging)
    battery.on_line = bool(system.ac_online)
    battery.percent = float(system.percent) if system.percent is not None else None
    battery.remaining_mwh = system.remaining_mwh
    battery.full_charged_mwh = system.max_mwh
    battery.rate_mw = system.rate_mw
    battery.estimated_seconds = system.estimated_seconds or system.life_seconds
    if battery.percent is None and battery.remaining_mwh and battery.full_charged_mwh:
        battery.percent = max(0.0, min(100.0, 100.0 * battery.remaining_mwh / battery.full_charged_mwh))
    battery.device_name = tr("Systémová baterie")
    battery.error = tr("Detailní ACPI údaje nejsou dostupné, zobrazen je souhrn Windows.")
    return battery


def read_snapshot() -> Snapshot:
    system = _read_system()
    batteries = []
    errors = []
    try:
        paths = _battery_paths()
    except Exception as exc:
        paths = []
        errors.append(tr("Výčet baterií selhal: {error}", error=exc))

    for index, path in enumerate(paths):
        battery = Battery(index=index, device_path=path)
        handle = _open_battery(path)
        if not handle:
            battery.present = False
            battery.error = tr("Zařízení baterie nelze otevřít (kód {code}).", code=ctypes.get_last_error())
            batteries.append(battery)
            continue
        try:
            tag = _query_tag(handle)
            battery.tag = tag
            if not tag:
                battery.present = False
                battery.error = tr("Baterie nehlásí platný tag (není vložená, nebo ji řadič nevidí).")
                batteries.append(battery)
                continue
            _fill_static(battery, handle, tag)
            _fill_status(battery, handle, tag)
            if battery.percent is None and system.percent is not None and index == 0:
                battery.percent = float(system.percent)
            if battery.estimated_seconds is None:
                battery.estimated_seconds = system.estimated_seconds or system.life_seconds
        except Exception as exc:
            battery.error = str(exc)
            errors.append(str(exc))
        finally:
            kernel32.CloseHandle(handle)
        batteries.append(battery)

    if not batteries:
        synthetic = _synthetic_from_system(system)
        if synthetic is not None:
            batteries.append(synthetic)
        elif system.battery_present is False:
            errors.append(tr("V tomto počítači není baterie."))
    return Snapshot(system=system, batteries=batteries, errors=errors)


def _demo() -> None:
    snap = read_snapshot()
    sys = snap.system
    print("AC:", sys.ac_online, "present:", sys.battery_present, "charge:", sys.charging, "dis:", sys.discharging)
    print("percent:", sys.percent, "life:", sys.life_seconds, "rate_mW:", sys.rate_mw)
    print("remain:", sys.remaining_mwh, "max:", sys.max_mwh, "idle:", sys.idleness, "cool:", sys.cooling_mode)
    print("errors:", snap.errors)
    for bat in snap.batteries:
        print("---", bat.index, bat.device_name, bat.manufacturer)
        print("  path:", bat.device_path)
        print("  chem:", bat.chemistry, "tech:", bat.technology, "date:", bat.manufacture_date)
        print("  serial:", bat.serial, "uid:", bat.unique_id, "cycles:", bat.cycle_count)
        print("  design:", bat.designed_mwh, "full:", bat.full_charged_mwh, "remain:", bat.remaining_mwh)
        print("  %:", bat.percent, "mV:", bat.voltage_mv, "mW:", bat.rate_mw, "mA:", bat.current_ma)
        print("  temp:", bat.temperature_c, "est:", bat.estimated_seconds, "health:", bat.health_percent)
        print("  caps:", bat.capabilities, "rel:", bat.relative_capacity, "state:", bat.power_state)
        print("  gran:", bat.granularity, "err:", bat.error, "src:", bat.source)


if __name__ == "__main__":
    _demo()
