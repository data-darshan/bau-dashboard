# Architecture and product contract

## Components

- `app.py`: Streamlit navigation, Settings, shared filters, dialogs, event queue and render orchestration.
- `parsers.py`: detects the workbook domain from sheet names, extracts date/site metrics and required employee drill-down details. A successful import atomically replaces the prior snapshot **for that domain only**; an invalid workbook does not clear the existing snapshot.
- `db.py`: SQLite schema, session-specific in-memory URI, query helpers and the independent site metadata registry.
- `onboarding_breakdown.py`: reconciles HR/site Aadhaar vs Manual counts to the official summary and holds the derived count records in session state, never in JSON files.
- `site_palette.py`: 64 approved site colors plus permanent, unique new-site allocations in the site metadata registry.
- Chart/table helpers: `onboarding_donut.py`, `onboarding_red_chart.py`, `attendance_hf_table.py`, `selectable_detail_table.py`, `roster_layers.py`, `chart_formatting.py`, `flex_metrics.py`, `flex_usage_chart.py`.

## Storage boundary

`st.session_state` holds the SQLite shared-memory URI and an open anchor connection. All `db.py` report helpers access that URI. It is unique per browser session and persists through Streamlit reruns, but is not durable across browser sessions or server restarts.

`data/site_settings.db` is a separate, small **disk** SQLite registry holding only `site_mapping` and `site_color_mapping`. The application seeds existing regions into that registry and refreshes the session DB mapping from it. Import-discovered sites are added without overwriting admin-assigned regions. Changes from Settings and generated colors are saved only in this registry. The original historic report database must not be copied here.

## Import behavior

1. Show a progress bar with current-file and real parsing-stage captions; read workbook into memory and detect report type.
2. Parse summary plus attendance/onboarding/flex detail. Reject reports with no usable summary before changing existing data.
3. Begin a SQLite transaction; clear previous *same-domain* summary, detail and one-entry import record; insert replacement rows and derived Attendance Single Punch %; commit once.
4. Register newly discovered site names and persistent colors in the metadata registry.
5. For Onboarding only, derive HR/site counts and retain the result in session state. If that validation fails, clear the old HR breakdown and show a warning instead of presenting mismatched history.
6. Streamlit releases the workbook buffers; closing the session removes the remaining report data.

The last uploaded file of each report type wins. If the latest workbook itself contains several reporting dates, those dates remain available for charts and filters; **other prior uploads are not merged**.

## Dashboard constraints (Flex updated 19 Oct 2026)

- Shared filters: date range, region, DC/XD and site. Blank Region means all for general graphs; blank DC/XD means both.
- Onboarding: Aadhaar/Manual donut with HR/site counts; Hyperverge RED bars with person-level detail.
- Attendance: four metrics (`8 Hrs + Adherence`, `5 to 8 Hrs Adherence`, `<5 Hrs Adherence`, `Single Punch %`) with the existing comparison and exception drill-down rules.
- Roster: Active HC, Rostered HC and Roster Match site-colored bars, without person-level drill-down. Two rounded-percentage labels (Roster Adoption and Roster Adherence) now **read the report's imported official percentage metrics directly** rather than recalculating them from counts. The original report defines Adoption as Rostered / Active and Adherence as Matched / Rostered; charts use the reported values even if the numbers ever differ from those ratios. Labels sit at the bottom of the corresponding bars (a below-baseline gutter for short bars). The percentages never alter counts or bar heights; missing official percentages render as an em dash.
- Flex Used: either a Region **or** at least one explicitly selected Site is required to draw the site-wise stacked bars; with neither selected a prompt asks to select a region or facilities. Regions can be blank when individual/multiple sites are chosen. The Flex Used single-day picker remains, scoped by Common date range, region/type/site; exception dialogs use the same selected day. Onboarded & Punched is non-clickable; the other segments open exception tables. Dark segment focus strokes are disabled while keyboard activation and hover details remain available.
- Flex Working Hours: always an Attendance-style date-wise line chart with clickable markers. No dedicated single-day selector, trend checkbox, or site pagination is used. Common date range/region/type/site still control the available series. Only site/date pairs with `flex_usage` **Total Flex Used > 0** are shown: a 100% official working percentage without corresponding Flex usage is not a real observation; a missing or zero usage date is omitted and adjacent plotted points connect directly. The official `8 Hrs+ Adherence` still drives 8+ hours; HF/MIS/SP counts are divided by `Total Punched`; an unknown denominator is omitted, never 0%. Site/date count popups and 8-hour comparisons operate on plotted days only. Detail excludes PT and the special zero-hour Bucket `-` MIS rows.
- `Hyderabad REV DC` detail aliases to `Hyderabad DC` for Flex popup reconciliation.
- Dialogs continue using the pending-payload session-state pattern. Read-only employee drill-downs render HTML tables with browser-native text selection and full-ID selection (`user-select:all`) instead of an interactive cell-selecting grid; HTML special characters are escaped. Settings mapping editors remain interactive.
- Percentages on the Aadhaar/Manual donut are shown with one decimal by default for both categories, increasing precision when a nonzero slice would otherwise appear as 0% or its counterpart as 100%. The raw integer onboarding counts and summary/details are unchanged.
- Removed low-value per-section "Data available through" captions. The import progress caption is deliberately retained because it communicates an active operation.

