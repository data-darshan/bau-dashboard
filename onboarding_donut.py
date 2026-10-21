"""Stable, directly clickable Aadhaar/Manual donut.

Streamlit components v2 render inline without the legacy chart-event iframe.
This prevents the loading skeleton that previously flashed whenever the
legacy component was assigned a new key after a slice click.

Only aggregated chart counts are sent to the browser. Detail retrieval remains
in the existing Streamlit onboarding_method_dialog() function.
"""
from __future__ import annotations

import streamlit as st


_HTML = """
<div class="bau-method-donut" aria-label="Aadhaar versus Manual onboarding chart">
  <div class="bau-method-heading">Aadhaar vs Manual</div>
  <div class="bau-method-figure">
    <svg class="bau-method-ring" viewBox="0 0 320 250" role="group"
         aria-label="Click a donut segment to open its onboarding summary">
      <circle class="bau-method-track" cx="160" cy="125" r="87" />
      <g class="bau-method-slices"></g>
      <text class="bau-method-center-label" x="160" y="119" text-anchor="middle">Total onboardings</text>
      <text class="bau-method-center-total" x="160" y="145" text-anchor="middle"></text>
    </svg>
  </div>
  <div class="bau-method-legend" aria-label="Onboarding methods"></div>
</div>
"""

_CSS = """
.bau-method-donut { width:100%; box-sizing:border-box; min-height:347px;
  color:var(--st-text-color,#231F20); overflow:visible; padding:0 8px 6px; }
.bau-method-heading { font-size:17px; font-weight:650; line-height:1.4;
  margin:3px 0 5px; text-align:center; }
.bau-method-figure { display:flex; justify-content:center; align-items:center; height:260px; }
.bau-method-ring { max-width:330px; width:100%; height:250px;
  overflow:visible; user-select:none; }
.bau-method-track { fill:none; stroke:#EDF2EC; stroke-width:54px; }
.bau-method-slice { fill:none; stroke-width:54px; stroke-linecap:butt;
  cursor:pointer; outline:none; transform-origin:160px 125px;
  transform:rotate(-90deg); transition:stroke-opacity .15s ease, filter .15s ease; }
.bau-method-slice:hover, .bau-method-slice:focus-visible {
  stroke-opacity:.86; filter:drop-shadow(0 0 2px rgba(0,0,0,.20)); }
.bau-method-slice:focus-visible { stroke-width:57px; }
.bau-method-center-label { font-size:11px; fill:var(--st-secondary-text-color,#65716A); }
.bau-method-center-total { font-size:23px; font-weight:700;
  fill:var(--st-text-color,#231F20); }
.bau-method-legend { display:flex; justify-content:center; align-items:center;
  flex-wrap:wrap; gap:8px 22px; padding:1px 0 6px; }
.bau-method-key { display:inline-flex; align-items:center; gap:7px; cursor:pointer;
  border-radius:6px; padding:5px; font-size:13px; line-height:1.4;
  color:var(--st-text-color,#231F20); outline:none; }
.bau-method-key:hover { background:rgba(127,140,160,.09); }
.bau-method-key:focus-visible { outline:2px solid var(--st-primary-color,#008A71); }
.bau-method-dot { width:10px; height:10px; border-radius:50%; display:inline-block;
  flex-shrink:0; }
.bau-method-value { color:var(--st-secondary-text-color,#65716A); font-variant-numeric:tabular-nums; }
@media (prefers-reduced-motion:reduce) {
  .bau-method-slice { transition:none; }
}
"""

