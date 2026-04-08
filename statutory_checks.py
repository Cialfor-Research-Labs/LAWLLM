from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class LimitationResult:
    deadline: Optional[date]
    is_time_barred: Optional[bool]
    rule: str


def _safe_add_years(d: date, years: int) -> date:
    try:
        return date(d.year + years, d.month, d.day)
    except ValueError:
        # Leap-day rollover.
        return date(d.year + years, d.month, 28)


def consumer_limitation(incident_date: Optional[date], today: date) -> LimitationResult:
    if incident_date is None:
        return LimitationResult(deadline=None, is_time_barred=None, rule="missing_incident_date")
    deadline = _safe_add_years(incident_date, 2)
    return LimitationResult(
        deadline=deadline,
        is_time_barred=today > deadline,
        rule="consumer_2_years",
    )


def money_recovery_limitation(incident_date: Optional[date], today: date) -> LimitationResult:
    if incident_date is None:
        return LimitationResult(deadline=None, is_time_barred=None, rule="missing_incident_date")
    deadline = _safe_add_years(incident_date, 3)
    return LimitationResult(
        deadline=deadline,
        is_time_barred=today > deadline,
        rule="money_recovery_3_years",
    )
