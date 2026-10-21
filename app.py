from __future__ import annotations

import gc
import hashlib
from datetime import date
from html import escape
from pathlib import Path

import polars as pl
import plotly.express as px
import streamlit as st

from db import (
    REGIONS,
    attendance_detail_for,
    clear_session_reports,
    coerce_date,
    available_sites,
    flex_detail_for,
    flex_working_detail_for,
    get_date_bounds,
    get_import_history,
    get_latest_by_section,
    get_site_mapping,
    infer_facility_type,
    init_db,
    init_site_registry,
    new_session_database,
    refresh_sites_from_registry,
    save_discovered_sites_to_registry,
    normalize_site,
    onboarding_red_for,
    query_summary,
    save_site_mapping,
    seed_region_mapping,
    upsert_sites,
)
from parsers import process_workbook
from onboarding_breakdown import import_hr_site_counts, query_hr_site_counts
from onboarding_donut import render_onboarding_donut
from onboarding_red_chart import render_hyperverge_red_chart
from attendance_hf_table import attendance_hf_html, attendance_hf_csv, partition_5_to_8_hour_rows
from flex_usage_chart import render_flex_usage_chart
from selectable_detail_table import detail_frame_html
from flex_metrics import (
    FLEX_WORKING_OPTIONS,
    derive_flex_working_metric,
    flex_working_on_used_days,
    flex_site_shades,
    flex_source_metrics,
)
from roster_layers import roster_coverage_rows, roster_grouped_figure, roster_page
from chart_formatting import percentage_hover_template
from metric_mappings import source_count_metric
from site_palette import site_color_map, ensure_site_colors
from theme import THEME_CSS

ROOT = Path(__file__).resolve().parent
SETTINGS_DB_PATH = ROOT / "data" / "site_settings.db"

from config import REGION_SEED
st.set_page_config(page_title="BAU Management Dashboard", page_icon="📊", layout="wide", initial_sidebar_state="auto")
st.markdown(THEME_CSS, unsafe_allow_html=True)

# Streamlit reruns app.py on UI events. This private SQLite anchor survives
# reruns but not the end of the browser session. No BAU reports are disk-backed.
if "_session_db_uri" not in st.session_state:
    uri, anchor = new_session_database()
    st.session_state["_session_db_uri"] = uri
    st.session_state["_session_db_anchor"] = anchor
DB_PATH = st.session_state["_session_db_uri"]

# The *only* durable database stores site/region metadata and site colors.
init_site_registry(SETTINGS_DB_PATH)
seed_region_mapping(SETTINGS_DB_PATH, REGION_SEED)
init_db(DB_PATH)
refresh_sites_from_registry(DB_PATH, SETTINGS_DB_PATH)
ensure_site_colors(SETTINGS_DB_PATH)

if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0
if "last_imports" not in st.session_state:
    st.session_state.last_imports = []
if "pending_dialog" not in st.session_state:
    st.session_state.pending_dialog = None
# A new browser session begins empty by design; no report data is loaded from
# previous sessions. Only site metadata survives across browser sessions.
if "dashboard_uploaded_this_session" not in st.session_state:
    st.session_state.dashboard_uploaded_this_session = False
if "onboarding_counts" not in st.session_state:
    st.session_state.onboarding_counts = []


def edit_polars_frame(frame: pl.DataFrame, **kwargs) -> pl.DataFrame:
    """Edit Polars rows through the supported Arrow-in/Arrow-out Streamlit path."""
    return pl.from_arrow(st.data_editor(frame.to_arrow(), **kwargs))


def pivot_site_metrics(frame: pl.DataFrame, metrics: list[str]) -> pl.DataFrame:
    """Sum site/metric rows across selected days, filling absent metrics with 0."""
    pivoted = frame.pivot(
        on="metric", index=["site_key", "site"],
        values="value", aggregate_function="sum",
    )
    missing = [name for name in metrics if name not in pivoted.columns]
    if missing:
        pivoted = pivoted.with_columns([pl.lit(0.0).alias(name) for name in missing])
    return pivoted.with_columns([pl.col(name).fill_null(0.0) for name in metrics]).sort(["site_key", "site"])


def fmt_date(d):
    if not d:
        return "—"
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.strftime("%d %b %Y")


def render_page_header(title: str, subtitle: str | None = None) -> None:
    """Main heading stays below native Streamlit navigation at every width."""
    summary = f'<p class="bau-subtitle">{escape(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f'<header class="bau-page-header"><h1 class="bau-title">{escape(title)}</h1>'
        f'{summary}</header>',
        unsafe_allow_html=True,
    )


def hyperverge_red_direct_payload(site_key, rows: list[dict], dfrom, dto):
    """Resolve a v3 direct SVG click to the original employee-detail dialog.

    Match by site key, never by position, rounded count, or display name.
    No chart selection state is retained after the click.
    """
    if not site_key:
        return None
    selected = next(
        (row for row in rows if row["site_key"] == str(site_key)), None,
    )
    if selected is None:
        return None
    return {
        "kind": "hyperverge", "site": selected["site"],
        "site_key": selected["site_key"], "count": selected["count"],
        "from": dfrom, "to": dto,
    }


def set_pending_once(chart_key: str, event, payload_builder):
    try:
        points = event.selection.points
    except Exception:
        points = []
    if not points:
        return
    p = points[0]
    token = f"{chart_key}:{p.get('curve_number')}:{p.get('point_number')}:{p.get('x')}:{p.get('y')}:{p.get('customdata')}"
    state_key = f"handled_{chart_key}"
    if st.session_state.get(state_key) == token:
        return
    st.session_state[state_key] = token
    st.session_state.pending_dialog = payload_builder(p)


def chart_point_count(section: str, data_date: date, site_key: str, metric: str, filters) -> float | None:
    """Look up the official count for the exact selected site/date/chart metric.

    Percentages belong to the chart point; this queries the original count
    metric from the same workbook, never derives or rounds the headcount.
    """
    source_metric = source_count_metric(section, metric)
    if source_metric is None:
        return None
    _from, _to, regions, types, _site_keys = filters
    rows = query_summary(
        DB_PATH, section, data_date, data_date, regions, types,
        [site_key], [source_metric],
    )
    if rows.is_empty():
        return None
    return float(rows.row(0, named=True)["value"])