_JS = r"""
export default function(component) {
  const { parentElement, data, setTriggerValue } = component;
  const root = parentElement.querySelector('.bau-method-donut');
  if (!root) return;
  const layer = root.querySelector('.bau-method-slices');
  const legend = root.querySelector('.bau-method-legend');
  const totalLabel = root.querySelector('.bau-method-center-total');
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const COLOR = { Aadhar: '#008A71', Manual: '#D5D226' };
  const LABEL = { Aadhar: 'Aadhaar', Manual: 'Manual' };
  const r = 87;
  const circumference = 2 * Math.PI * r;

  // Only numeric, aggregated report totals are accepted. No raw HTML is used.
  const safeCount = value => {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? Math.round(n) : 0;
  };
  const items = [
    { method: 'Aadhar', count: safeCount(data?.aadhar) },
    { method: 'Manual', count: safeCount(data?.manual) }
  ];
  const total = items.reduce((acc, item) => acc + item.count, 0);
  totalLabel.textContent = total.toLocaleString('en-IN');
  layer.replaceChildren();
  legend.replaceChildren();

  const open = method => setTriggerValue('method', method);
  const attachActions = (el, method) => {
    el.addEventListener('click', () => open(method));
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        open(method);
      }
    });
  };
  // Use at least one decimal for BOTH shares. Whole-number rounding can
  // falsely show 100% Aadhaar alongside a non-zero Manual share. If a very
  // small positive share would round to 0.0% (or its partner to 100.0%),
  // increase precision for both to keep the displayed split truthful.
  let decimals = 1;
  const partial = items.filter(item => item.count > 0 && item.count < total);
  while (decimals < 10 && partial.some(item => {
    const rounded = Number((item.count / total * 100).toFixed(decimals));
    return rounded <= 0 || rounded >= 100;
  })) decimals++;
  let progress = 0;
  items.forEach(item => {
    const fraction = total ? item.count / total : 0;
    const share = fraction * circumference;
    const percentage = (fraction * 100).toFixed(decimals);

    if (item.count > 0) {
      const arc = document.createElementNS(SVG_NS, 'circle');
      arc.setAttribute('cx','160');
      arc.setAttribute('cy','125');
      arc.setAttribute('r', String(r));
      arc.setAttribute('class', 'bau-method-slice');
      arc.setAttribute('stroke', COLOR[item.method]);
      arc.setAttribute('stroke-dasharray', `${share} ${circumference - share}`);
      arc.setAttribute('stroke-dashoffset', String(-progress * circumference));
      arc.setAttribute('role', 'button');
      arc.setAttribute('tabindex', '0');
      arc.setAttribute('aria-label', `${LABEL[item.method]}: ${item.count.toLocaleString('en-IN')} onboardings, ${percentage} percent. Open HR-by-site summary`);
      const title = document.createElementNS(SVG_NS, 'title');
      title.textContent = `${LABEL[item.method]}: ${item.count.toLocaleString('en-IN')} (${percentage}%)`;
      arc.appendChild(title);
      attachActions(arc, item.method);
      layer.appendChild(arc);
    }
    // The visual legend belongs to the chart (not extra action buttons below).
    // The legend is also clickable so a very narrow Manual slice remains usable.
    const key = document.createElement('span');
    key.className = 'bau-method-key';
    const dot = document.createElement('span');
    dot.className = 'bau-method-dot';
    dot.style.backgroundColor = COLOR[item.method];
    const name = document.createElement('span');
    name.textContent = LABEL[item.method];
    const value = document.createElement('span');
    value.className = 'bau-method-value';
    value.textContent = `${percentage}%`;
    key.append(dot, name, value);
    if (item.count) {
      key.setAttribute('role','button');
      key.setAttribute('tabindex','0');
      key.setAttribute('aria-label', `Open ${LABEL[item.method]} HR-by-site summary`);
      attachActions(key, item.method);
    } else {
      key.style.opacity = '.5';
      key.setAttribute('aria-disabled','true');
      key.style.cursor = 'default';
    }
    legend.appendChild(key);
    progress += fraction;
  });
}
"""

# Register once at import time; mount calls below reuse the same DOM identity.
_DONUT = st.components.v2.component(
    name="bau_onboarding_method_donut",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


def render_onboarding_donut(aadhar: int, manual: int) -> str | None:
    """Render a stable donut; return method only for a fresh slice click.

    V2 trigger values are ephemeral and fire even for repeat clicks on the same
    segment. Keeping the key stable means no iframe reset/loading skeleton.
    """
    result = _DONUT(
        key="main_onboarding_donut",
        data={"aadhar": int(aadhar), "manual": int(manual)},
        on_method_change=lambda: None,
    )
    method = result.method
    return method if method in {"Aadhar", "Manual"} else None