## Browser acceptance checklist (still pending)

Upload one workbook of each type. Check the Settings progress bar and its changing caption, Dashboard/Settings navigation, filters, site colors, onboarding percentages (including 99.4/0.6) and RED click, native full-ID selection/Ctrl+C in every read-only employee popup, Attendance point-click and CSV, Roster chart, Flex Used single-day selector and region-or-site gate, flat bar clicks without border, and Flex Working Hours always-on trend with zero-usage days omitted plus all four metrics and their dialogs. Re-upload an older-date workbook of one type and confirm its prior-date data disappear while the other three types remain; refresh Streamlit's browser session and verify the dashboard returns to the upload invitation. Confirm admin region edits and auto-assigned site colors survive a new session. Confirm **no** `data/dashboard.db`, count-history JSON or other personal-data files are created on disk.

## Manager updates and base-report status (17 October 2026)

- Streamlit's fixed toolbar is given clearance above the main heading and the sidebar uses responsive initial state. Dashboard, Settings and placeholder titles share one semantic header helper and a consistent typographic scale.
- The reusable `chart_formatting.py` builds hover templates that round the **display** percentage to whole numbers on Attendance and the Flex Working Hours trend. Roster hover uses the same whole-percent display. Onboarding's percentage-precision guard remains unchanged.
- The original official source counts, percentage scale normalization, detail eligibility rules and site identity/color rules are preserved. The Roster Adherence denominator is corrected to match the uploaded report and the parser no longer keeps out-of-report employee-base rows. All four uploaded BAU files have been reconciled with the in-memory import; only the real Streamlit browser acceptance test remains.
- Browser QA of an isolated representative HTML/Plotly chart was performed at 1440px, 1050px, 760px and 390px viewport widths. This is a **component-level** test; a full Streamlit acceptance and source-workbook numeric reconciliation are still required.
- See `docs/MANAGER_REVIEW_AND_BASE_RECONCILIATION.md` for the complete acceptance protocol.

### Source workbook reconciliation (17 October 2026)

The official Roster summary uses two different percentage denominators: Adoption = Rostered HC / Active HC; Adherence = Roster Match / Rostered HC. `roster_layers.py` now matches both ratios while bars continue showing raw Active/Rostered/Matched headcounts.

The Attendance, Flex and Onboarding base-detail importers now only retain records whose date/site can be displayed by a corresponding official summary sheet. This prevents a newer, partially populated employee-base date and unrelated/future/historical Flex base rows from extending the import-history range or accumulating in the ephemeral employee tables. Summary metrics are imported from the official report sheets without rescaling their counts or changing their source-defined percentage formulas. See `RECONCILIATION_17OCT2026.md`.

## WORKSPACE menu and reported Roster percent UX (17 Oct 2026)

- WORKSPACE uses a Streamlit sidebar container with six real full-width buttons rather than `st.radio`; the `nav_page` session key remains the single source of routing. Callback `navigate_to()` executes before rerun and changes the active item styling. CSS styles are scoped to `st-key-bau_workspace_nav`, leaving other actions untouched. Focus-visible styling supports keyboard users. The previous fixed-toolbar-safe top padding is unchanged.
- `app.py -> render_roster()` must query all five metrics: `Active HC`, `Rostered HC`, `Roster Match`, `Roster Adoption`, and `Roster Adherence`. `roster_layers.roster_coverage_rows()` accepts the official percentages as stored with unit `percent` by the Roster parser (`percent_scale='points'`). Do not recompute chart % values from counts. A missing/non-finite official value is displayed as missing, not zero.
- Roster percentages use Excel-style round-half-up when converted to **display text only**. The same rounded text appears on the chart and in Plotly hover. Raw percent values remain unchanged in the report data. The three actual count bar heights and count labels remain unchanged.
- The 17 October workbook was checked independently: 912 non-total site/day Adherence metrics from `DC Summary` / `XD Summary` match the dedicated Adherence tabs without mismatches. The workbook also contains 32 grand-total cells excluded by the parser.
