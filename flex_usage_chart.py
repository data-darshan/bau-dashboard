"""Direct-click, site-colored stacked Flex-used bars (Streamlit components v2).

Each site keeps its existing dashboard base color. The three usage states use
progressively darker shades of that same site color. Only exception segments
(Onboarded & Not Punched and Not Onboarded) emit click events; the compliant
Onboarded & Punched segment is intentionally display-only.
"""
from __future__ import annotations

import json

import streamlit as st

_HTML = """
<div class="bau-flex-chart" aria-label="Flex used by site">
  <div class="bau-flex-legend" aria-label="Flex usage legend">
    <span><i class="light"></i>Onboarded &amp; Punched</span>
    <span><i class="mid"></i>Onboarded &amp; Not Punched</span>
    <span><i class="dark"></i>Not Onboarded</span>
  </div>
  <div class="bau-flex-scroll" aria-label="Scroll horizontally for additional sites">
    <svg class="bau-flex-svg" role="group" aria-label="Flex usage stacked bars by site"></svg>
  </div>
  <div class="bau-flex-tooltip" role="tooltip" aria-hidden="true"></div>
</div>
"""

_CSS = """
.bau-flex-chart {position:relative;width:100%;box-sizing:border-box;font-family:inherit;
  padding:2px 2px 0;color:var(--st-text-color,#231F20);}
.bau-flex-legend {display:flex;gap:14px;justify-content:center;align-items:center;flex-wrap:wrap;
  font-size:11px;color:var(--st-secondary-text-color,#68756D);margin:0 0 2px;}
.bau-flex-legend span {display:inline-flex;align-items:center;gap:5px;}
.bau-flex-legend i {display:inline-block;width:10px;height:10px;border-radius:2px;background:#8FA49A;}
.bau-flex-legend i.light {opacity:.32}.bau-flex-legend i.mid {opacity:.62}.bau-flex-legend i.dark {opacity:1}
.bau-flex-scroll {width:100%;max-width:100%;overflow-x:auto;overflow-y:hidden;box-sizing:border-box;scrollbar-width:thin;}
.bau-flex-svg {height:350px;max-width:none;display:block;overflow:visible;}
.bau-flex-axis {fill:var(--st-secondary-text-color,#758179);font-size:11px;}
.bau-flex-total {fill:var(--st-text-color,#231F20);font-size:11px;font-weight:650;}
.bau-flex-grid {stroke:var(--st-border-color,#EDF1ED);stroke-width:1px;}
.bau-flex-baseline {stroke:var(--st-border-color,#D9E1DA);stroke-width:1.2px;}
.bau-flex-segment.clickable {cursor:pointer;transition:opacity .14s;}
.bau-flex-segment.clickable:hover {opacity:.82;}
/* Browsers often add a dark focus/selection stroke after a click. Keep the
   bars flat and clean without disabling keyboard use or focus tooltips. */
.bau-flex-segment {stroke:none !important;stroke-width:0 !important;
  outline:none !important;-webkit-tap-highlight-color:transparent;}
.bau-flex-segment.clickable:focus,
.bau-flex-segment.clickable:focus-visible,
.bau-flex-segment.clickable:active {stroke:none !important;outline:none !important;
  box-shadow:none !important;}
.bau-flex-segment.clickable:focus-visible {opacity:.82;}
.bau-flex-tooltip {display:none;position:absolute;z-index:2;background:var(--st-background-color,#fff);
  color:var(--st-text-color,#231F20);border:1px solid var(--st-border-color,#E2E7E3);
  box-shadow:0 4px 13px rgba(0,0,0,.12);border-radius:6px;padding:8px 10px;font-size:12px;
  pointer-events:none;white-space:pre-line;min-width:135px;max-width:240px;}
@media (prefers-reduced-motion:reduce) {.bau-flex-segment.clickable {transition:none;}}
"""

