"""Analýza naměřeného CSV logu baterie — výdrž, spotřeba, detekce chyb."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from i18n import tr


@dataclass
class MeasurementIssue:
    kind: str
    when: float
    detail: str
    severity: str = "warning"  # info | warning | critical


@dataclass
class MeasurementReport:
    sample_count: int = 0
    total_seconds: float = 0.0
    discharge_seconds: float = 0.0
    charge_seconds: float = 0.0
    idle_seconds: float = 0.0
    start_percent: Optional[float] = None
    end_percent: Optional[float] = None
    consumed_percent: Optional[float] = None
    gained_percent: Optional[float] = None
    start_mwh: Optional[int] = None
    end_mwh: Optional[int] = None
    consumed_mwh: Optional[int] = None
    gained_mwh: Optional[int] = None
    drawn_wh: float = 0.0
    stored_wh: float = 0.0
    avg_discharge_w: Optional[float] = None
    peak_discharge_w: Optional[float] = None
    avg_charge_w: Optional[float] = None
    avg_voltage_v: Optional[float] = None
    min_voltage_v: Optional[float] = None
    max_voltage_v: Optional[float] = None
    avg_discharge_pct_per_hour: Optional[float] = None
    projected_full_hours: Optional[float] = None
    health_percent: Optional[float] = None
    designed_mwh: Optional[int] = None
    full_charged_mwh: Optional[int] = None
    manufacturer: Optional[str] = None
    device_name: Optional[str] = None
    chemistry: Optional[str] = None
    issues: list = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len([item for item in self.issues if item.severity in ("warning", "critical")])

    @property
    def critical_count(self) -> int:
        return len([item for item in self.issues if item.severity == "critical"])


def _mean(values: list) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _phase(sample) -> str:
    if sample.discharging or (sample.rate_mw is not None and sample.rate_mw < -50):
        return "discharge"
    if sample.charging or (sample.rate_mw is not None and sample.rate_mw > 50):
        return "charge"
    return "idle"


def analyze_measurement(samples: list, meta=None) -> MeasurementReport:
    report = MeasurementReport(sample_count=len(samples))
    if meta is not None:
        report.health_percent = getattr(meta, "health_percent", None)
        report.designed_mwh = getattr(meta, "designed_mwh", None)
        report.full_charged_mwh = getattr(meta, "full_charged_mwh", None)
        report.manufacturer = getattr(meta, "manufacturer", None)
        report.device_name = getattr(meta, "device_name", None)
        report.chemistry = getattr(meta, "chemistry", None)

    if len(samples) < 2:
        if samples:
            report.start_percent = samples[0].percent
            report.end_percent = samples[0].percent
            report.start_mwh = samples[0].remaining_mwh
            report.end_mwh = samples[0].remaining_mwh
        return report

    report.total_seconds = max(0.0, samples[-1].t - samples[0].t)
    report.start_percent = samples[0].percent
    report.end_percent = samples[-1].percent
    report.start_mwh = samples[0].remaining_mwh
    report.end_mwh = samples[-1].remaining_mwh

    if report.start_percent is not None and report.end_percent is not None:
        delta = report.start_percent - report.end_percent
        if delta > 0:
            report.consumed_percent = delta
        elif delta < 0:
            report.gained_percent = -delta

    if report.start_mwh is not None and report.end_mwh is not None:
        delta_mwh = report.start_mwh - report.end_mwh
        if delta_mwh > 0:
            report.consumed_mwh = int(delta_mwh)
        elif delta_mwh < 0:
            report.gained_mwh = int(-delta_mwh)

    discharge_powers = []
    charge_powers = []
    voltages = []
    discharge_pct_points = []

    for prev, cur in zip(samples, samples[1:]):
        dt = cur.t - prev.t
        if not (0 < dt < 180):
            if dt >= 180:
                report.issues.append(
                    MeasurementIssue(
                        kind="gap",
                        when=prev.t,
                        detail=tr("Výpadek záznamu {minutes} min mezi vzorky.", minutes=f"{dt / 60.0:.1f}"),
                        severity="info",
                    )
                )
            continue

        phase = _phase(cur)
        if phase == "discharge":
            report.discharge_seconds += dt
        elif phase == "charge":
            report.charge_seconds += dt
        else:
            report.idle_seconds += dt

        if cur.voltage_mv:
            voltages.append(cur.voltage_mv / 1000.0)

        if cur.rate_mw is not None and 0 < dt < 60:
            wh = abs(cur.rate_mw) / 1000.0 * dt / 3600.0
            if phase == "discharge" or cur.rate_mw < 0:
                report.drawn_wh += wh
                discharge_powers.append(abs(cur.rate_mw) / 1000.0)
            elif phase == "charge" or cur.rate_mw > 0:
                report.stored_wh += wh
                charge_powers.append(abs(cur.rate_mw) / 1000.0)

        # Náhlý propad nabití při vybíjení
        if (
            prev.percent is not None
            and cur.percent is not None
            and phase == "discharge"
        ):
            drop = prev.percent - cur.percent
            if drop >= 2.0 and dt <= 12:
                report.issues.append(
                    MeasurementIssue(
                        kind="sudden_percent",
                        when=cur.t,
                        detail=tr("Náhlý propad nabití o {drop} % za {seconds} s.", drop=f"{drop:.1f}", seconds=f"{dt:.0f}"),
                        severity="critical" if drop >= 5 else "warning",
                    )
                )
            elif drop >= 5.0 and dt <= 60:
                report.issues.append(
                    MeasurementIssue(
                        kind="fast_drop",
                        when=cur.t,
                        detail=tr("Rychlý úbytek výdrže {drop} % za {seconds} s.", drop=f"{drop:.1f}", seconds=f"{dt:.0f}"),
                        severity="warning",
                    )
                )
            if drop > 0 and dt >= 5:
                discharge_pct_points.append(drop / dt * 3600.0)

            # Glitch: nabití naskočí nahoru při vybíjení
            rise = cur.percent - prev.percent
            if rise >= 1.5 and dt <= 20:
                report.issues.append(
                    MeasurementIssue(
                        kind="percent_glitch",
                        when=cur.t,
                        detail=tr("Podezřelý skok nabití nahoru o {rise} % při vybíjení.", rise=f"{rise:.1f}"),
                        severity="warning",
                    )
                )

        # Propady napětí
        if prev.voltage_mv and cur.voltage_mv and phase == "discharge":
            dv = (prev.voltage_mv - cur.voltage_mv) / 1000.0
            if dv >= 0.35 and dt <= 20:
                report.issues.append(
                    MeasurementIssue(
                        kind="voltage_drop",
                        when=cur.t,
                        detail=tr("Prudký pokles napětí o {volts} V za {seconds} s.", volts=f"{dv:.2f}", seconds=f"{dt:.0f}"),
                        severity="critical" if dv >= 0.6 else "warning",
                    )
                )

        # Kapacita mWh stoupá při vybíjení
        if (
            prev.remaining_mwh is not None
            and cur.remaining_mwh is not None
            and phase == "discharge"
            and cur.remaining_mwh > prev.remaining_mwh + 50
            and dt <= 30
        ):
            report.issues.append(
                MeasurementIssue(
                    kind="capacity_glitch",
                    when=cur.t,
                    detail=tr("Zbývající kapacita při vybíjení naskočila nahoru (chyba hlášení)."),
                    severity="warning",
                )
            )

    report.avg_discharge_w = _mean(discharge_powers)
    report.peak_discharge_w = max(discharge_powers) if discharge_powers else None
    report.avg_charge_w = _mean(charge_powers)
    report.avg_voltage_v = _mean(voltages)
    report.min_voltage_v = min(voltages) if voltages else None
    report.max_voltage_v = max(voltages) if voltages else None
    report.avg_discharge_pct_per_hour = _mean(discharge_pct_points)

    if report.avg_discharge_pct_per_hour and report.avg_discharge_pct_per_hour > 0.2:
        report.projected_full_hours = 100.0 / report.avg_discharge_pct_per_hour

    # Extrémně rychlé průměrné vybíjení
    if report.avg_discharge_pct_per_hour and report.avg_discharge_pct_per_hour >= 80:
        report.issues.append(
            MeasurementIssue(
                kind="extreme_rate",
                when=samples[0].t,
                detail=tr(
                    "Průměrná rychlost vybíjení {rate} %/h je abnormálně vysoká.",
                    rate=f"{report.avg_discharge_pct_per_hour:.0f}",
                ),
                severity="critical",
            )
        )
    elif report.avg_discharge_pct_per_hour and report.avg_discharge_pct_per_hour >= 45:
        report.issues.append(
            MeasurementIssue(
                kind="high_rate",
                when=samples[0].t,
                detail=tr(
                    "Vysoká průměrná rychlost vybíjení {rate} %/h.",
                    rate=f"{report.avg_discharge_pct_per_hour:.0f}",
                ),
                severity="warning",
            )
        )

    # Nesoulad energie a úbytku %
    full = report.full_charged_mwh
    if full and report.consumed_percent is not None and report.drawn_wh > 0.05:
        expected_pct = report.drawn_wh / (full / 1000.0) * 100.0
        if expected_pct > 1 and report.consumed_percent > expected_pct * 1.6 + 2:
            report.issues.append(
                MeasurementIssue(
                    kind="capacity_mismatch",
                    when=samples[-1].t,
                    detail=tr(
                        "Úbytek nabití ({consumed} %) je výrazně vyšší než odpovídá odebrané energii (~{expected} %).",
                        consumed=f"{report.consumed_percent:.1f}",
                        expected=f"{expected_pct:.1f}",
                    ),
                    severity="warning",
                )
            )

    # Deduplikace podobných chyb těsně za sebou (max 1 za 30 s stejného druhu)
    filtered = []
    last_by_kind = {}
    for issue in report.issues:
        prev_t = last_by_kind.get(issue.kind)
        if prev_t is not None and issue.when - prev_t < 30:
            continue
        filtered.append(issue)
        last_by_kind[issue.kind] = issue.when
    report.issues = filtered
    return report
