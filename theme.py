THEME_CSS = """
<style>
:root {
    --bau-bg: #F6F7F5;
    --bau-card: #FFFFFF;
    --bau-text: #231F20;
    --bau-muted: #65716A;
    --bau-border: #E2E7E3;
    --bau-accent: #008A71;
    --bau-font: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}
.stApp { background: var(--bau-bg); font-family: var(--bau-font); }
/* Streamlit's top navigation/toolbar is fixed. Keep the page heading BELOW
   its hit area instead of pushing it underneath with a negative margin. */
[data-testid="stMain"] .block-container {
    box-sizing: border-box;
    max-width: 1500px;
    padding: 4.65rem clamp(1.1rem, 2.1vw, 2.25rem) 2.2rem !important;
}
[data-testid="stSidebar"] { border-right: 1px solid var(--bau-border); }
[data-testid="stSidebar"] .block-container { padding-top: 1.35rem; }
.bau-brand { font-size: 1.08rem; line-height: 1.35; font-weight: 750;
    color: var(--bau-text); margin: .4rem 0 1.05rem; }
.bau-nav-caption { color: var(--bau-muted); font-size: .72rem;
    letter-spacing: .10em; font-weight: 750; margin: .55rem 0 .25rem; }
/* Sidebar WORKSPACE is a genuine menu of buttons, without radio indicators.
   Scope all styling to this container to leave other app buttons unchanged. */
[data-testid="stSidebar"] .st-key-bau_workspace_nav { margin-top: .2rem; }
[data-testid="stSidebar"] .st-key-bau_workspace_nav [data-testid="stVerticalBlock"] { gap: .16rem; }
[data-testid="stSidebar"] .st-key-bau_workspace_nav [data-testid="stButton"] button {
    display: flex; justify-content: flex-start; width: 100%;
    min-height: 2.45rem; padding: .48rem .78rem; text-align: left;
    border: 1px solid transparent; border-radius: 9px;
    background: transparent; color: #385248; box-shadow: none;
    font-size: .94rem; font-weight: 580;
    transition: background-color .12s ease, color .12s ease;
}
[data-testid="stSidebar"] .st-key-bau_workspace_nav [data-testid="stButton"] button p {
    text-align: left; line-height: 1.3; margin: 0;
}
[data-testid="stSidebar"] .st-key-bau_workspace_nav [data-testid="stButton"] button:hover {
    background: #EDF5EF; color: #135D4D;
}
[data-testid="stSidebar"] .st-key-bau_workspace_nav [data-testid="stButton"] button[kind="primary"] {
    background: #DDEDE5; border-color: #D4E7DC;
    color: #135D4D; font-weight: 700;
}
[data-testid="stSidebar"] .st-key-bau_workspace_nav [data-testid="stButton"] button:focus-visible {
    outline: 2px solid var(--bau-accent); outline-offset: 2px;
}
.bau-page-header { position: relative; z-index: 0; width: 100%;
    max-width: 100%; min-width: 0; padding: .1rem 0 .75rem;
    margin: 0 0 1.05rem; overflow-wrap: anywhere; }
.bau-title { font-family: var(--bau-font); font-size: clamp(1.5rem, 2.3vw, 2rem);
    line-height: 1.2; font-weight: 760; letter-spacing: -.025em;
    color: var(--bau-text); margin: 0; }
.bau-subtitle { font-size: .96rem; line-height: 1.5; color: var(--bau-muted);
    margin: .45rem 0 0; }
.bau-section-title { font-family: var(--bau-font); font-size: 1.17rem;
    line-height: 1.35; font-weight: 720; color: var(--bau-text);
    margin: .35rem 0 .3rem; }
[data-testid="stMetric"] { background: var(--bau-card);
    border: 1px solid var(--bau-border); border-radius: 12px;
    padding: .65rem .85rem; }
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--bau-card);
    border-color: var(--bau-border) !important; border-radius: 14px; }
hr { border-color: var(--bau-border); }
@media (max-width: 768px) {
    /* The native hamburger button remains usable without covering the title. */
    [data-testid="stMain"] .block-container { padding: 5rem 1rem 2rem !important; }
    .bau-page-header { margin-bottom: .85rem; }
    .bau-title { font-size: 1.55rem; }
    .bau-subtitle { font-size: .89rem; }
    .bau-section-title { font-size: 1.05rem; }
}
@media (prefers-reduced-motion: reduce) {
    [data-testid="stSidebar"] .st-key-bau_workspace_nav [data-testid="stButton"] button { transition: none; }
}
/* Scoped landing styles. No change to analytics charts or site mapping. */
.bau-empty-state {
  text-align: center; padding: 4.1rem 1.6rem 1.15rem;
  background: radial-gradient(ellipse at 50% 0%, #EDF5EF 0%, #fff 62%);
  border-radius: 15px;
}
.bau-empty-icon {
  display: grid; place-items: center; width: 72px; height: 72px;
  margin: 0 auto 1.5rem; border-radius: 20px; background: #E4F1EA;
  color: var(--bau-accent); font-size: 2.4rem; font-weight: 700;
  border: 1px solid #D3E6DB;
}
.bau-empty-eyebrow { font-size: .74rem; letter-spacing: .12em; font-weight: 750;
  color: var(--bau-accent); margin-bottom: .85rem; }
.bau-empty-title { font-size: clamp(1.55rem, 2.5vw, 2.1rem); line-height: 1.3;
  font-weight: 750; letter-spacing: -.025em; color: var(--bau-text);
  margin: 0 auto .85rem; max-width: 630px; }
/* Explicitly center the upload instruction paragraph, even when Streamlit
   supplies its own Markdown paragraph alignment styles. */
.bau-empty-state p.bau-empty-description { color: var(--bau-muted); font-size: 1rem;
  line-height: 1.7; max-width: 620px; margin: 0 auto;
  text-align: center !important; }
.bau-empty-tags { display: flex; align-items: center; justify-content: center;
  flex-wrap: wrap; gap: .55rem; margin: 1.4rem auto .8rem; }
.bau-empty-tags span { border: 1px solid var(--bau-border); border-radius: 999px;
  background: white; color: #526158; padding: .35rem .8rem;
  font-size: .83rem; font-weight: 600; }
.bau-empty-footnote { color: var(--bau-muted); font-size: .83rem;
  text-align: center; padding: 1.2rem 0 2rem; }

</style>
"""
