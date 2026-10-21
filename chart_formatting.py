"""Presentation-only chart formatting; source percentages are never rounded in storage."""
from __future__ import annotations

from datetime import date, datetime
from html import escape


def percentage_hover_template(metric: str, *, by_site: bool = False, report_day: date | None = None) -> str:
    """Round only the percentage shown on Plotly hover cards to a whole percent.

    The raw Plotly y value remains unchanged for bar/point location and drill-downs.
    Aadhaar/Manual onboarding intentionally retains variable decimal precision.
    """
    safe_metric = escape(metric, quote=True)
    if by_site:
        if report_day is None:
            raise ValueError("A single-day site view requires report_day")
        if isinstance(report_day, datetime):
            report_day = report_day.date()
        day = escape(report_day.strftime("%d %b %Y"))
        date_part = f"Date: {day}"
    else:
        date_part = "Date: %{x|%d %b %Y}"
    return (
        "<b>%{customdata[1]}</b><br>"
        + date_part + "<br>"
        + safe_metric + ": %{y:.0f}%"
        + "<extra></extra>"
    )
