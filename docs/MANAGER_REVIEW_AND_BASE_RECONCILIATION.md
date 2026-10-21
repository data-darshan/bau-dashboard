# Manager review: QA and report-number reconciliation

**Date:** 17 October 2026  
**Candidate:** BAU Dashboard UI fixes + manager presentation update  
**Status:** presentation changes implemented; official source-workbook reconciliation **not yet performed**.

## What has been changed

- Main heading is placed below the Streamlit fixed toolbar; initial sidebar is responsive, navigation highlights the selected page, font/size scale is consistent.
- Attendance, Flex Working Hours and Roster hover cards use whole-percent display rounding only; source values remain floating point. Aadhaar/Manual retains decimal percentages to prevent misleading 100%/0% claims.
- Roster bars contain all official Active HC, Rostered HC and Roster Match headcounts. Adoption = Rostered HC / Active HC x 100; Adherence = Roster Match / Rostered HC x 100. The latter two show as labels at the bottom of the matching bars. Tiny-bar labels move to a safe below-axis gutter rather than colliding with headcounts.
- No source import formulas, SQL queries, or employee-detail eligibility rules were changed as a substitute for source verification.

## Source-workbook data required for acceptance

The actual 17 October 2026 BAU `.xlsx` workbooks have now been reconciled, with source findings in `RECONCILIATION_17OCT2026.md`. For a future refresh, provide the same report types:

| Area | Required summary tabs | Supporting base |
|---|---|---|
| Onboarding | `Aadhar - DC`, `Aadhar - XD`, `Hyperverge - DC`, `Hyperverge - XD` | `Onboarding Base` |
| Attendance | `Attendance Adherence - DC`, `Attendance Adherence - XD` | `Attendance Base` |
| Roster | `DC Summary`, `XD Summary`; check `DC Roster Adoption`, `XD Roster Adoption` | Same workbook |
| Flex | `DC Summary - 1`, `DC Summary - 2`, `XD Summary - 1`, `XD Summary - 2` | `Central Flex Base` |

Do not copy personally identifiable employee detail from these files into the committed test fixtures or final distributable ZIP.

## Numeric acceptance methodology

1. Import the source workbooks into a **fresh session**, and log the report filename, detected domain and available reporting dates. Files of the same domain replace each other, so upload the desired final snapshot last.
2. Keep **the same date, region, DC/XD and site filters** when comparing the source Excel cells and the Dashboard. The initial dashboard offers multi-day ranges; Roster and Flex Used additionally have separate one-day selectors. Do not compare a multi-day sum with a one-day figure.
3. For every mismatching number, record: domain, workbook, sheet, Excel cell, date, site, metric, source/raw value, dashboard displayed value, normalized stored value and the expected percent scale. Start with exact raw headcounts before percentage formatting.
4. Onboarding: compare Aadhaar and Manual raw counts per site/day and Hyperverge RED totals. Verify site-region inclusion, avoid summing two site spellings as if they were identical, and reconcile detail row counts to the official summary where applicable.
5. Attendance: compare imported `8 Hrs + Adherence`, `5 to 8 Hrs Adherence`, `<5 Hrs Adherence` and `Single Punch %` against their source denominator/percent scale. Compare point-click employee records only to the corresponding site and date.
6. Roster: compare Active HC, Rostered HC and Roster Match from the official summary for the selected day. Confirm Adoption uses Active HC and Adherence uses Rostered HC, precisely as the 17 October source workbook specifies. Whole-percent display rounding must **not** be mistaken for a change to the raw percentage.
7. Flex Used: compare Total Flex Used and each segment to the **same date** and selected region/site. Check any source summary/detail alias roll-ups such as `Hyderabad REV DC` to `Hyderabad DC`. Flex Working Hours: check the official `8 Hrs+ Adherence`; derived HF/MIS/SP percentages use Total Punched as denominator and cannot assume a missing denominator is zero.
8. Categorize mismatches as parser/header mapping, different date/filter/snapshot, report formula/denominator, duplicate/missing site, unit conversion, detail eligibility or **display-only rounding**. Fix only a confirmed discrepancy and add a fixture/test that reproduces the real issue with redacted or synthetic data.

## Live Streamlit browser acceptance

- [ ] At 1366px desktop width, opening/closing the sidebar cannot obscure the page heading. Repeat at tablet and a phone-sized viewport; check both Dashboard and Settings.
- [ ] Sidebar navigation remains functional and the active page is visually identifiable.
- [ ] Font hierarchy is consistent and headings/titles stay readable at common browser zoom levels.
- [ ] Hover over Attendance and Flex Working Hours points: displayed percentage is a **whole number**, and clicking still retrieves precise site/date records.
- [ ] The Aadhaar/Manual legend must still show a nonzero minority, for example 99.4% / 0.6%; never 100% / 0% in that example.
- [ ] For a Roster site with a tall bar, verify Adoption % and Adherence % are positioned at the bottom center of their respective halves, separate from the headcounts.
- [ ] For a Roster site with a tiny/zero bar, the count and percentage must not overlap. The footer gutter remains legible and site legend controls work.
- [ ] All Roster bar heights remain actual headcounts, and the three numbers for each site/date match the workbook.
- [ ] The original Settings upload progress and captions, employee-ID selection, Flex Used date picker (no working-hours date picker), flat Flex Used bar click, and all drill-downs still work.
- [ ] Site mapping and colors persist, while report/employee data remain session-only and no historic employee database is created on disk.

## Test commands

From the `bau_dashboard` folder with the required dependencies installed:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py'
python scripts/verify_package.py
python -m streamlit run app.py
```

**Limitation:** On this editing machine, Streamlit and Polars were not installed, so complete browser and database-regression acceptance remains pending. A separate Plotly/CSS headless browser check used synthetic bar numbers and checked desktop/tablet/mobile toolbar clearance. All four source BAU `.xlsx` files were subsequently supplied and their numeric reconciliation is recorded in `RECONCILIATION_17OCT2026.md`.
