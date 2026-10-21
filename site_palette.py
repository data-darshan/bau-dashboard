"""Persistent Attendance/Roster/Flex site colors (metadata registry only).

All 64 approved colors stay unchanged. New sites receive maximally separated
colors in data/site_settings.db, which never contains employee/report data.
DC and XD remain distinct; similarly named sites are not automatically merged.
"""
from __future__ import annotations

import colorsys
import hashlib
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable

SITE_PALETTE_VERSION = "SITE_PALETTE_V7_PERSISTENT_20261012"

# Stable registered colors (keys are normalized site names, DC/XD kept distinct).
ASSIGNED_SITE_COLORS: dict[str, str] = {
    'ahmedabad dc': '#D4651C',
    'ajmer dc': '#1FEAAC',
    'akola xd': '#DA22DD',
    'aurangabad xd': '#B2E42F',
    'bangalore dc': '#24AE9B',
    'bhopal xd': '#5E46D7',
    'bhubaneswar xd': '#1DE23B',
    'chandigarh dc': '#7F28EB',
    'chandigarh xd': '#CFA120',
    'chennai dc': '#26DEE3',
    'chennai xd': '#E916A6',
    'coimbatore xd': '#77DF34',
    'dibrugarh xd': '#1C2ED4',
    'gorakhpur dc': '#EA461F',
    'gorakhpur xd': '#22DD7D',
    'guwahati dc': '#BC2FE4',
    'hubli xd': '#CEDB14',
    'hyderabad dc': '#2B9EDE',
    'hyderabad rev dc': '#E21D62',
    'indore xd': '#33EB28',
    'jabalpur xd': '#4A20CF',
    'jaipur dc': '#539B28',
    'jammu xd': '#16E9C3',
    'jodhpur xd': '#DF34CC',
    'kanpur xd': '#E63D43',
    'kochi xd': '#1F5DEA',
    'kolkata dc': '#BD50D6',
    'kozhikode xd': '#2FE462',
    'lucknow dc': '#8614DB',
    'ludhiana dc': '#DEC52B',
    'ludhiana xd': '#1DC3E2',
    'madurai xd': '#EB2894',
    'malda xd': '#4ECF20',
    'moradabad xd': '#2C26E3',
    'mumbai dc': '#D19538',
    'mysore xd': '#34DF9D',
    'nagpur dc': '#C31CD4',
    'ncr bamnoli dc': '#68A5E9',
    'ncr bilaspur dc': '#E54150',
    'ncr tauru dc': '#E47BA4',
    'noida dc': '#14DB23',
    'one ncr dc': '#F27A16',
    'oneamd dc': '#E29E1D',
    'onerjt dc': '#28EBE1',
    'onesrt dc': '#CF20A6',
    'patna dc': '#7FE326',
    'patna xd': '#163BE9',
    'pune xd': '#DF4834',
    'purnia xd': '#1CD467',
    'raipur xd': '#AD1FEA',
    'rajahmundry xd': '#DDDB22',
    'ranchi xd': '#2FB1E4',
    'sambalpur xd': '#DB1469',
    'silchar xd': '#43DE2B',
    'siliguri xd': '#3C1DE2',
    'srinagar xd': '#EB8028',
    'surat dc': '#176CCC',
    'trichy xd': '#E326DD',
    'twoncr dc': '#A5E916',
    'udaipur xd': '#3476DF',
    'vanaras xd': '#D41C2D',
    'varanasi xd': '#189D9C',
    'vijayawada xd': '#7E22DD',
    'visakhapatnam xd': '#E4BD2F',
}


def site_key(name: str) -> str:
    """Use the same canonical identity rule as db.normalize_site()."""
    return re.sub(r"\s+", " ", str(name or "").strip()).casefold()


def _hex_from_hls(hue: float, lightness: float, saturation: float) -> str:
    channels = colorsys.hls_to_rgb(hue, lightness, saturation)
    return "#" + "".join(f"{round(255 * v):02X}" for v in channels)


def _oklab(color: str) -> tuple[float, float, float]:
    """Perceptual RGB distance (OKLab), without external dependencies."""
    def linear(channel: int) -> float:
        val = channel / 255.0
        return val / 12.92 if val <= .04045 else ((val + .055) / 1.055) ** 2.4

    red, green, blue = [linear(int(color[i:i + 2], 16)) for i in (1, 3, 5)]
    l = (.4122214708 * red + .5363325363 * green + .0514459929 * blue) ** (1 / 3)
    m = (.2119034982 * red + .6806995451 * green + .1073969566 * blue) ** (1 / 3)
    s = (.0883024619 * red + .2817188376 * green + .6299787005 * blue) ** (1 / 3)
    return (
        .2104542553 * l + .7936177850 * m - .0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + .4505937099 * s,
        .0259040371 * l + .7827717662 * m - .8086757660 * s,
    )


