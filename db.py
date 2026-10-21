from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager, nullcontext
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence
from uuid import uuid4

import polars as pl

REGIONS = ["North", "South", "East", "West", "UNASSIGNED"]


def _query_frame(con: sqlite3.Connection, sql: str, params: Sequence = ()) -> pl.DataFrame:
    """Return a Polars frame from a safely parameterized SQLite query.

    sqlite3's execute method takes positional parameters, while the generic
    pl.read_database(execute_options=...) path passes keyword arguments.
    Using an already-executed SQLite cursor keeps binding safe and removes
    the pandas conversion, without altering existing SQL/database behavior.
    """
    cursor = con.execute(sql, tuple(params))
    columns = [item[0] for item in cursor.description]
    rows = [tuple(row) for row in cursor]
    if not rows:
        return pl.DataFrame(schema=columns)
    return pl.DataFrame(rows, schema=columns, orient="row", infer_schema_length=None)


def coerce_date(value, *, prefer_last: bool = False) -> date:
    """Return a real date even if a UI passes a date-range tuple/list."""
    if isinstance(value, (list, tuple)):
        if not value:
            raise ValueError("Date selection is empty")
        value = value[-1] if prefer_last else value[0]
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise TypeError(f"Unsupported date value: {type(value).__name__}")