@st.dialog("Attendance detail", width="large")
def attendance_dialog(payload):
    site = payload["site"]
    data_date = date.fromisoformat(payload["date"])
    metric = payload["metric"]
    value = payload["value"]
    count = payload.get("count")
    st.markdown(f"### {site}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Date", fmt_date(data_date))
    c2.metric(metric, f"{value:.1f}%")
    c3.metric("Count", "—" if count is None else f"{int(count):,}")

    if metric == "8 Hrs + Adherence":
        comp = payload.get("comparison", {})
        st.markdown("#### Selected-range comparison")
        a, b, c, d = st.columns(4)
        a.metric("Period average", f"{comp.get('average', 0):.1f}%")
        b.metric("Highest", f"{comp.get('high', 0):.1f}%", fmt_date(comp.get("high_date")))
        c.metric("Lowest", f"{comp.get('low', 0):.1f}%", fmt_date(comp.get("low_date")))
        delta = comp.get("from_start")
        d.metric("Vs first date", "—" if delta is None else f"{delta:+.1f} pp")
        return

    status_map = {
        "5 to 8 Hrs Adherence": "HF",
        "<5 Hrs Adherence": "MIS",
        "Single Punch %": "SP",
    }
    status = status_map.get(metric)
    if not status:
        st.info("This metric currently has count-level detail only. Employee drill-down is not configured for it.")
        return
    detail = attendance_detail_for(DB_PATH, data_date, payload["site_key"], status)
    if detail.is_empty():
        st.info("No employee records were found for this point.")
    else:
        label = {"HF": "5 to 8 Hours", "MIS": "Less than 5 Hours", "SP": "Single Punch"}[status]
        st.markdown(f"#### {label} employees ({len(detail):,})")
        if status == "HF":
            # Presentation-only: the database query already selects the
            # chart point's site, date, and HF status. It exposes
            # working_hours (actual), NOT total_hours.
            near, remaining = partition_5_to_8_hour_rows(detail.iter_rows(named=True))
            st.html(attendance_hf_html(near, remaining))
            # Keep the same five columns in an unformatted, downloadable
            # employee table. Color is deliberately never added to the CSV.
            safe_site = "".join(c if c.isalnum() and c.isascii() else "_" for c in site).strip("_")[:55]
            st.download_button(
                "Download 5 to 8 Hours table (CSV)",
                data=attendance_hf_csv(near, remaining),
                file_name=f"attendance_5_to_8_{safe_site or 'site'}_{data_date.isoformat()}.csv",
                mime="text/csv",
                width="stretch",
            )
        else:
            st.html(detail_frame_html(detail))


@st.dialog("Hyperverge RED", width="large")
def hyperverge_dialog(payload):
    st.markdown(f"### {payload['site']}")
    c1, c2 = st.columns(2)
    c1.metric("Selected period", f"{fmt_date(payload['from'])} → {fmt_date(payload['to'])}")
    c2.metric("Hyperverge RED", f"{int(payload['count']):,}")
    detail = onboarding_red_for(DB_PATH, payload["from"], payload["to"], payload["site_key"])
    if detail.is_empty():
        st.info("No Hyperverge RED detail rows were found for this bar.")
    else:
        st.markdown("#### Onboarding records")
        st.html(detail_frame_html(detail))


@st.dialog("Aadhaar / Manual onboarding by Site HR and site", width="large")
def onboarding_method_dialog(payload):
    method = payload["method"]
    label = "Aadhaar" if method == "Aadhar" else "Manual"
    st.markdown(f"### {label} onboarding — HR-by-site summary")
    c1, c2 = st.columns(2)
    c1.metric("Date range", f"{fmt_date(payload['from'])} → {fmt_date(payload['to'])}")
    c2.metric(f"Total {label} onboarding", f"{payload['count']:,}")
    try:
        detail = query_hr_site_counts(
            st.session_state.onboarding_counts, payload["from"], payload["to"], method,
            payload["regions"], payload["types"], payload["site_keys"],
            get_site_mapping(DB_PATH),
        )
    except (ValueError, OSError) as exc:
        st.error(f"Cannot read the HR/site breakdown: {exc}")
        return
    if detail.is_empty():
        st.info(
            "No HR-by-site breakdown is available for this selection yet. "
            "Upload the relevant Onboarding report in Settings to generate it."
        )
        return
    detail = detail.with_columns(pl.col("Count").cast(pl.Int64))
    total = int(detail["Count"].sum() or 0)
    st.html(detail_frame_html(detail.rename({"Count": f"{label} onboarding count"})))
    st.markdown(f"**Total shown in table: {total:,}**")
    if total != payload["count"]:
        st.warning(
            f"The HR/site breakdown totals {total:,}, but the official chart totals "
            f"{payload['count']:,}. Re-upload the matching Onboarding report(s) "
            "from Settings to refresh the date range."
        )


def queue_onboarding_dialog(method, mix, filters):
    dfrom, dto, regions, types, site_keys = filters
    count = int(round(float(
        mix.filter(pl.col("metric") == method).get_column("value").sum() or 0
    )))
    st.session_state.pending_dialog = {
        "kind": "onboarding_method", "method": method, "count": count,
        "from": dfrom, "to": dto, "regions": list(regions), "types": list(types),
        "site_keys": list(site_keys),
    }


@st.dialog("Flex detail", width="large")
def flex_dialog(payload):
    st.markdown(f"### {payload['site']}")
    c1, c2 = st.columns(2)
    c1.metric("Selected period", f"{fmt_date(payload['from'])} → {fmt_date(payload['to'])}")
    c2.metric(payload["segment"], f"{int(payload['count']):,}")
    detail = flex_detail_for(DB_PATH, payload["from"], payload["to"], payload["site_key"], payload["segment"])
    if detail.is_empty():
        st.info("No person-level Flex records were found for this segment.")
    else:
        st.html(detail_frame_html(detail))
        optional = [name for name in ("Phone Number", "Aadhaar Number", "HR") if name in detail.columns]
        if optional and all(
            detail.get_column(name).fill_null("").cast(pl.String).str.strip_chars().eq("").all()
            for name in optional
        ):
            st.caption(
                "Phone/Aadhaar/HR are optional fields from Central Flex Base. "
                "If blank, please check whether these columns exist in the uploaded workbook."
            )


