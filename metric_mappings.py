"""Match display labels to the exact count columns in the source workbooks.

Attendance and Flex intentionally use different 8-hour header spellings.
Do not normalize away the space before '+' in Attendance: that space is
present in the imported summary metric key, and missing it hides valid counts.
"""
from __future__ import annotations

_SOURCE_COUNT_METRICS = {
    "attendance": {
        "8 Hrs + Adherence": "8 Hours +",
        "5 to 8 Hrs Adherence": "5 to 8 Hours",
        "<5 Hrs Adherence": "Less than 5 Hours",
        "Single Punch %": "Single Punch",
    },
    "flex_working": {
        "8 Hrs + Adherence": "8 Hours+",
        "5 to 8 Hrs Adherence": "5 to 8 Hours",
        "<5 Hrs Adherence": "Less than 5 Hours",
        "Single Punch %": "Single Punch",
    },
}


def source_count_metric(section: str, chart_metric: str) -> str | None:
    """Return the exact stored count key for a selected chart metric."""
    return _SOURCE_COUNT_METRICS.get(section, {}).get(chart_metric)