_JS = r"""
export default function(component) {
  const { parentElement, data, setTriggerValue } = component;
  const root = parentElement.querySelector('.bau-flex-chart');
  if (!root) return;
  const scroll = root.querySelector('.bau-flex-scroll');
  const svg = root.querySelector('.bau-flex-svg');
  const tooltip = root.querySelector('.bau-flex-tooltip');
  if (!scroll || !svg || !tooltip) return;
  const NS = 'http://www.w3.org/2000/svg';
  const create = (tag, attrs, textValue) => {
    const node = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, String(value));
    if (textValue !== undefined) node.textContent = String(textValue);
    return node;
  };
  const safe = value => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
  const rows = (Array.isArray(data?.rows) ? data.rows : []).filter(r => r && r.site_key && r.site);
  const viewportW = Math.max(520, scroll.clientWidth || 760);
  const w = Math.max(viewportW, rows.length * 74 + 95);
  const h = 350, left = 48, right = 20, top = 32, bottom = 83;
  const plotH = h-top-bottom, plotW = w-left-right, bottomY = top+plotH;
  const mx = Math.max(1, ...rows.map(r => safe(r.total)));
  const step = Math.max(1, Math.ceil(mx / 5));
  const yMax = Math.max(1, step * Math.ceil(mx / step));
  const y = value => bottomY - safe(value) * plotH / yMax;
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.style.width = `${w}px`;
  svg.replaceChildren();

  for (let value=0; value<=yMax; value+=step) {
    const pos = y(value);
    svg.appendChild(create('line',{x1:left,y1:pos,x2:w-right,y2:pos,class:'bau-flex-grid'}));
    svg.appendChild(create('text',{x:left-8,y:pos+4,class:'bau-flex-axis','text-anchor':'end'},value));
  }
  svg.appendChild(create('line',{x1:left,y1:bottomY,x2:w-right,y2:bottomY,class:'bau-flex-baseline'}));
  svg.appendChild(create('text',{x:14,y:top+plotH/2,class:'bau-flex-axis','text-anchor':'middle',
    transform:`rotate(-90 14 ${top+plotH/2})`},'People'));

  const slotW = plotW / Math.max(1, rows.length), barW = Math.min(46, slotW*.68);
  const showTooltip = (event,row,label,count,clickable) => {
    tooltip.textContent = `${row.site}\n${label}: ${Math.round(count).toLocaleString('en-IN')}\nTotal Flex Used: ${Math.round(safe(row.total)).toLocaleString('en-IN')}${clickable?'\nClick for employee details':''}`;
    tooltip.style.display='block'; tooltip.setAttribute('aria-hidden','false');
    const rect=root.getBoundingClientRect();
    let x=(event.clientX||rect.left+rect.width/2)-rect.left+12;
    const tw=Math.min(245,tooltip.offsetWidth||190); if(x+tw>rect.width)x=Math.max(5,rect.width-tw-5);
    tooltip.style.left=`${Math.max(5,x)}px`;
    tooltip.style.top=`${Math.max(35,(event.clientY||rect.top+100)-rect.top-52)}px`;
  };
  const hideTooltip=()=>{tooltip.style.display='none';tooltip.setAttribute('aria-hidden','true');};
  rows.forEach((row,i)=>{
    const cx=left+slotW*(i+.5), total=safe(row.total);
    const values=[safe(row.onboarded_punched),safe(row.onboarded_not_punched),safe(row.not_onboarded)];
    const labels=['Onboarded & Punched','Onboarded & Not Punched','Not Onboarded'];
    const colors=[row.light,row.medium,row.dark];
    let accumulated=0;
    values.forEach((count,index)=>{
      if(count<=0){ accumulated += count; return; }
      const start=accumulated, end=accumulated+count;
      const topY=y(end), height=Math.max(0,y(start)-y(end));
      const clickable=index>0;
      const rect=create('rect',{x:cx-barW/2,y:topY,width:barW,height,
        fill:colors[index]||'#6B8F80',rx: index===2 ? 2 : 0,
        class:`bau-flex-segment${clickable?' clickable':''}`,
        tabindex:clickable?'0':'-1',role:clickable?'button':'img',
        'aria-label':`${row.site}: ${labels[index]} ${Math.round(count)}${clickable?'. Open details':''}`});
      rect.appendChild(create('title',{},`${row.site} — ${labels[index]}: ${Math.round(count)}`));
      if(clickable){
        const open=()=>setTriggerValue('selection',JSON.stringify({site_key:row.site_key,segment:labels[index]}));
        rect.addEventListener('click',open);
        rect.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});
      }
      rect.addEventListener('pointermove',e=>showTooltip(e,row,labels[index],count,clickable));
      rect.addEventListener('pointerleave',hideTooltip);
      rect.addEventListener('focus',e=>{const b=rect.getBoundingClientRect();showTooltip({clientX:b.left+b.width/2,clientY:b.top},row,labels[index],count,clickable);});
      rect.addEventListener('blur',hideTooltip);
      svg.appendChild(rect); accumulated=end;
    });
    const totalY = total>0 ? Math.max(top+9,y(total)-8) : bottomY-8;
    svg.appendChild(create('text',{x:cx,y:totalY,class:'bau-flex-total','text-anchor':'middle'},Math.round(total)));
    const ly=bottomY+14;
    svg.appendChild(create('text',{x:cx,y:ly,class:'bau-flex-axis','text-anchor':'end',
      transform:`rotate(-35 ${cx} ${ly})`},row.site));
  });
}
"""

_FLEX_CHART = st.components.v2.component(
    name="bau_flex_usage_site_stack_v1", html=_HTML, css=_CSS, js=_JS,
)


def render_flex_usage_chart(rows: list[dict]) -> dict | None:
    result = _FLEX_CHART(
        key="main_flex_usage_site_stack_v1",
        data={"rows": rows},
        on_selection_change=lambda: None,
    )
    selection = result.selection
    if not isinstance(selection, str):
        return None
    try:
        payload = json.loads(selection)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
