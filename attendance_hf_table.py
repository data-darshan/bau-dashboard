"""Presentation-only helpers for the Attendance 5-to-8-hours detail view.

Source ``working_hours`` is Actual Working Hours; ``total_hours`` is not used.
No report parsing, database rows, status buckets, or percentages are changed.
"""
from __future__ import annotations

import csv
import io
import math
from html import escape
from typing import Any, Iterable, Mapping


NEAR_EIGHT_THRESHOLD_HOURS = 7.7
EXISTING_DETAIL_COLUMNS = (
    "Employee ID", "Employee Name", "Role", "Shift", "Working Hours"
)


def _hours(row: Mapping[str, Any]) -> float | None:
    """Get the stored *actual* working hours, without rounding for selection."""
    value = row.get("Working Hours")
    if value is None or value == "":
        return None
    try:
        hours = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return hours if math.isfinite(hours) else None


def partition_5_to_8_hour_rows(
    records: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Sort by actual hours descending; split only for presentation.

    Exact 7.7 hours is included in the green-outlined group. Missing or
    invalid hours are shown at the end of the normal group, not as zero hours.
    """
    prepared = [(dict(row), _hours(row)) for row in records]
    prepared.sort(key=lambda item: (item[1] is None, -(item[1] or 0.0)))
    near = [row for row, hours in prepared if hours is not None and hours >= NEAR_EIGHT_THRESHOLD_HOURS]
    other = [row for row, hours in prepared if hours is None or hours < NEAR_EIGHT_THRESHOLD_HOURS]
    return near, other


def _cell_text(row: Mapping[str, Any], column: str) -> str:
    if column == "Working Hours":
        hours = _hours(row)
        return f"{hours:.2f}" if hours is not None else "&mdash;"
    value = row.get(column)
    if value is None or str(value).strip() == "":
        return "&mdash;"
    return escape(str(value), quote=True)


def _table_group(title: str, description: str, rows: list[dict[str, Any]], kind: str) -> str:
    header = "".join(
        f"<th scope='col'>{escape('Actual Working Hours' if c == 'Working Hours' else c)}</th>"
        for c in EXISTING_DETAIL_COLUMNS
    )
    def row_html(row: Mapping[str, Any]) -> str:
        cells = []
        for column in EXISTING_DETAIL_COLUMNS:
            text = _cell_text(row, column)
            if column == "Employee ID":
                text = f'<span class="bau-hf-copy-id">{text}</span>'
            cells.append(f"<td>{text}</td>")
        return "<tr>" + "".join(cells) + "</tr>"
    content = "".join(row_html(row) for row in rows)
    count_label = f"{len(rows):,} employee" + ("" if len(rows) == 1 else "s")
    if not rows:
        body = "<div class='bau-hf-none'>No employees in this group.</div>"
    else:
        body = (
            "<div class='bau-hf-table-scroll'>"
            f"<table class='bau-hf-table bau-hf-{kind}' aria-label='{escape(title, quote=True)}'>"
            f"<thead><tr>{header}</tr></thead><tbody>{content}</tbody></table></div>"
        )
    return (
        "<section class='bau-hf-section'>"
        "<div class='bau-hf-section-head'>"
        f"<span class='bau-hf-section-title'>{escape(title)}</span>"
        f"<span class='bau-hf-count'>{count_label}</span></div>"
        f"<p class='bau-hf-description'>{escape(description)}</p>"
        f"{body}</section>"
    )


def attendance_hf_html(
    near: list[dict[str, Any]], other: list[dict[str, Any]],
) -> str:
    """Build the two visual groups, using a dashed green vs solid black row outline."""
    css = """
    <style>
    .bau-hf-section { margin: 0 0 20px; color: #231F20; }
    .bau-hf-section-head { display: flex; align-items: center; justify-content: space-between;
        gap: 12px; flex-wrap: wrap; margin: 2px 0 4px; }
    .bau-hf-section-title { font-size: 15px; font-weight: 750; }
    .bau-hf-count { font-size: 12px; font-weight: 700; color: #526158;
        background: #F0F3EE; padding: 4px 10px; border-radius: 999px; }
    .bau-hf-description { margin: 0 0 8px; font-size: 12px; color: #65716A; }
    .bau-hf-none { color: #65716A; background: #F6F7F5; border-radius: 10px;
        padding: 13px; font-size: 13px; }
    .bau-hf-table-scroll { overflow: auto; max-height: 340px; padding: 0 1px;
        scrollbar-width: thin; }
    .bau-hf-table { border-collapse: separate; border-spacing: 0 5px;
        width: 100%; min-width: 650px; font-size: 12.5px; line-height: 1.4; }
    .bau-hf-table th { position: sticky; top: 0; z-index: 1;
        background: #EDF3ED; color: #3C5142; font-weight: 700;
        padding: 10px 11px; text-align: left; white-space: nowrap; }
    .bau-hf-table th:last-child, .bau-hf-table td:last-child { text-align: right; }
    .bau-hf-table td { padding: 9px 11px; vertical-align: middle;
        user-select: text !important; -webkit-user-select: text !important; cursor: text; }
    .bau-hf-copy-id { user-select: all !important; -webkit-user-select: all !important;
        cursor: text; white-space: pre; }
    /* Four edges enclose each employee row; no coloring of official statuses. */
    .bau-hf-green td { background: #F0F7F2;
        border-top: 2px dashed #008A71; border-bottom: 2px dashed #008A71; }
    .bau-hf-green td:first-child { border-left: 2px dashed #008A71;
        border-radius: 8px 0 0 8px; }
    .bau-hf-green td:last-child { border-right: 2px dashed #008A71;
        border-radius: 0 8px 8px 0; }
    .bau-hf-normal td { background: #fff;
        border-top: 1px solid #231F20; border-bottom: 1px solid #231F20; }
    .bau-hf-normal td:first-child { border-left: 1px solid #231F20;
        border-radius: 8px 0 0 8px; }
    .bau-hf-normal td:last-child { border-right: 1px solid #231F20;
        border-radius: 0 8px 8px 0; }
    </style>
    """
    return (
        css
        + _table_group(
            "7.7 hours or more", "Green dashed outline: actual working hours >= 7.7. Review indicator only.",
            near, "green",
        )
        + _table_group(
            "Remaining 5 to 8 hours", "Standard black outline: actual working hours below 7.7 or unavailable.",
            other, "normal",
        )
    )


def attendance_hf_csv(near: list[dict[str, Any]], other: list[dict[str, Any]]) -> bytes:
    """Export the same five original detail columns, without color or new fields."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(EXISTING_DETAIL_COLUMNS)
    for row in [*near, *other]:
        writer.writerow([row.get(column) for column in EXISTING_DETAIL_COLUMNS])
    return stream.getvalue().encode("utf-8-sig")
