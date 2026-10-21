"""Safe, read-only employee tables with browser-native text and ID selection.

Streamlit's interactive dataframe grid selects entire *cells*, so double-clicking
cannot reliably highlight the value of an employee ID. These semantic HTML tables
let the browser select text normally; an ID span selects its entire content
(including hyphens/leading zeros) for Ctrl+C. Source values are HTML-escaped.
"""
from __future__ import annotations

from html import escape
from typing import Any, Iterable, Mapping, Sequence


_ID_NAMES = frozenset({"employee id", "valinor id", "id", "user id", "aadhaar number", "aadhar number", "phone number"})


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def selectable_detail_html(columns: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> str:
    """Render details as selectable text, without JS, interactive grid or copies of data."""
    names = list(columns)
    head = "".join(f"<th scope='col'>{escape(name, quote=True)}</th>" for name in names)
    body: list[str] = []
    for row in rows:
        cells = []
        for name in names:
            content = escape(_as_text(row.get(name)), quote=True)
            if name.strip().casefold() in _ID_NAMES:
                # user-select:all copies the FULL identifier, even if it contains dashes.
                content = f'<span class="bau-copy-id" title="Select ID, then Ctrl+C to copy">{content}</span>'
            cells.append(f"<td>{content}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return """
<style>
.bau-detail-scroll {max-height:410px;overflow:auto;max-width:100%;border:1px solid #E2E7E3;
  border-radius:9px;scrollbar-width:thin;}
.bau-detail-table {border-collapse:collapse;width:100%;min-width:620px;font-size:13px;
  color:#231F20;font-variant-numeric:tabular-nums;}
.bau-detail-table th {position:sticky;top:0;z-index:1;background:#EFF4F0;color:#3C5142;
  text-align:left;padding:10px 11px;white-space:nowrap;font-weight:700;border-bottom:1px solid #DCE6DF;}
.bau-detail-table td {padding:10px 11px;border-bottom:1px solid #EDF0EC;white-space:nowrap;
  cursor:text;user-select:text !important;-webkit-user-select:text !important;}
.bau-detail-table tbody tr:nth-child(even) td {background:#FAFBFA;}
.bau-detail-table tbody tr:last-child td {border-bottom:none;}
.bau-detail-table .bau-copy-id {cursor:text;user-select:all !important;
  -webkit-user-select:all !important;white-space:pre;}
.bau-detail-table ::selection {background:#B3E6D8;color:#16271F;}
</style>
<div class="bau-detail-scroll" role="region" aria-label="Selectable employee details" tabindex="0">
<table class="bau-detail-table"><thead><tr>""" + head + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"


def detail_frame_html(frame: Any) -> str:
    """Accept Polars or another dataframe that supports iter_rows(named=True)."""
    return selectable_detail_html(frame.columns, frame.iter_rows(named=True))
