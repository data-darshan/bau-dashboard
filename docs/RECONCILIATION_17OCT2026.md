# BAU Management Dashboard - Source Report Reconciliation

**Review date:** 17 October 2026  
**Build basis:** BAU_Management_Dashboard_Manager_Review_17Oct2026.zip  
**Inputs:** the four XLSX reports named `Attendance Adherence Report - 17th Oct.xlsx`, `Flex Adoption Report - 17th Oct.xlsx`, `Onboarding Report - 17th Oct.xlsx`, and `Roster Report - 17th Oct.xlsx`.

## Result

The dashboard's Roster Adherence formula was incorrect. The source workbook defines **Roster Adherence = Roster Match / Rostered HC x 100**, but the old dashboard used Active HC as the denominator. This build corrects the calculation, bottom-of-bar labels, and hover cards. Roster headcounts and bar heights are unchanged. The source values themselves have not been edited.

Independent extraction of **27,966 summary metric cells** from the official dashboard sheets was compared against all 27,966 imported metrics in SQLite (not counting 905 separately derived Attendance Single Punch percentages). **0 missing, 0 extra and 0 numeric mismatches** were found. The four real files also completed the import pipeline in an isolated in-memory database. This verifies data ingestion and numeric computations, not full browser interaction.

### Roster source reconciliation

- Official source formulas: Adoption = Rostered HC / Active HC x 100; Adherence = Roster Match / Rostered HC x 100.
- Across 16 dates and 57 summary sites, **701 site/date Adherence percentages** differed under the old denominator.
- The source contains 912 Adoption headcount/percentage comparisons and 773 Adherence comparisons with positive Rostered HC; all agree with the formulas above. For zero Rostered HC, source Adherence is zero and the chart shows 0%.
- The source summary percentage cells also agree with the Roster Adoption and Roster Adherence supporting worksheets.
- Example (OneSRT DC, 1 Oct): Active 561; Rostered 198; Match 170. Adoption = 35.29% and Adherence = **85.86%**, whereas the old dashboard displayed **30.30%** for Adherence.
- Chart hover and bar-foot labels round to **whole percentage points only for display**. Calculations retain full precision, and all three headcounts remain unchanged.

### Attendance

- Summary coverage: **1-16 Oct 2026**; the `Attendance Base` also contains a partial 17 Oct date that is not in the official summary.
- **10,032 source summary cells** imported without discrepancy; plus **905** derived Single Punch percentage cells, which do not replace the source Single Punch counts.
- **2,736** source summary/site/date exception-count comparisons with `Attendance Base` all passed (SP, HF, MIS); all **33,107** retained exception-person rows reconcile with the official count totals.
- The approved dashboard-specific Single Punch % remains **Single Punch / Active HC x 100**. It is derived and is not a directly sourced percentage in the workbook. Source 8H+/5-8H/<5H adherence percentages use Total Punched.
- **37 source `Punched %` cells exceed 100%** because some workbook Total Punched figures exceed Active HC. The dashboard has not edited the source or silently capped these figures. Example: NCR Bamnoli DC, 1 Oct, 424 Total Punched vs 414 Active HC = 102.42%.

### Onboarding

- Summary coverage: **1-16 Oct 2026**.
- **6,174 source summary metric cells** imported exactly.
- Aadhaar/Manual HR-by-site breakdown: **2,016** source method/site/date cells reconciled, representing **6,197** total onboarding records and **969** HR/site/date breakdown rows.
- Hyperverge RED: **1,008** source site/date comparisons matched eligible person records. The official summary contains **17 RED cases**, and exactly **17** in-scope RED details are retained. Extra base rows that are not represented by the official summary are excluded.
- Aadhaar/Manual donut percentages retain enough decimals to avoid showing an incorrect 100% when the other segment is nonzero; this is separate from whole-percent hover formatting on other charts.

### Flex

