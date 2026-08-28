"""Connection to the Moodle database behind elearning.abchorizon.com.

Deliberately simple: host, port, user, password, database — read from .env,
handed to pymysql, done. There is no connection pool, no ORM and no retry
logic, because none of that is what stands between us and the data.

What DOES stand between us and the data is reachability. Moodle binds
MariaDB to localhost on the server, so MOODLE_DB_HOST is only ever one of:

    1. 127.0.0.1 with an SSH tunnel running  (ssh -N -L 3307:127.0.0.1:3306 ...)
    2. the server's public IP, once port 3306 is opened to this machine

Credentials cannot substitute for either one — a closed port refuses the
handshake before a password is ever sent. `probe()` exists to say which of
those two situations we are in, in one line, instead of leaving a bare
OperationalError to be interpreted.

Read-only by contract: `query()` refuses anything that is not SELECT or
SHOW, and the connection never autocommits. The btec_ro grant is SELECT-only
on the server side as well, so this is a third lock on an already locked
door — the point is that a future well-meaning edit fails loudly here.
"""

from __future__ import annotations

import os
import socket

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

load_dotenv()

HOST = os.getenv("MOODLE_DB_HOST", "")
PORT = int(os.getenv("MOODLE_DB_PORT") or 3306)
USER = os.getenv("MOODLE_DB_USER", "")
PASSWORD = os.getenv("MOODLE_DB_PASSWORD", "")
NAME = os.getenv("MOODLE_DB_NAME", "")
PREFIX = os.getenv("MOODLE_DB_PREFIX", "mdl_")


class DatabaseError(RuntimeError):
    """Raised instead of leaking pymysql internals or the password."""


def is_configured() -> bool:
    return all([HOST, USER, PASSWORD, NAME])


def describe() -> dict:
    """Current settings, safe to print. The password is never included."""
    return {
        "host": HOST or "(unset)",
        "port": PORT,
        "database": NAME or "(unset)",
        "user": USER or "(unset)",
        "prefix": PREFIX,
        "password_set": bool(PASSWORD),
    }


def port_is_open(timeout: float = 8.0) -> bool:
    """Whether the TCP port accepts a connection at all.

    Checked before connecting so that "the port is shut" and "the password
    is wrong" stay distinguishable — they produce very similar-looking
    errors otherwise, and only one of them is fixable from this machine.
    """
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((HOST, PORT))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def connect():
    if not is_configured():
        raise DatabaseError(
            "MOODLE_DB_* is incomplete in .env — need HOST, USER, PASSWORD, NAME."
        )
    try:
        return pymysql.connect(
            host=HOST,
            port=PORT,
            user=USER,
            password=PASSWORD,
            database=NAME,
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=10,
            autocommit=False,
        )
    except Exception as exc:
        # pymysql error text can carry host/user/database; it never carries
        # the password, but keep the surface minimal regardless.
        raise DatabaseError(
            f"Could not connect to {NAME} at {HOST}:{PORT} as {USER!r} "
            f"({type(exc).__name__})."
        ) from None


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Runs one read-only statement and returns every row as a dict."""
    first = sql.strip().split(None, 1)[0].upper() if sql.strip() else ""
    if first not in {"SELECT", "SHOW"}:
        raise DatabaseError(
            f"Refused a non-read statement ({first or 'empty'}). This module "
            "is SELECT-only; writes to Moodle must go through the Web "
            "Services API, never through direct SQL."
        )
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())
    finally:
        connection.close()


def probe() -> dict:
    """One call that answers 'is the database usable, and if not, why?'.

    Returns a dict with `ok`, and on failure a `reason` and a `fix` naming
    the specific next action rather than a generic connection error.
    """
    if not is_configured():
        return {
            "ok": False,
            "reason": "MOODLE_DB_* is incomplete in .env.",
            "fix": "Fill in host, user, password and database name.",
        }

    if not port_is_open():
        local = HOST in {"127.0.0.1", "localhost"}
        return {
            "ok": False,
            "reason": f"Port {PORT} on {HOST} does not accept connections.",
            "fix": (
                f"Open the SSH tunnel: ssh -N -L {PORT}:127.0.0.1:3306 "
                "<user>@<server>"
                if local
                else f"Allow this machine's IP to reach port {PORT} on {HOST} "
                "(CloudPanel: enable remote database access + firewall rule)."
            ),
        }

    try:
        rows = query("SELECT VERSION() AS version, DATABASE() AS db")
        tables = query(
            "SELECT COUNT(*) AS n FROM information_schema.tables "
            "WHERE table_schema = %s",
            (NAME,),
        )
    except DatabaseError as exc:
        return {
            "ok": False,
            "reason": str(exc),
            "fix": "Port is open, so this is credentials or the GRANT. Check "
            f"that {USER!r} may connect from this host and has SELECT on {NAME}.",
        }

    return {
        "ok": True,
        "server": rows[0]["version"],
        "database": rows[0]["db"],
        "tables": tables[0]["n"],
    }
