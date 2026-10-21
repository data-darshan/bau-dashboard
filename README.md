# BAU Management Dashboard

Interactive Streamlit management dashboard for **Onboarding, Attendance, Roster and Flex** Excel reports. This is the clean, **session-only report data** edition of the October 2026 project.

## Run locally

Requires Python and the packages in `requirements.txt` (Streamlit ≥1.65).

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open **Settings → Data Import**, upload your `.xlsx` reports, then open **Dashboard**. The separate Onboarding, Attendance, Roster and Flex sidebar pages are still placeholders; their visualizations are all on Dashboard.

## Data retention — important

- **No historical report database ships with this application.** Uploaded XLSX files, normalized summary rows, employee details, Flex phone/Aadhaar columns and onboarding HR breakdowns are **kept in this browser session's RAM**, not saved to a report database file or JSON sidecar.
- Each successful new upload **replaces the previous upload of that report type** in the same session (last uploaded file wins for that type); other report types remain loaded. Dates within the latest uploaded workbook are available for trends and filters.
- New browser sessions begin with no report data. Closing/expiring a browser session or restarting the Streamlit server loses its uploaded data; **re-upload reports to view the dashboard again**. The Settings button **Clear report data from this session** removes it immediately.
- The sole disk database, **`data/site_settings.db`**, stores **site names, DC/XD types, region assignments and site colors only**. It holds no report metrics, employee rows or imported workbook history. Preserve it when updating the app so admin-assigned regions/colors survive.
- Uploaded report bytes may transiently reside in Streamlit uploader state and process memory during the session. Host/process logs and backups are outside this application's control; protect the environment accordingly.

**Why:** the earlier prototype bundled a 17 MB `data/dashboard.db` with older summaries and employee records, and a count-history JSON. Neither is required under this model. These artifacts have been deliberately excluded from this release. There is no automatic migration of historical reports into the clean dashboard.

## Folder tree

```text
bau_dashboard/
├── app.py                         # Streamlit entry point and pages
├── db.py                          # per-session DB, queries, admin registry access
├── parsers.py                     # workbook detection, parsing, atomic imports
├── config.py                      # region seed
├── theme.py                       # styling
├── site_palette.py                # stable site colors
├── onboarding_breakdown.py       # session-only HR/site counts
├── onboarding_donut.py            # onboarding method donut
├── onboarding_red_chart.py        # RED detail chart
├── attendance_hf_table.py        # attendance detail table
├── roster_layers.py              # roster figures
├── flex_metrics.py               # working-hours formulas and shades
├── flex_usage_chart.py           # site stacked chart
├── assets/shadowfax_logo.png
├── .streamlit/config.toml
├── data/site_settings.db          # persistent metadata ONLY
├── tests/                         # active regression tests
├── scripts/verify_package.py      # pre-shipment checks
├── docs/ARCHITECTURE.md
├── requirements.txt
└── .gitignore
```

## Flex visualization refinement (19 Oct 2026)

- **Flex Used:** when neither a Region nor any Site is selected, the first panel asks **"Please select a region or select facilities"**. Selecting a region **or** one/multiple facilities in the Site multiselect is sufficient to show site-wise stacked bars. The dedicated **Flex Used date** selector remains: it picks one actual report day within the Common date range, and exception popups use that same exact date.
- **Flex Working Hours:** always an Attendance-style multi-day **line trend with clickable markers** for all four working-hours metrics; the trend checkbox, separate single-day selector, scatter-point view and pagination are no longer presented. The **Common date range** controls the window. Roster still has its own required single-day selector.
- **Do not draw 100% for no Flex usage:** each working-hours point is displayed **only when `Total Flex Used > 0` for that same site and date**. Zero, missing or null usage dates are skipped, without replacing the source percentage or inventing 0%/100% data. The line connects directly between neighboring valid observations (for example 17 Oct to 19 Oct when 18 Oct had no Flex usage). Other sites can have valid points on a skipped site's date. Hover, click-through count, employee details and the 8-hour comparison operate on the actual plotted dates.