@st.dialog("Flex working-hours detail", width="large")
def flex_working_dialog(payload):
    site = payload["site"]
    data_date = date.fromisoformat(payload["date"])
    metric = payload["metric"]
    value = payload["value"]
    count = payload.get("count")
    st.markdown(f"### {site}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Date", fmt_date(data_date))
    c2.metric(metric, f"{value:.1f}%")
    c3.metric("Count", "—" if count is None else f"{int(count):,}")

    if metric == "8 Hrs + Adherence":
        comp = payload.get("comparison", {})
        st.markdown("#### Selected-range comparison")
        a, b, c, d = st.columns(4)
        a.metric("Period average", f"{comp.get('average', 0):.1f}%")
        b.metric("Highest", f"{comp.get('high', 0):.1f}%", fmt_date(comp.get("high_date")))
        c.metric("Lowest", f"{comp.get('low', 0):.1f}%", fmt_date(comp.get("low_date")))
        delta = comp.get("from_start")
        d.metric("Vs first date", "—" if delta is None else f"{delta:+.1f} pp")
        return

    status_map = {
        "5 to 8 Hrs Adherence": "HF",
        "<5 Hrs Adherence": "MIS",
        "Single Punch %": "SP",
    }
    punch_code = status_map.get(metric)
    if not punch_code:
        st.info("This metric currently has count-level detail only.")
        return
    detail = flex_working_detail_for(DB_PATH, data_date, payload["site_key"], punch_code)
    if detail.is_empty():
        st.info("No Flex employee records were found for this point.")
    else:
        label = {"HF": "5 to 8 Hours", "MIS": "Less than 5 Hours", "SP": "Single Punch"}[punch_code]
        st.markdown(f"#### {label} Flex employees ({len(detail):,})")
        st.html(detail_frame_html(detail))


def render_filters():
    mn, mx = get_date_bounds(DB_PATH)
    if not mn:
        st.info("No dashboard data has been imported yet. Go to Settings → Data Import.")
        return None
    with st.container(border=True):
        st.markdown("**Common filters**")
        c1, c2, c3, c4 = st.columns([1.5, 1.8, 1.2, 2.2])
        with c1:
            # A newly imported report can extend the date bounds. Using the
            # available bounds in the key refreshes the initial full range.
            dr = st.date_input(
                "Date range", value=(mn, mx), min_value=mn, max_value=mx,
                key=f"main_date_range_{mn.isoformat()}_{mx.isoformat()}_v2",
            )
            # Streamlit date-range input can temporarily return a 1-item tuple
            # while the user is choosing the end date. Never pass that tuple
            # into the database layer. Treat a single selected date as a
            # one-day range until the second date is selected.
            if isinstance(dr, (list, tuple)):
                if len(dr) >= 2:
                    dfrom, dto = dr[0], dr[-1]
                elif len(dr) == 1:
                    dfrom = dto = dr[0]
                else:
                    dfrom, dto = mn, mx
            else:
                dfrom = dto = dr
        with c2:
            region = st.selectbox(
                "Region", ["North", "South", "East", "West"],
                index=None, placeholder="All regions", key="main_region_single_v2",
            )
            regions = [region] if region else []
        with c3:
            st.caption("Facility type (leave blank for both)")
            dc = st.checkbox("DC", value=False, key="main_dc_blank_v2")
            xd = st.checkbox("XD", value=False, key="main_xd_blank_v2")
            # Neither checked = no type restriction (both types included).
            types = (["DC"] if dc else []) + (["XD"] if xd else [])
        sites_df = available_sites(DB_PATH, regions, types)
        with c4:
            # An HR/site selection from North must not remain applied if the
            # user switches to South or changes the DC/XD scope.
            site_scope = (region, tuple(types))
            if st.session_state.get("_site_scope_v2") != site_scope:
                st.session_state["main_sites_blank_v2"] = []
                st.session_state["_site_scope_v2"] = site_scope
            options = sites_df.get_column("site").to_list() if not sites_df.is_empty() else []
            selected_sites = st.multiselect(
                "Site", options, placeholder="All available sites",
                key="main_sites_blank_v2",
            )
        key_map = {r["site"]: r["site_key"] for r in sites_df.iter_rows(named=True)}
        site_keys = [key_map[site] for site in selected_sites if site in key_map]
    return dfrom, dto, regions, types, site_keys


def filtered(section, filters, metrics=None):
    dfrom, dto, regions, types, site_keys = filters
    return query_summary(DB_PATH, section, dfrom, dto, regions, types, site_keys or None, metrics)


def select_report_day(frame: pl.DataFrame, label: str, key: str):
    """Single-day picker shared with Roster and Flex Used.

    Never retain an invalid date when the shared filters or a fresh upload
    change the available dates. Default to the most recent in-scope report day.
    """
    days = sorted(frame.get_column("data_date").unique().to_list()) if not frame.is_empty() else []
    if not days:
        return None
    if st.session_state.get(key) not in days:
        st.session_state[key] = days[-1]
    return st.selectbox(label, days, format_func=fmt_date, key=key)


