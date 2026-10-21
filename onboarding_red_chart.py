"""Direct-click Hyperverge RED site bars (Streamlit components v2).

Streamlit Plotly only reports *selection* events, which can fail to fire on
ordinary bar clicks depending on browser/Plotly version. The existing
Aadhaar/Manual chart already uses component-v2 click triggers successfully.
This chart uses the same supported approach to open the existing RED detail
without changing the dashboard's stored data, filtering or dialog.

Only count and site identifier/label are sent to the browser. No employee PII.
"""
from __future__ import annotations

import streamlit as st


_HTML = """
<div class="bau-red-chart" aria-label="Hyperverge RED cases by site">
  <div class="bau-red-heading">Hyperverge RED</div>
  <div class="bau-red-scroll" aria-label="Scroll horizontally for additional sites">
    <svg class="bau-red-svg" role="group" aria-label="Click a RED site bar to open its details"></svg>
  </div>
  <div class="bau-red-tooltip" role="tooltip" aria-hidden="true"></div>
</div>
"""

_CSS = """
.bau-red-chart {position:relative; width:100%; box-sizing:border-box;
  font-family:inherit; padding:2px 2px 0; color:var(--st-text-color,#231F20);}
.bau-red-heading {font-weight:650; font-size:17px; margin:6px 0 4px; text-align:center;}
.bau-red-scroll {width:100%; max-width:100%; overflow-x:auto; overflow-y:hidden;
  box-sizing:border-box; scrollbar-width:thin;}
.bau-red-svg {height:320px; max-width:none; display:block; overflow:visible;}
.bau-red-svg .bau-red-axis {fill:var(--st-secondary-text-color,#758179); font-size:11px;}
.bau-red-svg .bau-red-grid {stroke:var(--st-border-color,#EDF1ED); stroke-width:1px;}
.bau-red-svg .bau-red-baseline {stroke:var(--st-border-color,#D9E1DA); stroke-width:1.2px;}
.bau-red-bar {cursor:pointer; transition:opacity .14s;}
.bau-red-point {cursor:pointer; outline:none;}
.bau-red-point:hover .bau-red-bar {opacity:.82;}
.bau-red-point:focus-visible .bau-red-bar {stroke:var(--st-text-color,#231F20); stroke-width:2px;}
.bau-red-chart .bau-red-tooltip {display:none; position:absolute; z-index:2;
  background:var(--st-background-color,#fff); color:var(--st-text-color,#231F20);
  border:1px solid var(--st-border-color,#E2E7E3); box-shadow:0 4px 13px rgba(0,0,0,.12);
  border-radius:6px; padding:8px 10px; font-size:12px; pointer-events:none;
  white-space:pre-line; min-width:90px; max-width:220px;}
.bau-red-point text {pointer-events:none;}
@media (prefers-reduced-motion:reduce) {.bau-red-bar {transition:none;}}
"""