## Latest dashboard usability improvements (17 Oct 2026)

- **Settings → Data Import:** a visible percentage progress bar and a changing caption describe the file being opened, detected, parsed, validated, replaced in session memory, and finalized. The final result remains on Settings after the page reruns. Milestones represent completed stages, not estimated row-by-row timing.
- **Cleaner Dashboard:** removed the old "Data available through ..." captions below Onboarding, Attendance, Roster and Flex.
- **Aadhaar vs Manual:** the legend uses decimal percentages for both methods (e.g., **99.4% vs 0.6%**, not an incorrectly rounded 100%). For very small non-zero shares, both labels automatically use more decimals. The raw counts and chart drill-down totals remain unchanged.
- **Copyable employee IDs:** read-only popup tables use a selectable HTML table instead of Streamlit's cell-selecting grid. Click/double-click an identifier, then Ctrl+C (or Cmd+C) to copy it. IDs containing dashes or leading zeros stay intact. Attendance HF keeps its special green/black row grouping and CSV export.
- **Flex Used:** no dark bar border when an exception segment is clicked. A **Flex Used date** dropdown defaults to the latest date available within the common filters; displayed bars and their detail dialogs both use only that selected day. A region or one/multiple sites are required.
- **Flex Working Hours (superseded by 19 Oct update):** The single-day comparison, extra date dropdown and optional trend checkbox described in the original October 17 build have been replaced with the always-on attendance-style line trend above.
- Report data is still **session-only**. The 64 persistent site/region mappings and colors remain in `data/site_settings.db`.

## Manager review updates (17 Oct 2026)

- **Font and sizing:** unified system-safe Segoe UI / Inter / Arial typography, more readable heading hierarchy and responsive padding for compact screens.
- **Navigation / heading collision:** the standard sidebar opens automatically according to screen size instead of always forcing an expanded drawer. Main Dashboard, Settings and placeholder page headings use semantic `h1` and sit below Streamlit's fixed toolbar. WORKSPACE now uses full-width, accessible menu buttons (not visible or hidden radio controls), with a subtle active-page highlight; the navigation callback preserves session page selection.
- **Rounded hover percentages:** Attendance, Flex Working Hours (trend) and Roster hover cards display percentage values rounded to the nearest whole percent. **Stored values, plot coordinates, and drill-downs are not rounded.** Aadhaar/Manual shares deliberately retain decimals so 99.4% is not misrepresented as 100% alongside 0.6% Manual.
- **Roster percentage placement:** Roster Adoption (Rostered HC / Active HC) and Roster Adherence (Roster Match / Rostered HC) percentages are shown at the bottom center of their corresponding site bars. The original three headcounts and color rules remain intact. When a bar is too short for two labels, its percent moves into a reserved region just below the baseline; the count remains centered or sits safely above a zero/tiny bar. No percentage is used to replace or rescale the source headcount.
- **Actual base-report reconciliation completed, 17 October 2026:** checked the four supplied reports. Roster Adherence previously used `Roster Match / Active HC`, but the official report unambiguously uses `Roster Match / Rostered HC`. Fixed the formula in every bar-foot label and hover; unchanged Active HC, Rostered HC and Roster Match counts. 701 source site/date adherence values were affected. Flex, Attendance and Onboarding summaries and all eligible detail counts reconcile. See `docs/RECONCILIATION_17OCT2026.md` for counts, source anomalies and acceptance limits.

This build has not undergone a full interactive Streamlit acceptance test in the current environment, which lacks Streamlit and Polars. Browser-level inspection of an **isolated Plotly/CSS test page** has been done with synthetic counts; that does not imply full app verification.

## Test

```bash
python -m unittest discover -s tests -p "test_*.py"
python scripts/verify_package.py
```

