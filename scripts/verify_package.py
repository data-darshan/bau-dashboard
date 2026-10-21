"""Run offline before distributing the clean BAU dashboard ZIP."""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {"dashboard.db", "onboarding_hr_site_counts.json"}

for source in ROOT.glob("*.py"):
    ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
for source in (ROOT / "tests").glob("*.py"):
    ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
assert not any(part == "__pycache__" for x in ROOT.rglob("*") for part in x.parts)
assert not any(p.name in FORBIDDEN for p in ROOT.rglob("*"))
assert not list(ROOT.rglob("*.xlsx"))
assert not list(ROOT.rglob("*.xls"))
assert not list(ROOT.rglob("*.pyc"))
assert not [p for p in ROOT.rglob("*.txt") if p.name != "requirements.txt"]
registry = ROOT / "data" / "site_settings.db"
assert registry.is_file(), "The non-sensitive site registry must be shipped"
with sqlite3.connect(registry) as con:
    names = {x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names == {"site_mapping", "site_color_mapping"}, names
    assert con.execute("SELECT count(*) FROM site_mapping").fetchone()[0] == 64
    assert con.execute("SELECT count(*) FROM site_color_mapping").fetchone()[0] == 64

app = (ROOT / "app.py").read_text(encoding="utf-8")
assert 'new_session_database()' in app
assert 'ROOT / "data" / "site_settings.db"' in app
assert 'ROOT / "data" / "dashboard.db"' not in app
print("PASS: clean package, 64 saved site maps/colors, and no historic report data")