_JS = r"""
export default function(component) {
  const { parentElement, data, setTriggerValue } = component;
  const root = parentElement.querySelector('.bau-red-chart');
  if (!root) return;
  const scroll = root.querySelector('.bau-red-scroll');
  const svg = root.querySelector('.bau-red-svg');
  const tooltip = root.querySelector('.bau-red-tooltip');
  if (!scroll || !svg || !tooltip) return;
  const NS = 'http://www.w3.org/2000/svg';
  const create = (tag, attrs, textValue) => {
    const node = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      node.setAttribute(key, String(value));
    }
    if (textValue !== undefined) node.textContent = String(textValue);
    return node;
  };
  const rows = Array.isArray(data?.rows) ? data.rows : [];
  const points = rows.filter(r => r && typeof r.site === 'string'
    && typeof r.site_key === 'string' && r.site_key.length > 0
    && Number.isFinite(Number(r.count)) && Number(r.count) > 0);

  // Keep the old red palette. Do not use external scripts or a separate
  // Plotly selection handler; the SVG bar itself is the click target.
  const viewportW = Math.max(480, scroll.clientWidth || 680);
  const w = Math.max(viewportW, points.length * 62 + 85);
  const h = 320, left = 45, right = 17, top = 16, bottom = 79;
  const plotH = h - top - bottom;
  const plotW = w - left - right;
  const mx = Math.max(1, ...points.map(r => Math.ceil(Number(r.count))));
  const step = Math.max(1, Math.ceil(mx / 5));
  const yMax = Math.max(1, step * Math.ceil(mx / step));
  const bottomY = top + plotH;
  const y = v => bottomY - Math.max(0, Number(v)) * plotH / yMax;
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.style.width = `${w}px`;
  svg.replaceChildren();

  for (let value = 0; value <= yMax; value += step) {
    const pos = y(value);
    svg.appendChild(create('line', {x1:left, y1:pos, x2:w-right, y2:pos, class:'bau-red-grid'}));
    svg.appendChild(create('text', {x:left-8, y:pos+4, class:'bau-red-axis',
      'text-anchor':'end'}, value));
  }
  svg.appendChild(create('line', {x1:left, y1:bottomY, x2:w-right,
    y2:bottomY, class:'bau-red-baseline'}));
  svg.appendChild(create('text', {x:14,y:top+plotH/2, class:'bau-red-axis',
    'text-anchor':'middle', transform:`rotate(-90 14 ${top+plotH/2})`}, 'RED'));

  const slotW = plotW / Math.max(1, points.length);
  const barW = Math.min(43, slotW * .72);
  const showTooltip = (event, point) => {
    tooltip.textContent = `${point.site}\nRED: ${Math.round(Number(point.count)).toLocaleString('en-IN')}\nClick for onboarding records`;
    tooltip.style.display = 'block';
    tooltip.setAttribute('aria-hidden','false');
    const rect = root.getBoundingClientRect();
    let x = (event.clientX || rect.left + rect.width/2) - rect.left + 12;
    const tooltipW = Math.min(225, tooltip.offsetWidth || 180);
    if (x + tooltipW > rect.width) x = Math.max(5, rect.width - tooltipW - 5);
    tooltip.style.left = `${Math.max(5, x)}px`;
    tooltip.style.top = `${Math.max(35, (event.clientY || rect.top+100) - rect.top - 48)}px`;
  };
  const hideTooltip = () => {
    tooltip.style.display = 'none';
    tooltip.setAttribute('aria-hidden','true');
  };
  points.forEach((point, i) => {
    const cx = left + slotW * (i + .5);
    const barTop = y(point.count);
    const pointGroup = create('g', {class:'bau-red-point', role:'button', tabindex:'0',
      'aria-label':`${point.site}: ${Math.round(Number(point.count))} Hyperverge RED cases. Open details`});
    const rect = create('rect', {class:'bau-red-bar', x:cx-barW/2, y:barTop,
      width:barW, height:Math.max(0, bottomY-barTop),
      fill: /^#(?:[0-9a-f]{3}){1,2}$|^rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)$/i.test(String(point.color||''))
        ? String(point.color) : '#DC2626'});
    const nativeTitle = create('title',{}, `${point.site} — RED: ${Math.round(Number(point.count))}`);
    rect.appendChild(nativeTitle);
    pointGroup.appendChild(rect);
    const labelY = bottomY + 13;
    const label = create('text', {class:'bau-red-axis', x:cx, y:labelY,
      'text-anchor':'end',transform:`rotate(-35 ${cx} ${labelY})`}, point.site);
    // The label can also be clicked; the group represents the entire site.
    pointGroup.appendChild(label);
    const open = () => setTriggerValue('site_key', point.site_key);
    pointGroup.addEventListener('click', open);
    pointGroup.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault(); open();
      }
    });
    pointGroup.addEventListener('pointermove', event => showTooltip(event, point));
    pointGroup.addEventListener('pointerleave', hideTooltip);
    pointGroup.addEventListener('focus', event => {
      const b = rect.getBoundingClientRect();
      showTooltip({clientX:b.left+b.width/2, clientY:b.top}, point);
    });
    pointGroup.addEventListener('blur', hideTooltip);
    svg.appendChild(pointGroup);
  });
}
"""

_RED_CHART = st.components.v2.component(
    name="bau_hyperverge_red_bar_direct_v3",
    html=_HTML, css=_CSS, js=_JS,
)


def render_hyperverge_red_chart(rows: list[dict]) -> str | None:
    """Draw case-count bars and return the clicked site key (including repeats)."""
    result = _RED_CHART(
        key="main_hyperverge_red_direct_v3",
        data={"rows": rows},
        on_site_key_change=lambda: None,
    )
    selected = result.site_key
    return str(selected) if selected is not None else None
