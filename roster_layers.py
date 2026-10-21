"""ROSTER_V5_SITE_HUES: actual headcounts, true site-color shades, visible count labels.

Adoption and Roster Match occupy adjacent halves of a pale Active HC cap.
Bar heights use real headcounts, never a uniform 100% per site.
Counts retain the center position while percentages sit at the bar foot.
"""
from __future__ import annotations

import math
import re
import colorsys
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Any, Iterable, Mapping

import plotly.graph_objects as go
from site_palette import site_color_map, SITE_PALETTE_VERSION

ROSTER_VISUAL_VERSION = "ROSTER_V6_ASSIGNED_SITE_PALETTE_20261012"
REQUIRED_COUNTS = ("Active HC", "Rostered HC", "Roster Match")
OFFICIAL_PERCENTAGES = ("Roster Adoption", "Roster Adherence")


def _reported_percentage_label(value: float | None) -> str:
    """Round a source percentage for display only, using Excel-style halves-up.

    Never derive a missing percentage from a count or turn it into a false 0%.
    """
    if value is None:
        return "—"
    return f"{Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)}%"


def _finite_report_percentage(value: Any) -> float | None:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def _count_label(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


def roster_coverage_rows(metric_rows: Iterable[Mapping[str, Any]]):
    """Combine official report counts and imported percentages per site/date.

    Roster Adoption and Roster Adherence are read from the report's own
    summary metrics, never recomputed for display. Missing/non-finite reported
    percentages stay unknown while valid headcount bars remain available.
    Return (included, excluded).
    """
    by_site: dict[str, dict] = {}
    for raw in metric_rows:
        metric = raw.get("metric")
        if metric not in REQUIRED_COUNTS and metric not in OFFICIAL_PERCENTAGES:
            continue
        site_key = str(raw.get("site_key") or "").strip()
        if not site_key:
            continue
        item = by_site.setdefault(site_key, {
            "site_key": site_key, "site": str(raw.get("site") or site_key), "metrics": {},
        })
        item["metrics"][metric] = raw.get("value")

    output, excluded = [], []
    for item in sorted(by_site.values(), key=lambda r: r["site"].casefold()):
        raw_counts = item["metrics"]
        missing = [field for field in REQUIRED_COUNTS if raw_counts.get(field) is None]
        if missing:
            excluded.append({"site": item["site"], "reason": "Missing " + ", ".join(missing)})
            continue
        try:
            active, rostered, match = [float(raw_counts[name]) for name in REQUIRED_COUNTS]
        except (TypeError, ValueError):
            excluded.append({"site": item["site"], "reason": "Non-numeric roster counts"})
            continue
        if not all(map(math.isfinite, (active, rostered, match))):
            excluded.append({"site": item["site"], "reason": "Non-finite roster counts"})
            continue
        if active <= 0:
            excluded.append({"site": item["site"], "reason": "Active HC is zero or negative"})
            continue
        if match < 0 or rostered < 0 or rostered > active or match > rostered:
            excluded.append({"site": item["site"], "reason": "Roster counts are inconsistent"})
            continue
        output.append({
            "site_key": item["site_key"], "site": item["site"],
            "active_hc": active, "rostered_hc": rostered, "roster_match": match,
            "adoption_pct": _finite_report_percentage(raw_counts.get("Roster Adoption")),
            "adherence_pct": _finite_report_percentage(raw_counts.get("Roster Adherence")),
        })
    return output, excluded


def roster_page(rows: list[dict], requested_page: int, page_size: int = 8):
    """Small Roster-only batches keep numbers legible for 57-site selections.

    Sort by Active HC (largest first) so wildly different site sizes do not
    collapse most bars to a nearly invisible sliver. All sites remain reachable.
    """
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    ordered = sorted(rows, key=lambda r: (-r["active_hc"], r["site"].casefold()))
    total_pages = max(1, (len(ordered) + page_size - 1) // page_size)
    page_index = min(max(0, int(requested_page)), total_pages - 1)
    begin = page_index * page_size
    return ordered[begin:begin + page_size], page_index, total_pages


def _normal_hex(color: str) -> str:
    color = (color or "").strip()
    if re.fullmatch(r"#[a-fA-F0-9]{6}", color):
        return color.upper()
    match = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", color)
    if match:
        components = [int(c) for c in match.groups()]
        if all(0 <= value <= 255 for value in components):
            return "#" + "".join(f"{c:02X}" for c in components)
    return "#636EFA"


def pale_tint(color: str, whiteness: float) -> str:
    """Keep each site's Attendance hue; only the lightness changes."""
    base = _normal_hex(color)
    channels = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    whiteness = min(1.0, max(0.0, float(whiteness)))
    return "#" + "".join(f"{round(c + (255 - c) * whiteness):02X}" for c in channels)


def roster_site_colors(rows: list[dict], attendance_palette: Mapping[str, str] | None = None, *, db_path=None):
    """Return each site's pre-assigned color from the global Attendance/Roster map.

    The old optional argument is intentionally ignored: a stale per-chart
    color map must NEVER repaint every Roster site in the same blue shade.
    """
    return site_color_map((row["site"] for row in rows), db_path=db_path)


def site_shades(base_color: str) -> tuple[str, str, str]:
    """Pale Active HC, dark Adoption, medium Match: identical base-site hue.

    Use HLS hue-preserving lightness rather than gray transparency overlays.
    A minimum saturation keeps each bar unmistakably site-colored even on a
    pale chart background. Returns (light, dark, medium).
    """
    color = _normal_hex(base_color)
    red, green, blue = (int(color[i:i+2], 16) / 255 for i in (1, 3, 5))
    hue, _lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    saturation = max(.69, saturation)
    def shade(lightness: float) -> str:
        channels = colorsys.hls_to_rgb(hue, lightness, saturation)
        return "#" + "".join(f"{round(255*c):02X}" for c in channels)
    return shade(.87), shade(.32), shade(.52)


def _relative_luminance(color: str) -> float:
    hexcode = _normal_hex(color)
    values = [int(hexcode[i:i+2], 16) / 255 for i in (1,3,5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055)**2.4 for v in values]
    return sum(x*y for x,y in zip((.2126, .7152, .0722), linear))


def _legible_ink(bar_color: str) -> str:
    """WCAG-style choose high contrast white or deep-navy text."""
    lum = _relative_luminance(bar_color)
    ink_dark_lum = _relative_luminance('#11263B')
    contrast_white = (1.05) / (lum + .05)
    contrast_dark = (lum + .05) / (ink_dark_lum + .05)
    return '#FFFFFF' if contrast_white >= contrast_dark else '#11263B'


def _bar_label_positions(count: float, maximum: float, bar_color: str) -> dict:
    """Return separated label positions for one Roster inner bar.

    A headcount and a percentage need about 20 px of separation at a typical
    figure size. Short bars cannot fit both, so the percent moves into a
    reserved footer gutter below y=0 while the count stays centered or moves
    just above an extremely short/zero bar. Nothing alters its real height.
    """
    if maximum <= 0:
        raise ValueError("maximum must be positive")
    percent_inside = count >= maximum * 0.20
    if percent_inside:
        percentage_y = maximum * 0.046
    else:
        percentage_y = -maximum * 0.055

    if count >= maximum * 0.075:
        count_y = count * 0.58
        count_color = _legible_ink(bar_color)
    else:
        count_y = count + maximum * 0.026
        count_color = "#152945"

    # If the count would end up beside its percentage, promote the count to a
    # taller safe position; in normal bars the guard does not change anything.
    if percent_inside:
        count_y = max(count_y, percentage_y + maximum * 0.085)
    return {
        "count_y": count_y,
        "count_color": count_color,
        "percentage_y": percentage_y,
        "percentage_color": _legible_ink(bar_color) if percent_inside else "#152945",
        "percentage_inside": percent_inside,
    }


def _headcount_tick_step(maximum: float) -> float:
    """Readable integer-ish Y ticks; none appear in the negative label gutter."""
    target = max(float(maximum) / 5.0, 1.0)
    power = 10 ** math.floor(math.log10(target))
    for factor in (1, 2, 2.5, 5, 10):
        if factor * power >= target:
            return factor * power
    return 10 * power


def roster_grouped_figure(rows: list[dict], selected_day: date,
                          attendance_palette: Mapping[str, str] | None = None, *, db_path=None):
    """Actual-HC pale cap with two edge-touching Adoption and Match bars.

    All rectangle fills belong to the respective Attendance site's hue family.
    Keep the original headcount geometry and all three source counts. The
    Adoption and Adherence labels come directly from the imported report
    percentages, not a calculation from these counts. Two percentage labels
    are drawn near the bottom of their respective bars;
    small bars use an explicit below-axis gutter so percentages and headcounts
    do not collide. Hover cards round percentages to whole numbers without
    changing any stored, plotted, or drill-down values.
    """
    fig = go.Figure()
    if not rows:
        return fig

    palette = roster_site_colors(rows, db_path=db_path)
    maximum = max(row['active_hc'] for row in rows)
    top = maximum * 1.15
    bottom = -maximum * 0.13  # reserved for tiny-bar percentage labels
    backdrop_width = .83
    inner_width = .395    # adjacent halves, zero gap between adoption and match
    half_inner = inner_width / 2
    hover = (
        '<b>%{customdata[0]}</b><br>'
        'Active HC: %{customdata[1]:,.0f}<br>'
        'Rostered HC: %{customdata[2]:,.0f}<br>'
        'Roster Match: %{customdata[3]:,.0f}<br>'
        'Roster Adoption: %{customdata[4]} of Active HC<br>'
        'Roster Adherence: %{customdata[5]} of Rostered HC'
        '<extra></extra>'
    )
    percent_traces = []
    for index, row in enumerate(rows):
        site = row['site']
        active, adopted, matched = row['active_hc'], row['rostered_hc'], row['roster_match']
        original_color = palette[site]
        light, dark, medium = site_shades(original_color)
        data = [[site, active, adopted, matched,
                 _reported_percentage_label(row.get('adoption_pct')),
                 _reported_percentage_label(row.get('adherence_pct'))]]

        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode='markers', name=site,
            marker=dict(symbol='square', color=original_color, size=11),
            legendgroup=site, showlegend=True, hoverinfo='skip',
        ))
        fig.add_trace(go.Bar(
            x=[index], y=[active], width=backdrop_width,
            marker=dict(color=light, line=dict(width=0)),
            customdata=data, hovertemplate=hover,
            name=site, legendgroup=site, showlegend=False,
        ))

        for offset, count, fill, percentage in (
            (-half_inner, adopted, dark, row['adoption_pct']),
            (half_inner, matched, medium, row['adherence_pct']),
        ):
            x_pos = index + offset
            fig.add_trace(go.Bar(
                x=[x_pos], y=[count], width=inner_width,
                marker=dict(color=fill, line=dict(width=0)),
                customdata=data, hovertemplate=hover,
                name=site, legendgroup=site, showlegend=False,
            ))
            layout = _bar_label_positions(count, maximum, fill)
            # Text traces cannot be silently suppressed by Plotly's bar-fit
            # behavior. Headcounts are never replaced by computed percentages.
            font_size = 10 if len(_count_label(count)) > 4 else 11
            fig.add_trace(go.Scatter(
                x=[x_pos], y=[layout['count_y']], mode='text',
                text=[_count_label(count)], textposition='middle center',
                textfont=dict(size=font_size, color=layout['count_color']),
                name=site, legendgroup=site, showlegend=False, hoverinfo='skip',
                cliponaxis=False,
            ))
            # Add percent traces last so labels sit over the background bars.
            # Each bar owns its own percent, even when the other bar is tiny.
            percent_traces.append(go.Scatter(
                x=[x_pos], y=[layout['percentage_y']], mode='text',
                text=[_reported_percentage_label(percentage)], textposition='middle center',
                textfont=dict(size=10, color=layout['percentage_color'], family='Arial'),
                name=site, legendgroup=site, showlegend=False, hoverinfo='skip',
                cliponaxis=False,
            ))

        # Keep the Active HC label separated from any tiny inner-bar labels.
        active_label_y = max(active + maximum * .034,
                             maximum * .15 if active < maximum * .14 else 0)
        fig.add_trace(go.Scatter(
            x=[index], y=[active_label_y],
            text=[_count_label(active)], mode='text',
            textposition='middle center', textfont=dict(size=12, color='#152945'),
            name=site, legendgroup=site, showlegend=False, hoverinfo='skip',
            cliponaxis=False,
        ))

    for percentage_trace in percent_traces:
        fig.add_trace(percentage_trace)

    fig.update_layout(
        barmode='overlay',
        height=590, margin=dict(l=50, r=35, t=47, b=56),
        plot_bgcolor='#FFFFFF', paper_bgcolor='#FFFFFF',
        font=dict(color='#233550', size=12), hovermode='closest',
        legend=dict(title='Site', x=1.02, xanchor='left', y=1, yanchor='top',
                    groupclick='togglegroup', tracegroupgap=3),
    )
    fig.update_yaxes(title='Employees (headcount)', range=[bottom, top],
                     tickformat=',d', tickmode='linear', tick0=0,
                     dtick=_headcount_tick_step(maximum),
                     gridcolor='#E9EEF7', zeroline=False)
    fig.update_xaxes(title='Date', tickmode='array',
                     tickvals=[(len(rows)-1)/2],
                     ticktext=[selected_day.strftime('%d %b %Y')],
                     range=[-.52, len(rows)-.48], showgrid=False, zeroline=False)
    return fig