Tests use synthetic rows/workbooks. The UI tests include executable inline-JavaScript donut checks when Node.js is available. Do not copy historical employee data into `tests/`. The ZIP is statically and DOM/browser-logic tested; a complete interactive Streamlit acceptance test is still required in an environment with Streamlit and Polars installed.

## Security / deployment

The prototype currently has **no built-in user authentication or roles**. Do not expose the app publicly without protected access, appropriate network controls and a retention review. Deployments with multiple workers must share the same durable site-registry path (or use managed configuration storage); report data is intentionally isolated per browser session within the hosting process. Never distribute the old employee-bearing `dashboard.db`.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for parsing, storage and dashboard interaction details.

## Base-sheet date scope and retention fix (17 Oct 2026)

The `Central Flex Base` supplied with the 17 October report contains rows dated outside the official Flex summary period. Attendance Base also has a next-day partial date. Both the import-history date range and retained employee rows are now constrained to dates/sites in the official summary sheets. Site aliases such as `Hyderabad REV DC` remain recognized. These extra rows are not reinterpretated as different days or silently folded into chart counts. The four real report uploads were verified with an isolated in-memory SQLite database.

For exact source comparisons, the packaged `docs/RECONCILIATION_17OCT2026.md` distinguishes actual application corrections from anomalies in the supplied Excel files. The workbooks and employee identities are not included in this release.

## Follow-up fixes (17 Oct 2026): landing alignment and 8-hour popup count

- **Landing-page instructions:** the upload guidance paragraph is explicitly center-aligned, including under Streamlit's Markdown paragraph styles. The landing text and Settings workflow are unchanged.
- **Attendance 8 Hrs + Adherence popup:** `Count` now retrieves the workbook's official `8 Hours +` count for the clicked site and date (previously the UI queried `8 Hours+` and showed a missing-value dash). No headcounts or official adherence percentages are recalculated or changed.
- **Flex 8 Hrs + Adherence popup:** continues using its distinct official count header, `8 Hours+`, as it appears in `DC Summary - 2` and `XD Summary - 2`.
- The two source count names are centralized in `metric_mappings.py` and covered by tests. A genuine missing count still displays a dash; a real zero shows `0`.

The full Streamlit browser acceptance test is still required where Streamlit/Polars are installed. Use the supplied reports to click an Attendance 8 Hrs+ point and confirm the selected site/date matches the source `8 Hours +` column. See the latest handover notes below for the exact test.

## Follow-up fixes (17 Oct 2026): WORKSPACE menu and report-sourced Roster percentages

- **WORKSPACE sidebar:** the old six-option Streamlit radio widget has been replaced by six real full-width navigation buttons. The active page has a soft green highlight; navigation remains keyboard-focusable. All Dashboard, Settings and placeholder routes remain unchanged. Only the WORKSPACE menu is restyled, not Settings actions.
- **Roster Adoption/Adherence:** the chart now uses the **actual imported `Roster Adoption` and `Roster Adherence` source percentage cells** for its bottom-of-bar labels and hover cards, instead of independently computing percentages from headcounts. These fields already exist in the imported Roster `DC Summary` and `XD Summary`. Labels/hover are rounded to whole percentages for display; imported source values are preserved at full precision. Missing official percentages display an em dash, never an estimated zero or recalculated replacement. Active HC, Rostered HC, and Roster Match counts/geometry are unchanged.
- **Real workbook verification:** the supplied 17 October Roster report has 912 individual site/date Adherence values (57 sites x 16 days), plus 32 DC/XD grand-total cells that the dashboard intentionally excludes. All 912 imported site/date values agree with the corresponding dedicated `DC Roster Adherence` and `XD Roster Adherence` sheets. OneSRT DC on 1 Oct reports 85.85858585858585%, displayed as **86%**.

Browser acceptance is still required in a live Streamlit installation, which isn't available in the current environment. Run the tests and check Dashboard -> Roster and the sidebar after uploading the workbook.