def page_site_rows(rows: list[dict], requested_page: int, page_size: int = 10):
    """Present daily working-hours data legibly when many sites are in scope."""
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    ordered = sorted(rows, key=lambda row: (str(row["site"]).casefold(), str(row["site_key"])))
    pages = max(1, (len(ordered) + page_size - 1) // page_size)
    index = max(0, min(int(requested_page), pages - 1))
    return ordered[index * page_size:(index + 1) * page_size], index, pages


def hyperverge_bar_colors(counts):
    """Return lighter reds for lower visible case counts and darker for higher."""
    values = [float(count) for count in counts]
    if not values:
        return []
    minimum, maximum = min(values), max(values)
    # When every site has one case, use a gentle light red. With identical
    # higher counts, use a consistent middle red; never imply a distinction.
    positions = [
        (value - minimum) / (maximum - minimum)
        if maximum > minimum else (0.0 if maximum <= 1 else 0.55)
        for value in values
    ]
    return px.colors.sample_colorscale(["#FCA5A5", "#991B1B"], positions)


def render_hyperverge_empty_state(has_report):
    """Friendly no-results card in place of an empty or zero-only bar chart."""
    if has_report:
        heading = "No Hyperverge RED cases"
        message = "No Hyperverge RED cases found for the selected filters."
        supporting = "Try another date range, region, facility type or site."
    else:
        heading = "Hyperverge RED data not available"
        message = "Upload an Onboarding report to see Hyperverge RED cases."
        supporting = "Your other dashboard charts remain available."
    st.markdown(
        # The chart wrapper needs a REAL bottom gap after this white card.
        # Inner padding/box-sizing alone does not preserve that gap under
        # browser zoom in the Streamlit border container.
        '<div style="width:100%;max-width:100%;min-height:300px;'
        'box-sizing:border-box;display:flex;flex-direction:column;'
        'align-items:center;justify-content:center;text-align:center;'
        'padding:20px 16px;border-radius:14px;background:#ffffff;">'
        '<div style="font-weight:700;font-size:20px;color:#231F20;'
        'margin-bottom:16px;">Hyperverge RED</div>'
        '<div style="width:58px;height:58px;border-radius:50%;background:#EDF5EF;'
        'border:1px solid #D3E6DB;color:#008A71;display:flex;align-items:center;'
        'justify-content:center;font-size:27px;margin-bottom:17px;">&#10003;</div>'
        f'<div style="font-size:17px;font-weight:700;color:#231F20;">{heading}</div>'
        f'<div style="color:#526158;margin-top:7px;">{message}</div>'
        f'<div style="color:#829087;font-size:13px;margin-top:10px;">{supporting}</div>'
        '</div>'
        # A sibling spacer participates in normal document flow, so the
        # border wrapper grows BELOW the rounded white card rather than
        # ending flush with (or beneath) its bottom corners.
        '<div aria-hidden="true" style="height:18px;width:100%;'
        'flex-shrink:0;pointer-events:none;"></div>',
        unsafe_allow_html=True,
    )


def render_onboarding_empty_state(has_report):
    """Fit a clear Aadhaar/Manual no-data message inside the donut chart card."""
    if has_report:
        heading = "No onboardings found"
        message = "No Aadhaar or Manual onboardings were recorded for the selected filters."
        supporting = "Try another date range, region, facility type or site."
    else:
        heading = "Aadhaar / Manual data not available"
        message = "Upload an Onboarding report to view Aadhaar and Manual onboardings."
        supporting = "Your other dashboard charts remain available."
    st.markdown(
        '<div style="width:100%;max-width:100%;min-height:335px;'
        'box-sizing:border-box;display:flex;flex-direction:column;'
        'align-items:center;justify-content:center;text-align:center;'
        'padding:18px 14px;border-radius:14px;background:#ffffff;'
        'overflow-wrap:break-word;">'
        '<div style="font-weight:700;font-size:20px;color:#231F20;'
        'margin-bottom:16px;">Aadhaar vs Manual</div>'
        '<div style="width:56px;height:56px;flex-shrink:0;border-radius:50%;'
        'background:#EDF5EF;border:1px solid #D3E6DB;color:#008A71;'
        'display:flex;align-items:center;justify-content:center;'
        'font-size:27px;margin-bottom:16px;">&#8212;</div>'
        f'<div style="font-size:17px;font-weight:700;color:#231F20;">{heading}</div>'
        f'<div style="color:#526158;margin-top:7px;">{message}</div>'
        f'<div style="color:#829087;font-size:13px;margin-top:10px;">{supporting}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_onboarding(filters, latest):
    st.markdown('<div class="bau-section-title">Onboarding</div>', unsafe_allow_html=True)
    left, right = st.columns([1, 1.65])
    with left:
        with st.container(border=True):
            df = filtered("onboarding_aadhar", filters, ["Aadhar", "Manual"])
            if df.is_empty():
                # No matching report rows for these filters.  Keep the donut
                # panel consistent with the Hyperverge no-cases treatment.
                render_onboarding_empty_state(bool(latest.get("onboarding_aadhar")))
            else:
                mix = df.group_by("metric").agg(pl.col("value").sum())
                aadhar_count = int(round(float(
                    mix.filter(pl.col("metric") == "Aadhar").get_column("value").sum() or 0
                )))
                manual_count = int(round(float(
                    mix.filter(pl.col("metric") == "Manual").get_column("value").sum() or 0
                )))
                if aadhar_count <= 0 and manual_count <= 0:
                    # Covers a real report with explicit zero counts; no
                    # empty ring, duplicate buttons or misleading slice.
                    render_onboarding_empty_state(bool(latest.get("onboarding_aadhar")))
                else:
                    # Keep the existing direct-click SVG and dialog for every
                    # selection with at least one positive onboarding count.
                    method = render_onboarding_donut(aadhar_count, manual_count)
                    if method:
                        queue_onboarding_dialog(method, mix, filters)
    with right:
        with st.container(border=True):
            df = filtered("onboarding_hyperverge", filters, ["RED Cases"])
            agg = (
                df.group_by(["site_key", "site"])
                .agg(pl.col("value").sum())
                .sort(["value", "site_key", "site"], descending=[True, False, False])
                .filter(pl.col("value") > 0)
                if not df.is_empty()
                else pl.DataFrame(schema={"site_key": pl.String, "site": pl.String, "value": pl.Float64})
            )
            # A facility with zero RED cases must not occupy a bar or an
            # X-axis label. This applies for every combination of filters.
            if agg.is_empty():
                render_hyperverge_empty_state(bool(latest.get("onboarding_hyperverge")))
            else:
                # Direct-click SVG uses the same Streamlit components-v2
                # event mechanism as the working Aadhaar/Manual donut.
                # Plotly point *selection* did not reliably fire on a normal
                # bar click; do not use selection_mode or key cycling here.
                colors = hyperverge_bar_colors(agg["value"])
                rows = [
                    {
                        "site": row["site"], "site_key": row["site_key"],
                        "count": int(round(float(row["value"]))),
                        "color": color,
                    }
                    for row, color in zip(agg.iter_rows(named=True), colors)
                ]
                clicked_site_key = render_hyperverge_red_chart(rows)
                if clicked_site_key is not None:
                    dfrom, dto, *_ = filters
                    payload = hyperverge_red_direct_payload(
                        clicked_site_key, rows, dfrom, dto,
                    )
                    if payload is not None:
                        # Identical popup/data query to the existing version.
                        # Unlike Plotly selection, v2 trigger events are fresh
                        # even when the same bar is clicked repeatedly.
                        st.session_state.pending_dialog = payload


def render_attendance(filters, latest):
    st.markdown('<div class="bau-section-title">Attendance</div>', unsafe_allow_html=True)
    with st.container(border=True):
        # Four approved attendance metrics. All plot in percentages.
        attendance_options = [
            "8 Hrs + Adherence", "5 to 8 Hrs Adherence",
            "<5 Hrs Adherence", "Single Punch %",
        ]
        if st.session_state.get("attendance_metric") not in (None, *attendance_options):
            st.session_state["attendance_metric"] = attendance_options[0]
        metric = st.selectbox(
            "Attendance metric",
            attendance_options,
            index=0,
            key="attendance_metric",
        )
        df = filtered("attendance", filters, [metric])
        if df.is_empty():
            st.info("No Attendance data for this selection.")
            return
        fig = px.line(df, x="data_date", y="value", color="site", markers=True, custom_data=["site_key", "site", "metric"], color_discrete_map=site_color_map(df.get_column("site").unique().to_list(), db_path=SETTINGS_DB_PATH), labels={"data_date": "Date", "value": "%", "site": "Site"})
        fig.update_traces(hovertemplate=percentage_hover_template(metric))
        fig.update_yaxes(range=[0, 100], ticksuffix="%")
        fig.update_layout(title=f"{metric} trend", margin=dict(l=10, r=10, t=55, b=25), height=470, legend_title_text="Site", hovermode="closest")
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", config={"displayModeBar": False}, key="attendance_line")

        def payload(p):
            custom = p.get("customdata") or []
            site_key = custom[0] if len(custom) > 0 else ""
            site = custom[1] if len(custom) > 1 else ""
            clicked_metric = custom[2] if len(custom) > 2 else metric
            clicked_date = coerce_date(p.get("x"))
            value = float(p.get("y") or 0)
            count = chart_point_count("attendance", clicked_date, site_key, clicked_metric, filters)
            comparison = {}
            if clicked_metric == "8 Hrs + Adherence":
                sdf = df.filter(pl.col("site_key") == site_key).sort("data_date")
                if not sdf.is_empty():
                    # Break ties by earlier date, as pandas idxmax/idxmin did.
                    high_row = sdf.sort(["value", "data_date"], descending=[True, False]).row(0, named=True)
                    low_row = sdf.sort(["value", "data_date"]).row(0, named=True)
                    first = float(sdf.row(0, named=True)["value"])
                    comparison = {
                        "average": float(sdf["value"].mean()), "high": float(high_row["value"]), "high_date": high_row["data_date"],
                        "low": float(low_row["value"]), "low_date": low_row["data_date"], "from_start": value - first,
                    }
            return {"kind": "attendance", "site_key": site_key, "site": site, "date": clicked_date.isoformat(), "metric": clicked_metric, "value": value, "count": count, "comparison": comparison}
        set_pending_once("attendance_line", event, payload)


def render_roster(filters, latest):
    st.markdown('<div class="bau-section-title">Roster</div>', unsafe_allow_html=True)
    with st.container(border=True):
        # The common date/region/type/site filters still scope this report;
        # this section-only selector chooses exactly one available roster day.
        records = filtered("roster", filters, ["Active HC", "Rostered HC", "Roster Match", "Roster Adoption", "Roster Adherence"])
        if records.is_empty():
            st.info("No Roster data for this selection.")
            return
        heading, picker = st.columns([3.5, 1.35], vertical_alignment="bottom")
        with heading:
            st.markdown("**Roster Adoption vs Roster Adherence**")
        with picker:
            selected_day = select_report_day(records, "Roster date", "roster_single_day")
        if selected_day is None:
            st.info("No Roster dates are available for these filters.")
            return
        one_day = records.filter(pl.col("data_date") == selected_day)
        chart_rows, excluded = roster_coverage_rows(one_day.iter_rows(named=True))
        if chart_rows:
            # Roster-only site pages prevent unreadable, crowded numbers
            # when the common filters include all 57 sites. Every site remains
            # available; this changes presentation only, not data filtering.
            visible_rows, page_index, page_count = roster_page(
                chart_rows, st.session_state.get("roster_site_page", 0), page_size=8,
            )
            st.session_state["roster_site_page"] = page_index
            fig = roster_grouped_figure(visible_rows, selected_day, db_path=SETTINGS_DB_PATH)
            st.plotly_chart(
                fig, width="stretch", config={"displayModeBar": False},
                key="roster_v6_fixed_site_palette_20261012",
            )
            if page_count > 1:
                prev_col, count_col, next_col = st.columns([1.5, 2.5, 1.5], vertical_alignment="center")
                with prev_col:
                    if st.button("← Previous sites", key="roster_page_previous", disabled=page_index == 0):
                        st.session_state["roster_site_page"] = page_index - 1
                        st.rerun()
                with count_col:
                    first_site = page_index * 8 + 1
                    last_site = min((page_index + 1) * 8, len(chart_rows))
                    st.markdown(f"<div style='text-align:center;color:#65716A;font-size:0.85rem'>Sites {first_site}–{last_site} of {len(chart_rows)}</div>", unsafe_allow_html=True)
                with next_col:
                    if st.button("Next sites →", key="roster_page_next", disabled=page_index == page_count - 1):
                        st.session_state["roster_site_page"] = page_index + 1
                        st.rerun()
        else:
            st.info("No valid Roster count records for the selected date.")
        if excluded:
            st.warning(
                f"{len(excluded)} site(s) are not shown because Active HC or Roster counts "
                "were missing or inconsistent: "
                + ", ".join(row["site"] for row in excluded[:12])
                + ("..." if len(excluded) > 12 else "")
            )


def render_flex_scope_prompt():
    """Offer either a Region or one or more Sites for the Flex Used chart."""
    st.markdown(
        '<div style="width:100%;max-width:100%;min-height:330px;'
        'box-sizing:border-box;display:flex;flex-direction:column;'
        'align-items:center;justify-content:center;text-align:center;'
        'padding:20px 16px;border-radius:14px;background:#ffffff;">'
        '<div style="font-weight:700;font-size:20px;color:#231F20;'
        'margin-bottom:16px;">Flex Used</div>'
        '<div style="width:58px;height:58px;border-radius:50%;background:#EDF5EF;'
        'border:1px solid #D3E6DB;color:#008A71;display:flex;align-items:center;'
        'justify-content:center;font-size:25px;margin-bottom:17px;">&#8982;</div>'
        '<div style="font-size:17px;font-weight:700;color:#231F20;">Please select a region or select facilities</div>'
        '<div style="color:#526158;margin-top:7px;">Choose a Region, or select one or more facilities in the Site filter above, to view Flex usage.</div>'
        '<div style="color:#829087;font-size:13px;margin-top:10px;">DC / XD can remain blank to include both facility types.</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_flex_usage_empty_state(has_report):
    if has_report:
        heading = "No Flex usage found"
        message = "No Flex usage records match the selected filters."
        supporting = "Try another date range, region, facility type or site."
    else:
        heading = "Flex usage data not available"
        message = "Upload a Flex report to view site-wise usage."
        supporting = "The working-hours panel will remain available when its data exists."
    st.markdown(
        '<div style="width:100%;max-width:100%;min-height:330px;'
        'box-sizing:border-box;display:flex;flex-direction:column;'
        'align-items:center;justify-content:center;text-align:center;'
        'padding:20px 16px;border-radius:14px;background:#ffffff;">'
        '<div style="font-weight:700;font-size:20px;color:#231F20;margin-bottom:16px;">Flex Used</div>'
        '<div style="width:58px;height:58px;border-radius:50%;background:#EDF5EF;'
        'border:1px solid #D3E6DB;color:#008A71;display:flex;align-items:center;'
        'justify-content:center;font-size:27px;margin-bottom:17px;">&#8212;</div>'
        f'<div style="font-size:17px;font-weight:700;color:#231F20;">{heading}</div>'
        f'<div style="color:#526158;margin-top:7px;">{message}</div>'
        f'<div style="color:#829087;font-size:13px;margin-top:10px;">{supporting}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_flex(filters, latest):
    st.markdown('<div class="bau-section-title">Flex</div>', unsafe_allow_html=True)
    _dfrom, _dto, regions, _types, site_keys = filters

    with st.container(border=True):
        usage_metrics = [
            "Total Flex Used", "Onboarded & Punched",
            "Onboarded & Not Punched", "Not Onboarded",
        ]
        # A region is optional when the user explicitly selects one or more
        # sites. Only the completely unscoped Flex Used view shows the prompt.
        if not (regions or site_keys):
            render_flex_scope_prompt()
        else:
            usage = filtered("flex_usage", filters, usage_metrics)
            if usage.is_empty():
                render_flex_usage_empty_state(bool(latest.get("flex_usage")))
            else:
                heading, picker = st.columns([3.5, 1.35], vertical_alignment="bottom")
                with heading:
                    st.markdown("**Flex Used**")
                with picker:
                    usage_day = select_report_day(usage, "Flex Used date", "flex_usage_single_day")
                # Use ONLY that date's counts, never the sum of multiple reporting
                # days. The exception dialog must use that same date for an exact
                # summary/detail reconciliation.
                if usage_day is not None:
                    one_day = usage.filter(pl.col("data_date") == usage_day)
                    pv = pivot_site_metrics(one_day, usage_metrics)
                    color_map = site_color_map(pv.get_column("site").to_list(), db_path=SETTINGS_DB_PATH)
                    rows = []
                    for row in pv.iter_rows(named=True):
                        light, medium, dark = flex_site_shades(color_map[row["site"]])
                        rows.append({
                            "site_key": row["site_key"],
                            "site": row["site"],
                            "total": float(row["Total Flex Used"] or 0),
                            "onboarded_punched": float(row["Onboarded & Punched"] or 0),
                            "onboarded_not_punched": float(row["Onboarded & Not Punched"] or 0),
                            "not_onboarded": float(row["Not Onboarded"] or 0),
                            "light": light, "medium": medium, "dark": dark,
                        })
                    selection = render_flex_usage_chart(rows)
                    if selection:
                        segment = selection.get("segment")
                        site_key = str(selection.get("site_key") or "")
                        if segment in {"Onboarded & Not Punched", "Not Onboarded"} and site_key:
                            selected = next((row for row in rows if row["site_key"] == site_key), None)
                            if selected is not None:
                                count_key = (
                                    "onboarded_not_punched"
                                    if segment == "Onboarded & Not Punched"
                                    else "not_onboarded"
                                )
                                st.session_state.pending_dialog = {
                                    "kind": "flex", "site": selected["site"],
                                    "site_key": site_key, "segment": segment,
                                    "count": selected[count_key],
                                    "from": usage_day, "to": usage_day,
                                }

    with st.container(border=True):
        if st.session_state.get("flex_working_metric") not in (None, *FLEX_WORKING_OPTIONS):
            st.session_state["flex_working_metric"] = FLEX_WORKING_OPTIONS[0]
        metric = st.selectbox(
            "Flex working-hours metric", FLEX_WORKING_OPTIONS,
            index=0, key="flex_working_metric",
        )
        raw = filtered("flex_working", filters, flex_source_metrics(metric))
        all_dates = derive_flex_working_metric(raw, metric)
        # An official 100% on a date with no Flex usage is not a meaningful
        # compliance observation. Filter PER SITE AND DATE, not by whether
        # anyone at any other site used Flex that day. Missing days are
        # omitted, so Plotly connects the neighboring observed points.
        flex_used = filtered("flex_usage", filters, ["Total Flex Used"])
        chart_data = flex_working_on_used_days(all_dates, flex_used)
        if chart_data.is_empty():
            st.info("No Flex working-hours data on dates with Flex usage for this selection.")
        else:
            fig = px.line(
                chart_data, x="data_date", y="value", color="site", markers=True,
                custom_data=["site_key", "site", "metric"],
                color_discrete_map=site_color_map(
                    chart_data.get_column("site").unique().to_list(), db_path=SETTINGS_DB_PATH,
                ),
                labels={"data_date": "Date", "value": "%", "site": "Site"},
            )
            fig.update_traces(hovertemplate=percentage_hover_template(metric))
            fig.update_yaxes(range=[0, 100], ticksuffix="%")
            fig.update_layout(
                title=f"{metric} trend", margin=dict(l=10, r=10, t=55, b=25),
                height=470, legend_title_text="Site", hovermode="closest",
            )
            event = st.plotly_chart(
                fig, width="stretch", on_select="rerun", selection_mode="points",
                config={"displayModeBar": False}, key="flex_working_line_v4",
            )

            def payload(p):
                custom = p.get("customdata") or []
                site_key = custom[0] if len(custom) > 0 else ""
                site = custom[1] if len(custom) > 1 else ""
                clicked_metric = custom[2] if len(custom) > 2 else metric
                clicked_date = coerce_date(p.get("x"))
                value = float(p.get("y") or 0)
                count = chart_point_count("flex_working", clicked_date, site_key, clicked_metric, filters)
                comparison = {}
                if clicked_metric == "8 Hrs + Adherence":
                    sdf = chart_data.filter(pl.col("site_key") == site_key).sort("data_date")
                    if not sdf.is_empty():
                        high_row = sdf.sort(
                            ["value", "data_date"], descending=[True, False],
                        ).row(0, named=True)
                        low_row = sdf.sort(["value", "data_date"]).row(0, named=True)
                        first = float(sdf.row(0, named=True)["value"])
                        comparison = {
                            "average": float(sdf["value"].mean()),
                            "high": float(high_row["value"]),
                            "high_date": high_row["data_date"],
                            "low": float(low_row["value"]),
                            "low_date": low_row["data_date"],
                            "from_start": value - first,
                        }
                return {
                    "kind": "flex_working", "site_key": site_key, "site": site,
                    "date": clicked_date.isoformat(), "metric": clicked_metric,
                    "value": value, "count": count, "comparison": comparison,
                }

            set_pending_once("flex_working_line_v4", event, payload)


def navigate_to(page: str):
    """Navigate from the empty-state button before the sidebar is rendered next run."""
    st.session_state.nav_page = page


def render_dashboard_empty_state():
    """Landing screen on EVERY new browser session, regardless of old DB data."""
    with st.container(border=True):
        st.markdown(
            '<div class="bau-empty-state">'
            '<div class="bau-empty-icon">&#8593;</div>'
            '<div class="bau-empty-eyebrow">BAU MANAGEMENT DASHBOARD</div>'
            '<div class="bau-empty-title">Turn your daily reports into a clearer view.</div>'
            '<p class="bau-empty-description">Please upload your reports to view '
            'the visual analysis. Add your latest Attendance, Onboarding, Roster '
            'and Flex Excel reports in Settings to unlock the dashboard.</p>'
            '<div class="bau-empty-tags">'
            '<span>Attendance</span><span>Onboarding</span>'
            '<span>Roster</span><span>Flex</span>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        _, middle, _ = st.columns([1.3, 1.4, 1.3])
        with middle:
            st.button(
                "Upload reports  →",
                type="primary",
                width="stretch",
                on_click=navigate_to,
                args=("Settings",),
                key="dashboard_empty_upload",
            )
        st.markdown(
            '<div class="bau-empty-footnote">'
            'Dashboard → Settings → Upload reports → View analysis'
            '</div>', unsafe_allow_html=True,
        )


def render_dashboard():
    render_page_header("Management Dashboard", "Interactive management view from normalized BAU report data.")
    # Only reports uploaded in this browser session may unlock the dashboard.
    # Closing the session discards all report/employee rows automatically.
    if (not st.session_state.dashboard_uploaded_this_session
            or get_date_bounds(DB_PATH)[0] is None):
        render_dashboard_empty_state()
        return
    filters = render_filters()
    if not filters:
        return
    latest = get_latest_by_section(DB_PATH)
    render_onboarding(filters, latest)
    st.divider()
    render_attendance(filters, latest)
    st.divider()
    render_roster(filters, latest)
    st.divider()
    render_flex(filters, latest)

    pending = st.session_state.get("pending_dialog")
    if pending:
        st.session_state.pending_dialog = None
        if pending["kind"] == "attendance":
            attendance_dialog(pending)
        elif pending["kind"] == "hyperverge":
            hyperverge_dialog(pending)
        elif pending["kind"] == "onboarding_method":
            onboarding_method_dialog(pending)
        elif pending["kind"] == "flex":
            flex_dialog(pending)
        elif pending["kind"] == "flex_working":
            flex_working_dialog(pending)


def render_placeholder(name: str):
    render_page_header(name)
    st.info(f"Dedicated {name} report requirements are intentionally on hold. This first prototype implements only the main Dashboard and Settings.")


def render_unassigned_site_panel():
    """Make report-detected unmapped sites actionable at the TOP of Settings."""
    mapping = get_site_mapping(DB_PATH)
    unassigned = mapping.filter(pl.col("Region") == "UNASSIGNED").select(
        ["site_key", "Site", "Type", "Region"]
    )
    if unassigned.is_empty():
        return

    count = len(unassigned)
    st.warning(
        f"**{count} site{'s' if count != 1 else ''} need a region.** "
        "Assign each site below so regional dashboard analysis includes it correctly."
    )
    with st.container(border=True):
        st.markdown("#### Unassigned sites")
        st.caption("Site names and facility type (DC/XD) are detected from the reports. "
                   "Choose North, South, East or West for each site, then save. "
                   "You can leave a site UNASSIGNED until its region is confirmed.")
        # Reset table edit state when the set of unassigned sites changes (e.g.,
        # after importing new reports or saving some assignments).
        identity = "|".join(sorted(unassigned["site_key"].cast(pl.String).to_list()))
        table_id = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
        edited = edit_polars_frame(
            unassigned,
            width="stretch",
            hide_index=True,
            disabled=["site_key", "Site", "Type"],
            column_config={
                "site_key": None,
                "Site": st.column_config.TextColumn("Site"),
                "Type": st.column_config.TextColumn("DC / XD"),
                "Region": st.column_config.SelectboxColumn(
                    "Assign region", options=REGIONS, required=True
                ),
            },
            key=f"unassigned_mapping_{table_id}",
        )
        to_save = edited.filter(pl.col("Region").is_in(["North", "South", "East", "West"]))
        if st.button(
            "Save region assignments",
            type="primary",
            disabled=to_save.is_empty(),
            key="save_unassigned_regions",
        ):
            save_site_mapping(SETTINGS_DB_PATH, to_save)
            refresh_sites_from_registry(DB_PATH, SETTINGS_DB_PATH)
            st.rerun()


def render_settings():
    render_page_header("Settings", "Admin-level report import and site-to-region configuration.")

    # Warning and actionable region mapping must be visible without scrolling.
    # After the importer reruns, newly detected sites immediately appear here.
    render_unassigned_site_panel()

    st.markdown("### Data Import")
    st.caption("Reports and employee records exist only in this browser session's memory. Each new report replaces the previous upload of the same type. Only site/region settings and site colors are saved permanently.")
    files = st.file_uploader(
        "Upload Attendance / Onboarding / Roster / Flex report(s)",
        type=["xlsx"], accept_multiple_files=True,
        key=f"report_upload_{st.session_state.upload_key}",
    )
    if st.button("Process uploaded reports", type="primary", disabled=not files):
        results = []
        file_total = len(files)
        progress_bar = st.progress(0, text=f"Processing 0 of {file_total} reports")
        progress_caption = st.empty()

        def update_import_progress(index: int, stage: float, file_name: str, message: str) -> None:
            # Stages are emitted by the actual parser/importer; progress is
            # proportional to report FILES, not fabricated per-row timing.
            percentage = min(100, max(0, round(100 * (index + stage) / file_total)))
            progress_bar.progress(
                percentage,
                text=f"Processing report {index + 1} of {file_total} · {percentage}%",
            )
            progress_caption.caption(f"{file_name} · {message}")

        for index, f in enumerate(files):
            update_import_progress(index, 0, f.name, "Reading uploaded file into memory")
            try:
                blob = f.getvalue()
                def parser_progress(stage: float, message: str) -> None:
                    update_import_progress(index, stage, f.name, message)
                result = process_workbook(blob, f.name, str(DB_PATH), progress=parser_progress)
                update_import_progress(index, 0.90, f.name, "Registering site/region mappings and colors")
                save_discovered_sites_to_registry(DB_PATH, SETTINGS_DB_PATH)
                refresh_sites_from_registry(DB_PATH, SETTINGS_DB_PATH)
                ensure_site_colors(SETTINGS_DB_PATH)
                breakdown_note = ""
                if result["report_type"] == "Onboarding":
                    update_import_progress(index, 0.94, f.name, "Building Aadhaar/Manual HR-by-site breakdown")
                    st.session_state.onboarding_counts = []
                    try:
                        breakdown = import_hr_site_counts(blob)
                        st.session_state.onboarding_counts = breakdown
                        breakdown_note = f" · {len(breakdown):,} HR/site groups loaded"
                    except Exception as hr_exc:
                        breakdown_note = " · HR/site breakdown needs attention"
                        st.warning(f"Onboarding report imported, but HR/site breakdown was not refreshed: {hr_exc}")
                update_import_progress(index, 0.99, f.name, "Finishing and releasing temporary workbook buffers")
                results.append({
                    "File": f.name, "Report": result["report_type"],
                    "From": result["min_date"], "To": result["max_date"],
                    "Summary rows": result["summary_rows"], "Detail rows": result["detail_rows"],
                    "Status": "Imported" + breakdown_note,
                })
                del blob
                gc.collect()
            except Exception as exc:
                results.append({
                    "File": f.name, "Report": "—", "From": "—", "To": "—",
                    "Summary rows": 0, "Detail rows": 0, "Status": f"ERROR: {exc}",
                })
                st.error(f"{f.name}: {exc}")
            finally:
                update_import_progress(index, 1, f.name, "Report processed; moving to the next file" if index + 1 < file_total else "All files processed")
        imported = sum(row["Status"].startswith("Imported") for row in results)
        st.session_state.last_import_summary = (imported, file_total - imported)
        st.session_state.last_imports = results
        if imported:
            st.session_state.dashboard_uploaded_this_session = True
        st.session_state.upload_key += 1
        gc.collect()
        st.rerun()

    summary = st.session_state.get("last_import_summary")
    if summary:
        succeeded, failed = summary
        if failed:
            st.warning(f"Processed {succeeded + failed} report(s): {succeeded} imported, {failed} failed. Check the details below.")
        else:
            st.success(f"All {succeeded} report(s) imported into this session.")

    if st.session_state.last_imports:
        st.dataframe(pl.DataFrame(st.session_state.last_imports), width="stretch", hide_index=True)

    history = get_import_history(DB_PATH, 4)
    if not history.is_empty():
        with st.expander("Currently loaded reports (this session only)"):
            st.dataframe(history, width="stretch", hide_index=True)

    if st.button("Clear report data from this session", key="clear_session_reports"):
        clear_session_reports(DB_PATH)
        st.session_state.onboarding_counts = []
        st.session_state.last_imports = []
        st.session_state.last_import_summary = None
        st.session_state.pending_dialog = None
        st.session_state.dashboard_uploaded_this_session = False
        st.session_state.upload_key += 1
        st.rerun()

    st.divider()
    st.markdown("### Site / Region Mapping")
    st.caption("New sites detected during import are added as UNASSIGNED until an admin maps them.")
    mapping = get_site_mapping(DB_PATH)
    edited = edit_polars_frame(
        mapping,
        width="stretch",
        hide_index=True,
        disabled=["site_key", "Site", "Type", "updated_at"],
        column_config={
            "site_key": None,
            "updated_at": None,
            "Region": st.column_config.SelectboxColumn("Region", options=REGIONS, required=True),
        },
        key="mapping_editor",
    )
    if st.button("Save region mapping"):
        save_site_mapping(SETTINGS_DB_PATH, edited)
        refresh_sites_from_registry(DB_PATH, SETTINGS_DB_PATH)
        st.success("Region mapping saved.")
        st.rerun()

    with st.expander("Add / map a site manually"):
        with st.form("manual_site"):
            c1, c2, c3 = st.columns([2, 1, 1])
            site = c1.text_input("Site name")
            ftype = c2.selectbox("Type", ["DC", "XD"])
            region = c3.selectbox("Region", ["North", "South", "East", "West"])
            submitted = st.form_submit_button("Add site")
            if submitted and site.strip():
                upsert_sites(SETTINGS_DB_PATH, [(site.strip(), ftype, region)])
                ensure_site_colors(SETTINGS_DB_PATH, (site.strip(),))
                refresh_sites_from_registry(DB_PATH, SETTINGS_DB_PATH)
                # Explicit admin action should override UNASSIGNED/existing region.
                temp = get_site_mapping(DB_PATH)
                mask = pl.col("site_key") == normalize_site(site)
                temp = temp.with_columns(
                    pl.when(mask).then(pl.lit(region)).otherwise(pl.col("Region")).alias("Region"),
                    pl.when(mask).then(pl.lit(ftype)).otherwise(pl.col("Type")).alias("Type"),
                )
                save_site_mapping(SETTINGS_DB_PATH, temp)
                refresh_sites_from_registry(DB_PATH, SETTINGS_DB_PATH)
                st.success(f"{site.strip()} mapped to {region}.")
                st.rerun()


st.sidebar.image(str(ROOT / "assets" / "shadowfax_logo.png"), width=180)
st.sidebar.markdown('<div class="bau-brand">BAU Management</div>', unsafe_allow_html=True)
st.sidebar.markdown('<div class="bau-nav-caption">WORKSPACE</div>', unsafe_allow_html=True)
NAV_PAGES = ("Dashboard", "Onboarding", "Attendance", "Roster", "Flex", "Settings")
if st.session_state.get("nav_page") not in NAV_PAGES:
    st.session_state["nav_page"] = "Dashboard"
# Actual menu buttons (not visually hidden radio inputs). Callbacks execute
# before the Streamlit rerun, so the highlighted page stays synchronized.
with st.sidebar.container(key="bau_workspace_nav"):
    for page in NAV_PAGES:
        st.button(
            page,
            key=f"workspace_nav_{page.lower()}",
            type="primary" if page == st.session_state["nav_page"] else "secondary",
            width="stretch",
            on_click=navigate_to,
            args=(page,),
        )
menu = st.session_state["nav_page"]

if menu == "Dashboard":
    render_dashboard()
elif menu == "Settings":
    render_settings()
else:
    render_placeholder(menu)