def normalize_site(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def infer_facility_type(site: str) -> str:
    s = re.sub(r"\s+", " ", str(site or "").strip()).upper()
    if s.endswith(" XD"):
        return "XD"
    if s.endswith(" DC"):
        return "DC"
    return "UNKNOWN"


def new_session_database() -> tuple[str, sqlite3.Connection]:
    """An isolated, shared-cache SQLite database held alive only by this session.

    No employee/report data is ever written to a file. The caller must retain
    the anchor connection for the lifetime of the Streamlit browser session.
    """
    uri = f"file:bau_session_{uuid4().hex}?mode=memory&cache=shared"
    anchor = sqlite3.connect(uri, uri=True, timeout=60, check_same_thread=False)
    return uri, anchor


def _memory_uri(db_path: str | Path) -> bool:
    return str(db_path).startswith("file:") and "mode=memory" in str(db_path)


@contextmanager
def connect(db_path: str | Path):
    con = sqlite3.connect(str(db_path), timeout=60, uri=_memory_uri(db_path))
    con.row_factory = sqlite3.Row
    if not _memory_uri(db_path):
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_site_registry(registry_path: str | Path) -> None:
    """Durable admin metadata only: NO report, employee, or import-history tables."""
    Path(registry_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(registry_path) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS site_mapping (
                site_key TEXT PRIMARY KEY,
                site TEXT NOT NULL,
                facility_type TEXT NOT NULL,
                region TEXT NOT NULL DEFAULT 'UNASSIGNED',
                updated_at TEXT NOT NULL
            )
        """)


def refresh_sites_from_registry(session_db: str, registry_path: str | Path) -> None:
    """Pull authoritative region/identity settings into this session's database."""
    with connect(registry_path) as registry:
        rows = registry.execute(
            "SELECT site_key, site, facility_type, region, updated_at FROM site_mapping"
        ).fetchall()
    with connect(session_db) as session:
        session.executemany("""
            INSERT INTO site_mapping(site_key,site,facility_type,region,updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(site_key) DO UPDATE SET
                site=excluded.site, facility_type=excluded.facility_type,
                region=excluded.region, updated_at=excluded.updated_at
        """, [tuple(row) for row in rows])


def save_discovered_sites_to_registry(session_db: str, registry_path: str | Path) -> None:
    """Remember new facility names without overwriting administrator mappings."""
    with connect(session_db) as session:
        rows = session.execute(
            "SELECT site_key, site, facility_type, region, updated_at FROM site_mapping"
        ).fetchall()
    with connect(registry_path) as registry:
        registry.executemany("""
            INSERT INTO site_mapping(site_key,site,facility_type,region,updated_at)
            VALUES(?,?,?,?,?) ON CONFLICT(site_key) DO NOTHING
        """, [tuple(row) for row in rows])


REPORT_SECTIONS = {
    "Attendance": ("attendance",),
    "Onboarding": ("onboarding_aadhar", "onboarding_hyperverge"),
    "Roster": ("roster",),
    "Flex": ("flex_usage", "flex_working"),
}
REPORT_DETAILS = {
    "Attendance": "attendance_detail", "Onboarding": "onboarding_red_detail",
    "Flex": "flex_detail",
}


def clear_previous_report(con: sqlite3.Connection, report_type: str) -> None:
    """Discard the previous upload OF THIS DOMAIN inside an import transaction."""
    if report_type not in REPORT_SECTIONS:
        raise ValueError(f"Unknown report type: {report_type}")
    for section in REPORT_SECTIONS[report_type]:
        con.execute("DELETE FROM summary_metrics WHERE section=?", (section,))
    detail_table = REPORT_DETAILS.get(report_type)
    if detail_table:
        con.execute(f"DELETE FROM {detail_table}")  # hard-coded allowlist above
    con.execute("DELETE FROM import_history WHERE report_type=?", (report_type,))


def clear_session_reports(session_db: str) -> None:
    """Manually reset all report data; site settings remain intact."""
    with connect(session_db) as con:
        con.execute("BEGIN IMMEDIATE")
        for report_type in REPORT_SECTIONS:
            clear_previous_report(con, report_type)


def init_db(db_path: str | Path) -> None:
    if not _memory_uri(db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS site_mapping (
                site_key TEXT PRIMARY KEY,
                site TEXT NOT NULL,
                facility_type TEXT NOT NULL,
                region TEXT NOT NULL DEFAULT 'UNASSIGNED',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS summary_metrics (
                section TEXT NOT NULL,
                data_date TEXT NOT NULL,
                site_key TEXT NOT NULL,
                site TEXT NOT NULL,
                facility_type TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL,
                unit TEXT NOT NULL,
                source_file TEXT,
                imported_at TEXT NOT NULL,
                PRIMARY KEY (section, data_date, site_key, metric)
            );
            CREATE INDEX IF NOT EXISTS idx_summary_filter
                ON summary_metrics(section, data_date, facility_type, site_key, metric);

            CREATE TABLE IF NOT EXISTS attendance_detail (
                data_date TEXT NOT NULL,
                site_key TEXT NOT NULL,
                site TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                employee_name TEXT,
                role TEXT,
                shift TEXT,
                total_hours REAL,
                working_hours REAL,
                punch_status TEXT NOT NULL,
                source_file TEXT,
                imported_at TEXT NOT NULL,
                PRIMARY KEY (data_date, site_key, employee_id)
            );
            CREATE INDEX IF NOT EXISTS idx_att_detail
                ON attendance_detail(data_date, site_key, punch_status);

            CREATE TABLE IF NOT EXISTS onboarding_red_detail (
                data_date TEXT NOT NULL,
                site_key TEXT NOT NULL,
                site TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                employee_name TEXT,
                role TEXT,
                approved_by TEXT,
                aadhaar_onboarding TEXT,
                hyperverge_status TEXT,
                auto_verification_status TEXT,
                comments TEXT,
                source_file TEXT,
                imported_at TEXT NOT NULL,
                PRIMARY KEY (data_date, site_key, employee_id)
            );
            CREATE INDEX IF NOT EXISTS idx_onb_red_detail
                ON onboarding_red_detail(data_date, site_key);

            CREATE TABLE IF NOT EXISTS flex_detail (
                data_date TEXT NOT NULL,
                site_key TEXT NOT NULL,
                site TEXT NOT NULL,
                employee_id TEXT,
                employee_name TEXT,
                role TEXT,
                hrbp_name TEXT,
                employee_type TEXT,
                validation_status TEXT,
                flex_check TEXT,
                punch_code TEXT,
                working_hours REAL,
                bucket TEXT,
                source_file TEXT,
                imported_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_flex_detail
                ON flex_detail(data_date, site_key, validation_status, flex_check, bucket);

            CREATE TABLE IF NOT EXISTS import_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                source_file TEXT NOT NULL,
                min_date TEXT,
                max_date TEXT,
                summary_rows INTEGER NOT NULL DEFAULT 0,
                detail_rows INTEGER NOT NULL DEFAULT 0,
                imported_at TEXT NOT NULL
            );
            """
        )
        # Backward-compatible Flex detail enrichment. Older prototype DBs do
        # not contain these optional PII/ownership fields, while newer Flex
        # workbooks may expose them in Central Flex Base.
        flex_columns = {row[1] for row in con.execute("PRAGMA table_info(flex_detail)")}
        for column, sql_type in (
            ("phone_number", "TEXT"),
            ("aadhaar_number", "TEXT"),
            ("hr_name", "TEXT"),
        ):
            if column not in flex_columns:
                con.execute(f"ALTER TABLE flex_detail ADD COLUMN {column} {sql_type}")


def upsert_sites(db_path: str | Path, sites: Iterable[tuple[str, str, str | None]], *, con: sqlite3.Connection | None = None) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    rows = []
    for site, facility_type, region in sites:
        if not site:
            continue
        key = normalize_site(site)
        rows.append((key, re.sub(r"\s+", " ", str(site).strip()), facility_type or infer_facility_type(site), region or "UNASSIGNED", now))
    if not rows:
        return
    with (connect(db_path) if con is None else nullcontext(con)) as active_con:
        for key, site, ftype, region, ts in rows:
            existing = active_con.execute("SELECT region, site, facility_type FROM site_mapping WHERE site_key=?", (key,)).fetchone()
            if existing:
                # Preserve an admin-assigned region; refresh display/type only when sensible.
                active_con.execute(
                    "UPDATE site_mapping SET site=?, facility_type=?, updated_at=? WHERE site_key=?",
                    (existing["site"] or site, existing["facility_type"] if existing["facility_type"] != "UNKNOWN" else ftype, ts, key),
                )
            else:
                active_con.execute(
                    "INSERT INTO site_mapping(site_key,site,facility_type,region,updated_at) VALUES(?,?,?,?,?)",
                    (key, site, ftype, region, ts),
                )


def seed_region_mapping(db_path: str | Path, mapping: Sequence[tuple[str, str]]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with connect(db_path) as con:
        for site, region in mapping:
            key = normalize_site(site)
            ftype = infer_facility_type(site)
            clean_site = re.sub(r"\s+", " ", site.strip())
            con.execute(
                """
                INSERT INTO site_mapping(site_key,site,facility_type,region,updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(site_key) DO NOTHING
                """,
                (key, clean_site, ftype, region, now),
            )


def replace_summary_rows(db_path: str | Path, rows: list[dict], *, con: sqlite3.Connection | None = None) -> int:
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    values = [
        (
            r["section"], str(r["data_date"]), r["site_key"], r["site"], r["facility_type"],
            r["metric"], r.get("value"), r["unit"], r.get("source_file"), now,
        )
        for r in rows
    ]
    with (connect(db_path) if con is None else nullcontext(con)) as active_con:
        active_con.executemany(
            """
            INSERT INTO summary_metrics(section,data_date,site_key,site,facility_type,metric,value,unit,source_file,imported_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(section,data_date,site_key,metric) DO UPDATE SET
                site=excluded.site,
                facility_type=excluded.facility_type,
                value=excluded.value,
                unit=excluded.unit,
                source_file=excluded.source_file,
                imported_at=excluded.imported_at
            """,
            values,
        )
    return len(values)


def sync_attendance_single_punch_percent(db_path: str | Path, dates: Sequence[str] | None = None, *, con: sqlite3.Connection | None = None) -> None:
    """Store Single Punch / Active HC * 100 for each attendance site/date.

    The original Single Punch count remains intact for employee drill-down.
    If Active HC is missing or zero, no percentage is stored (not a false 0%).
    `dates` limits import-time work; None uses all current-session records.
    Safe to call repeatedly: derived rows are upserted, never duplicated.
    """
    target_dates = tuple(sorted({str(d) for d in dates})) if dates is not None else None
    if target_dates is not None and not target_dates:
        return

    date_clause = (
        " AND data_date IN (%s)" % ",".join("?" for _ in target_dates)
        if target_dates is not None else ""
    )
    source_date_clause = (
        " AND sp.data_date IN (%s)" % ",".join("?" for _ in target_dates)
        if target_dates is not None else ""
    )
    # Keep only percentages with a valid same-site, same-date denominator.
    # No other metric or report section is modified by the cleanup.
    with (connect(db_path) if con is None else nullcontext(con)) as active_con:
        active_con.execute(
            """
            DELETE FROM summary_metrics
            WHERE section='attendance' AND metric='Single Punch %'
            """ + date_clause + """
              AND NOT EXISTS (
                SELECT 1 FROM summary_metrics AS sp
                JOIN summary_metrics AS hc
                  ON hc.section=sp.section AND hc.data_date=sp.data_date
                 AND hc.site_key=sp.site_key AND hc.metric='Active HC'
                WHERE sp.section='attendance' AND sp.metric='Single Punch'
                  AND sp.data_date=summary_metrics.data_date
                  AND sp.site_key=summary_metrics.site_key
                  AND sp.value IS NOT NULL AND hc.value > 0
              )
            """,
            target_dates or (),
        )
        active_con.execute(
            """
            INSERT INTO summary_metrics (
                section, data_date, site_key, site, facility_type,
                metric, value, unit, source_file, imported_at
            )
            SELECT sp.section, sp.data_date, sp.site_key, sp.site, sp.facility_type,
                   'Single Punch %', sp.value * 100.0 / hc.value,
                   'percent', sp.source_file, ?
            FROM summary_metrics AS sp
            JOIN summary_metrics AS hc
              ON hc.section=sp.section AND hc.data_date=sp.data_date
             AND hc.site_key=sp.site_key AND hc.metric='Active HC'
            WHERE sp.section='attendance' AND sp.metric='Single Punch'
              AND sp.value IS NOT NULL AND hc.value > 0
            """ + source_date_clause + """
            ON CONFLICT(section, data_date, site_key, metric) DO UPDATE SET
                site=excluded.site,
                facility_type=excluded.facility_type,
                value=excluded.value,
                unit=excluded.unit,
                source_file=excluded.source_file,
                imported_at=excluded.imported_at
            """,
            (datetime.now().isoformat(timespec="seconds"),) + (target_dates or ()),
        )


def replace_attendance_detail(db_path: str | Path, rows: list[dict], dates: Sequence[str], *, con: sqlite3.Connection | None = None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with (connect(db_path) if con is None else nullcontext(con)) as active_con:
        if dates:
            q = ",".join("?" for _ in dates)
            active_con.execute(f"DELETE FROM attendance_detail WHERE data_date IN ({q})", tuple(dates))
        if rows:
            active_con.executemany(
                """
                INSERT OR REPLACE INTO attendance_detail(
                    data_date,site_key,site,employee_id,employee_name,role,shift,total_hours,working_hours,punch_status,source_file,imported_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [(
                    r["data_date"], r["site_key"], r["site"], r["employee_id"], r.get("employee_name"), r.get("role"),
                    r.get("shift"), r.get("total_hours"), r.get("working_hours"), r["punch_status"], r.get("source_file"), now,
                ) for r in rows],
            )
    return len(rows)


def replace_onboarding_red_detail(db_path: str | Path, rows: list[dict], dates: Sequence[str], *, con: sqlite3.Connection | None = None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with (connect(db_path) if con is None else nullcontext(con)) as active_con:
        if dates:
            q = ",".join("?" for _ in dates)
            active_con.execute(f"DELETE FROM onboarding_red_detail WHERE data_date IN ({q})", tuple(dates))
        if rows:
            active_con.executemany(
                """
                INSERT OR REPLACE INTO onboarding_red_detail(
                    data_date,site_key,site,employee_id,employee_name,role,approved_by,aadhaar_onboarding,
                    hyperverge_status,auto_verification_status,comments,source_file,imported_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [(
                    r["data_date"], r["site_key"], r["site"], r["employee_id"], r.get("employee_name"), r.get("role"),
                    r.get("approved_by"), r.get("aadhaar_onboarding"), r.get("hyperverge_status"),
                    r.get("auto_verification_status"), r.get("comments"), r.get("source_file"), now,
                ) for r in rows],
            )
    return len(rows)


def replace_flex_detail(db_path: str | Path, rows: list[dict], dates: Sequence[str], *, con: sqlite3.Connection | None = None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with (connect(db_path) if con is None else nullcontext(con)) as active_con:
        if dates:
            q = ",".join("?" for _ in dates)
            active_con.execute(f"DELETE FROM flex_detail WHERE data_date IN ({q})", tuple(dates))
        if rows:
            active_con.executemany(
                """
                INSERT INTO flex_detail(
                    data_date,site_key,site,employee_id,employee_name,role,hrbp_name,employee_type,validation_status,
                    flex_check,punch_code,working_hours,bucket,phone_number,aadhaar_number,hr_name,source_file,imported_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [(
                    r["data_date"], r["site_key"], r["site"], r.get("employee_id"), r.get("employee_name"), r.get("role"),
                    r.get("hrbp_name"), r.get("employee_type"), r.get("validation_status"), r.get("flex_check"),
                    r.get("punch_code"), r.get("working_hours"), r.get("bucket"), r.get("phone_number"),
                    r.get("aadhaar_number"), r.get("hr_name"), r.get("source_file"), now,
                ) for r in rows],
            )
    return len(rows)


def add_import_history(db_path: str | Path, report_type: str, source_file: str, dates: Sequence[str], summary_rows: int, detail_rows: int, *, con: sqlite3.Connection | None = None) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    min_date = min(dates) if dates else None
    max_date = max(dates) if dates else None
    with (connect(db_path) if con is None else nullcontext(con)) as active_con:
        active_con.execute(
            "INSERT INTO import_history(report_type,source_file,min_date,max_date,summary_rows,detail_rows,imported_at) VALUES(?,?,?,?,?,?,?)",
            (report_type, source_file, min_date, max_date, summary_rows, detail_rows, now),
        )


def get_site_mapping(db_path: str | Path) -> pl.DataFrame:
    with connect(db_path) as con:
        return _query_frame(
            con,
            "SELECT site_key, site AS Site, facility_type AS Type, region AS Region, updated_at FROM site_mapping ORDER BY region, site",
        )


def save_site_mapping(db_path: str | Path, frame: pl.DataFrame) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with connect(db_path) as con:
        for row in frame.iter_rows(named=True):
            key = str(row.get("site_key") or normalize_site(row["Site"]))
            con.execute(
                "UPDATE site_mapping SET site=?, facility_type=?, region=?, updated_at=? WHERE site_key=?",
                (str(row["Site"]), str(row["Type"]), str(row["Region"]), now, key),
            )


def get_import_history(db_path: str | Path, limit: int = 20) -> pl.DataFrame:
    with connect(db_path) as con:
        return _query_frame(
            con,
            "SELECT report_type AS Report, source_file AS File, min_date AS FromDate, max_date AS ToDate, summary_rows AS SummaryRows, detail_rows AS DetailRows, imported_at AS ImportedAt FROM import_history ORDER BY id DESC LIMIT ?",
            (limit,),
        )


def get_date_bounds(db_path: str | Path) -> tuple[date | None, date | None]:
    with connect(db_path) as con:
        row = con.execute("SELECT MIN(data_date) AS mn, MAX(data_date) AS mx FROM summary_metrics").fetchone()
    if not row or not row["mn"]:
        return None, None
    return date.fromisoformat(row["mn"]), date.fromisoformat(row["mx"])


def get_latest_by_section(db_path: str | Path) -> dict[str, str]:
    with connect(db_path) as con:
        rows = con.execute("SELECT section, MAX(data_date) AS mx FROM summary_metrics GROUP BY section").fetchall()
    return {r["section"]: r["mx"] for r in rows}


def get_unassigned_count(db_path: str | Path) -> int:
    with connect(db_path) as con:
        return int(con.execute("SELECT COUNT(*) FROM site_mapping WHERE region='UNASSIGNED'").fetchone()[0])


def available_sites(db_path: str | Path, regions: Sequence[str], types: Sequence[str]) -> pl.DataFrame:
    sql = """
        SELECT DISTINCT s.site_key, COALESCE(m.site,s.site) AS site, s.facility_type, COALESCE(m.region,'UNASSIGNED') AS region
        FROM summary_metrics s
        LEFT JOIN site_mapping m ON m.site_key=s.site_key
        WHERE 1=1
    """
    params: list = []
    if regions:
        sql += " AND COALESCE(m.region,'UNASSIGNED') IN (%s)" % ",".join("?" for _ in regions)
        params.extend(regions)
    if types:
        sql += " AND s.facility_type IN (%s)" % ",".join("?" for _ in types)
        params.extend(types)
    sql += " ORDER BY site"
    with connect(db_path) as con:
        return _query_frame(con, sql, params)


def query_summary(
    db_path: str | Path,
    section: str,
    date_from: date,
    date_to: date,
    regions: Sequence[str],
    types: Sequence[str],
    site_keys: Sequence[str] | None = None,
    metrics: Sequence[str] | None = None,
) -> pl.DataFrame:
    sql = """
        SELECT s.section, s.data_date, s.site_key, COALESCE(m.site,s.site) AS site,
               s.facility_type, COALESCE(m.region,'UNASSIGNED') AS region,
               s.metric, s.value, s.unit
        FROM summary_metrics s
        LEFT JOIN site_mapping m ON m.site_key=s.site_key
        WHERE s.section=? AND s.data_date BETWEEN ? AND ?
    """
    date_from = coerce_date(date_from)
    date_to = coerce_date(date_to, prefer_last=True)
    params: list = [section, date_from.isoformat(), date_to.isoformat()]
    if regions:
        sql += " AND COALESCE(m.region,'UNASSIGNED') IN (%s)" % ",".join("?" for _ in regions)
        params.extend(regions)
    if types:
        sql += " AND s.facility_type IN (%s)" % ",".join("?" for _ in types)
        params.extend(types)
    if site_keys:
        sql += " AND s.site_key IN (%s)" % ",".join("?" for _ in site_keys)
        params.extend(site_keys)
    if metrics:
        sql += " AND s.metric IN (%s)" % ",".join("?" for _ in metrics)
        params.extend(metrics)
    sql += " ORDER BY s.data_date, site, s.metric"
    with connect(db_path) as con:
        df = _query_frame(con, sql, params)
    if not df.is_empty():
        df = df.with_columns(pl.col("data_date").str.strptime(pl.Date, "%Y-%m-%d"))
    return df


def attendance_detail_for(db_path: str | Path, data_date: date, site_key: str, punch_status: str) -> pl.DataFrame:
    with connect(db_path) as con:
        return _query_frame(
            con,
            """
            SELECT employee_id AS "Employee ID", employee_name AS "Employee Name", role AS "Role",
                   shift AS "Shift", working_hours AS "Working Hours"
            FROM attendance_detail
            WHERE data_date=? AND site_key=? AND punch_status=?
            ORDER BY employee_name
            """,
            (coerce_date(data_date).isoformat(), site_key, punch_status),
        )


def onboarding_red_for(db_path: str | Path, date_from: date, date_to: date, site_key: str) -> pl.DataFrame:
    with connect(db_path) as con:
        return _query_frame(
            con,
            """
            SELECT data_date AS "Date", employee_id AS "Employee ID", employee_name AS "Employee Name",
                   role AS "Role", approved_by AS "Approved By", site AS "Site",
                   aadhaar_onboarding AS "Aadhaar Onboarding", auto_verification_status AS "Verification Status"
            FROM onboarding_red_detail
            WHERE data_date BETWEEN ? AND ? AND site_key=?
            ORDER BY data_date, employee_name
            """,
            (coerce_date(date_from).isoformat(), coerce_date(date_to, prefer_last=True).isoformat(), site_key),
        )


def flex_detail_for(db_path: str | Path, date_from: date, date_to: date, site_key: str, segment: str) -> pl.DataFrame:
    """Person-level details for clickable Flex usage exception segments.

    Flex summary sheets roll a ``<site> REV DC`` Central Base label into the
    corresponding ``<site> DC`` summary site. Include that detail alias when
    it exists so popup rows reconcile with the clicked summary segment.
    """
    key = normalize_site(site_key)
    site_keys = [key]
    if key.endswith(" dc") and not key.endswith(" rev dc"):
        site_keys.append(key[:-3] + " rev dc")
    placeholders = ",".join("?" for _ in site_keys)
    params: list = [
        coerce_date(date_from).isoformat(),
        coerce_date(date_to, prefer_last=True).isoformat(),
        *site_keys,
    ]
    if segment == "Onboarded & Not Punched":
        where = " AND LOWER(TRIM(validation_status))='onboarded' AND LOWER(TRIM(flex_check))='absent'"
        select = '''
            SELECT employee_id AS "Employee ID", employee_name AS "Employee Name",
                   COALESCE(NULLIF(hr_name,''), NULL) AS "HR", hrbp_name AS "HRBP"
        '''
    elif segment == "Not Onboarded":
        where = " AND LOWER(TRIM(validation_status))='not onboarded'"
        select = '''
            SELECT employee_name AS "Employee Name", phone_number AS "Phone Number",
                   aadhaar_number AS "Aadhaar Number", COALESCE(NULLIF(hr_name,''), NULL) AS "HR",
                   hrbp_name AS "HRBP"
        '''
    else:
        return pl.DataFrame()
    sql = select + f'''
        FROM flex_detail
        WHERE data_date BETWEEN ? AND ? AND site_key IN ({placeholders})
    ''' + where + " ORDER BY employee_name"
    with connect(db_path) as con:
        return _query_frame(con, sql, params)

def flex_working_detail_for(db_path: str | Path, data_date: date, site_key: str, punch_code: str) -> pl.DataFrame:
    """Flex employee drill-down reconciled to the working-hours summary.

    The Central Flex Base contains PT rows that are intentionally excluded from
    the working-hours summary.  MIS can also include zero-hour rows whose Bucket
    is ``-``; those are excluded from the official ``Less than 5 Hours`` count.
    Apply the same rules here so point-click detail always matches the chart.
    ``<site> REV DC`` detail is rolled into the corresponding summary DC site.
    """
    key = normalize_site(site_key)
    site_keys = [key]
    if key.endswith(" dc") and not key.endswith(" rev dc"):
        site_keys.append(key[:-3] + " rev dc")
    placeholders = ",".join("?" for _ in site_keys)
    extra = ""
    if punch_code == "HF":
        extra = " AND LOWER(TRIM(bucket))='5 to 8 hours'"
    elif punch_code == "MIS":
        extra = " AND LOWER(TRIM(bucket))='less than 5 hours'"
    elif punch_code != "SP":
        return pl.DataFrame()
    sql = f'''
        SELECT employee_id AS "Employee ID", employee_name AS "Employee Name",
               hrbp_name AS "HRBP", working_hours AS "Working Hours"
        FROM flex_detail
        WHERE data_date=? AND site_key IN ({placeholders}) AND punch_code=?
          AND LOWER(TRIM(validation_status))='onboarded'
          AND LOWER(TRIM(flex_check))='present'
          AND LOWER(TRIM(employee_type))!='pt'
          {extra}
        ORDER BY employee_name
    '''
    params = [coerce_date(data_date).isoformat(), *site_keys, punch_code]
    with connect(db_path) as con:
        return _query_frame(con, sql, params)
