"""The application's own database — the one this project writes to.

Not to be confused with app/extractor/moodle_db.py, which is a READ-ONLY
window onto Moodle's database. Two different databases with two different
contracts:

    app/db.py          -> our data (units, submissions, evaluations). Writes.
    extractor/moodle_db.py -> Moodle's data (BTEC criteria text). SELECT only.

CONFIGURATION
-------------
DATABASE_URL in .env selects the backend. Leave it blank (the default) to
use the local SQLite development file app_dev.db, which is what every
script, test and portal page has always used. Set it to move the app onto a
real server, e.g.:

    DATABASE_URL=postgresql+psycopg://user:pass@host:5432/btek
    DATABASE_URL=mysql+pymysql://user:pass@host:3306/btek

A non-SQLite URL needs its driver installed (psycopg for PostgreSQL;
PyMySQL is already in requirements.txt).
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import create_engine

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The development default. Kept as a Path (not just a URL string) because
# scripts/seed_dev_db.py deletes this file to reseed from scratch — an
# operation that is only meaningful for the local SQLite backend.
DB_PATH = PROJECT_ROOT / "app_dev.db"
SQLITE_DEV_URL = f"sqlite:///{DB_PATH}"

# .strip() because a trailing space in a .env value is invisible and would
# otherwise produce a baffling driver error.
_CONFIGURED_URL = os.getenv("DATABASE_URL", "").strip()

DB_URL = _CONFIGURED_URL or SQLITE_DEV_URL

# True when DB_URL still points at the local dev file. seed_dev_db.py checks
# this before unlinking DB_PATH: with DATABASE_URL set to a real server,
# deleting app_dev.db would silently destroy an unrelated local file while
# seeding somewhere else entirely.
IS_SQLITE_DEV = DB_URL == SQLITE_DEV_URL


def get_engine():
    return create_engine(DB_URL)


def describe_config() -> dict:
    """Connection facts safe to print — mirrors moodle_db.describe_config().

    A DATABASE_URL for a real server embeds its password, so report only
    which backend is in use and where the URL came from, never the URL.
    """
    return {
        "backend": DB_URL.split(":", 1)[0],
        "source": "DATABASE_URL" if _CONFIGURED_URL else "default (sqlite dev)",
        "sqlite_dev": IS_SQLITE_DEV,
        "db_file": str(DB_PATH) if IS_SQLITE_DEV else "(not a file backend)",
    }