- Official summary coverage: **1-15 Oct 2026**. `Central Flex Base` has **11,034** rows (excluding header) but contains records outside the source summary scope.
- **7,200 source summary metric cells** imported exactly; **3,000** exception/working-hours detail comparisons match official counts; **9,608** in-scope Flex records equal the sum of the source `Total Flex Used` figures.
- **335** nonzero-denominator source Flex Used compliance comparisons and **314** official 8H+ source percentage comparisons match their source counts.
- In `Central Flex Base`, **859** rows have dates outside October; **332** are Oct 16/17 (with no matching Flex summary); **234** use a site/date pair absent from the summary; and **1** has an unusable site/date. The importer now excludes these **1,426** records, rather than treating them as report history or guessing they belong on different dates.
- Import history now displays **1-15 Oct** for this report, not the incorrect January-December span that the unsummarized detail rows previously caused.
- The source reports **286** site/date cases of official 8H+ adherence = 100% even though `Total Punched` = 0. These are **source-sheet values**, and have been retained under the approved policy of using the official percentage. The other three derived working-hours percentages continue to omit zero-denominator points instead of inventing zeroes.
- The `Central Flex Base` has `HRBP Name`, but no standalone HR/Site HR column. HR popup cells cannot be populated from this workbook without a corresponding source field. Phone and Aadhaar columns are available. Do not substitute HRBP or Vendor as HR.

## Mapping and filter caveat

The preserved site-registry database includes sites with an **UNASSIGNED** Region: Akola XD, Chandigarh DC, Chennai XD, Gorakhpur XD, Ludhiana XD, Patna XD, Srinagar XD and Vanaras XD. These sites may appear under all-region filtering but not in North/South/East/West until an administrator assigns them in Settings. No region classification was guessed or overwritten during this reconciliation. Before comparing a region-filtered chart with a workbook, align the site scope.

## Files changed in this review

- `roster_layers.py` - correct source Roster Adherence denominator, labels and hover definition.
- `parsers.py` - constrain in-memory employee details and import-history date bounds to the official summary site/dates; retain supported REV DC aliases.
- `tests/test_roster_layers.py`, `tests/test_manager_presentation.py`, `tests/test_site_palette.py`, `tests/test_report_retention.py` - update and extend synthetic regressions.
- `README.md`, `docs/ARCHITECTURE.md`, `docs/MANAGER_REVIEW_AND_BASE_RECONCILIATION.md` and this report - correct technical definitions.

## Verification boundary

Verified: actual workbook schema detection, parsing, source-to-import normalization, mathematical ratios, detail-count reconciliation, per-session import/retention behavior, source-independent synthetic tests, and package integrity. **A full Streamlit browser acceptance test is still required** on a machine with the declared Streamlit and Polars dependencies. Existing source-data anomalies remain identified above; they are not dashboard bugs and should be resolved by the report owner if business policy changes.

The original four XLSX reports are unchanged and are **not** included in the packaged dashboard ZIP. No employee names, mobile numbers, Aadhaar values or employee IDs are included in the reconciliation artifacts.

## UI follow-up: Attendance 8 Hrs+ popup Count

The Attendance summary workbook contains a count column named `8 Hours +` (note the space); the Flex Working Hours summary uses `8 Hours+`. An earlier Attendance point-click payload looked for the Flex spelling and therefore displayed a missing Count despite the imported count being present. The popup now uses the exact Attendance header, without changing stored percentages or any summary values. The Flex mapping is unchanged. The landing-page upload instruction is explicitly centered.

### Follow-up: official percentage passthrough (17 October 2026)

The earlier denominator correction established the source's Roster Adherence definition. A later change makes the graph use the **imported percentage itself** (`Roster Adherence` from DC/XD Summary), not even a mathematically equivalent recalculation. The dedicated Adherence sheets independently match all 912 site/date values. Adoption similarly reads its official percentage column. Plot labels/hover round the imported value only for presentation. All Roster headcounts are untouched. WORKSPACE navigation has also been converted from a radio group to menu-style buttons.