@lru_cache(maxsize=1)
def _candidate_colors() -> tuple[tuple[str, tuple[float, float, float]], ...]:
    """Vivid hue options with several saturation/lightness combinations."""
    options = []
    for degree in range(0, 360, 3):
        for saturation in (.67, .80, .93):
            for lightness in (.39, .48, .58):
                code = _hex_from_hls(degree / 360, lightness, saturation)
                options.append((code, _oklab(code)))
    return tuple(options)


def _best_available_color(site: str, existing_colors: set[str]) -> str:
    """Pick the unused color most unlike the already assigned ones.

    Unlimited sites cannot have unlimited visually distinguishable colors.
    We guarantee an exact unique HEX until palette exhaustion and maximize
    perceptual separation from all currently saved colors.
    """
    existing_lab = [_oklab(color) for color in existing_colors]
    best_color = None
    best_score = (-1.0, -1)
    for candidate, lab in _candidate_colors():
        if candidate in existing_colors:
            continue
        nearest_squared = min(
            (lab[0] - other[0]) ** 2 + (lab[1] - other[1]) ** 2 + (lab[2] - other[2]) ** 2
            for other in existing_lab
        ) if existing_lab else float('inf')
        tie_break = int.from_bytes(hashlib.sha256(
            f"{site}|{candidate}".encode('utf-8')).digest()[:4], 'big')
        rank = (nearest_squared, tie_break)
        if rank > best_score:
            best_score, best_color = rank, candidate
    if best_color is None:
        raise RuntimeError("No unused site colors remain in the available palette")
    return best_color


def ensure_site_colors(db_path: str | Path,
                       site_names: Iterable[str] = ()) -> dict[str, str]:
    """Seed approved colors and store new ones in the durable site registry.

    Concurrent allocations share a SQLite transaction and uniqueness checks.
    No report or employee tables are read or written by this function.
    Returns saved HEX values keyed by canonical site name.
    """
    file = Path(db_path)
    file.parent.mkdir(parents=True, exist_ok=True)
    requested_keys = {site_key(name) for name in site_names if site_key(name)}
    with closing(sqlite3.connect(str(file), timeout=60)) as con:
        con.execute('PRAGMA busy_timeout = 60000')
        con.execute('BEGIN IMMEDIATE')
        try:
            con.execute('''
                CREATE TABLE IF NOT EXISTS site_color_mapping (
                    site_key TEXT PRIMARY KEY,
                    color_hex TEXT NOT NULL UNIQUE,
                    assigned_at TEXT NOT NULL,
                    source TEXT NOT NULL
                )
            ''')
            now = datetime.now(timezone.utc).isoformat(timespec='seconds')
            con.executemany('''
                INSERT OR IGNORE INTO site_color_mapping
                    (site_key, color_hex, assigned_at, source)
                VALUES (?, ?, ?, 'V6_APPROVED')
            ''', [(key, color.upper(), now) for key, color in ASSIGNED_SITE_COLORS.items()])
            existing = con.execute('SELECT site_key, color_hex FROM site_color_mapping').fetchall()
            saved = {str(key): str(color).upper() for key, color in existing}
            if any(not re.fullmatch(r'#[0-9A-F]{6}', color) for color in saved.values()):
                raise ValueError('Invalid saved HEX in site_color_mapping')
            requested = set(requested_keys)
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='site_mapping'").fetchone():
                requested.update(site_key(row[0]) for row in con.execute('SELECT site_key FROM site_mapping'))
            used = set(saved.values())
            for key in sorted(requested - saved.keys()):
                if not key:
                    continue
                candidate = _best_available_color(key, used)
                con.execute('''
                    INSERT INTO site_color_mapping(site_key, color_hex, assigned_at, source)
                    VALUES (?, ?, ?, 'AUTO_GENERATED')
                ''', (key, candidate, now))
                saved[key] = candidate
                used.add(candidate)
            con.commit()
            return saved
        except Exception:
            con.rollback()
            raise


def site_color(name: str, *, db_path: str | Path | None = None) -> str:
    """Read the approved or permanently saved base color for one site.

    Provide db_path for any new sites: that activates collision checks and
    permanence. The no-database fallback exists only for stand-alone previews.
    """
    key = site_key(name)
    if db_path is not None:
        return ensure_site_colors(db_path, (name,))[key]
    if key in ASSIGNED_SITE_COLORS:
        return ASSIGNED_SITE_COLORS[key]
    digest = hashlib.sha256(key.encode('utf-8')).digest()
    hue = int.from_bytes(digest[:4], 'big') / 2 ** 32
    return _hex_from_hls(hue, .43 + digest[5] / 255 * .12,
                         .73 + digest[4] / 255 * .12)


def site_color_map(site_names: Iterable[str], *,
                   db_path: str | Path | None = None) -> dict[str, str]:
    """Single consistent mapping for both Attendance and Roster."""
    names = [str(name) for name in site_names]
    if db_path is not None:
        saved = ensure_site_colors(db_path, names)
        return {name: saved[site_key(name)] for name in names}
    return {name: site_color(name) for name in names}
