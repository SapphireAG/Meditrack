"""Connection helper for MediTrack.

Credentials come only from environment variables (or a local .env file
that is never committed):
    ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN   e.g. localhost:1521/FREEPDB1
"""

import os
import re
from pathlib import Path

import oracledb

APP_DIR = Path(__file__).resolve().parent
SQL_DIR = APP_DIR.parent / "sql"

# Order in which the SQL files build a clean database (triggers before seed).
BUILD_ORDER = [
    "99_drop_all.sql",
    "01_ddl.sql",
    "04_functions.sql",
    "05_procedures.sql",
    "06_triggers.sql",
    "02_seed_data.sql",
    "03_queries.sql",
]


def _load_env_file():
    """Read app/.env (KEY=VALUE lines) into os.environ if present."""
    env_file = APP_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def get_connection():
    """Open a thin-mode connection using the ORACLE_* environment variables."""
    _load_env_file()
    missing = [k for k in ("ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_DSN") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing)
            + ". Copy app/.env.example to app/.env and fill it in."
        )
    return oracledb.connect(
        user=os.environ["ORACLE_USER"],
        password=os.environ["ORACLE_PASSWORD"],
        dsn=os.environ["ORACLE_DSN"],
    )


def business_error(exc):
    """Turn an oracledb.DatabaseError into (code, clean message).

    ORA-20001..20099 are our own business rules; for those we show only the
    message we raised. Constraint violations are explained by constraint name.
    """
    error = exc.args[0]
    code = getattr(error, "code", None)
    message = getattr(error, "message", str(error))
    first_line = message.splitlines()[0]
    if code and 20001 <= code <= 20099:
        # "ORA-20003: Slot 09:00 ... taken" -> "Slot 09:00 ... taken"
        return code, re.sub(r"^ORA-\d+:\s*", "", first_line)
    constraint = re.search(r"\(([A-Z0-9_$#]+)\.([A-Z0-9_$#]+)\)", first_line)
    if code == 1 and constraint:
        return code, f"Duplicate value: violates unique constraint {constraint.group(2)}"
    if code == 2290 and constraint:
        return code, f"Value not allowed: violates check constraint {constraint.group(2)}"
    if code == 2291 and constraint:
        return code, f"Referenced row does not exist: foreign key {constraint.group(2)}"
    if code == 2292 and constraint:
        return code, f"Row is still referenced by child rows: foreign key {constraint.group(2)}"
    return code, first_line


# ---------------------------------------------------------------------------
# SQL*Plus-style script runner (used by setup_db.py and the Streamlit admin)
# ---------------------------------------------------------------------------
_PLSQL_START = re.compile(
    r"^\s*(CREATE\s+(OR\s+REPLACE\s+)?(PROCEDURE|FUNCTION|TRIGGER|PACKAGE)|BEGIN|DECLARE)\b",
    re.IGNORECASE,
)
_SQLPLUS_COMMAND = re.compile(r"^\s*(SET|PROMPT|SPOOL|@@?)\b", re.IGNORECASE)


def split_script(text):
    """Split a SQL*Plus script into executable statements.

    SQL statements end with ';' at the end of a line. PL/SQL blocks
    (CREATE PROCEDURE/FUNCTION/TRIGGER, BEGIN, DECLARE) end with a line
    holding only '/'. SQL*Plus commands (SET, PROMPT) are skipped.
    """
    statements = []
    buffer = []
    in_plsql = False
    for line in text.splitlines():
        stripped = line.strip()
        if not buffer:
            if not stripped or stripped.startswith("--") or _SQLPLUS_COMMAND.match(line):
                continue
            in_plsql = bool(_PLSQL_START.match(line))
        if in_plsql:
            if stripped == "/":
                statements.append("\n".join(buffer).strip())
                buffer = []
            else:
                buffer.append(line)
        else:
            # drop a trailing "-- comment" (one with no quote after it) before looking for ';'
            line = re.sub(r"\s--[^']*$", "", line)
            stripped = line.strip()
            buffer.append(line)
            if stripped.endswith(";") and not stripped.startswith("--"):
                statements.append("\n".join(buffer).strip().rstrip(";"))
                buffer = []
    if buffer and "".join(buffer).strip():
        statements.append("\n".join(buffer).strip().rstrip(";"))
    return statements


def read_dbms_output(cursor):
    """Fetch every line queued by DBMS_OUTPUT.PUT_LINE."""
    lines = []
    line_var = cursor.var(str)
    status_var = cursor.var(int)
    while True:
        cursor.callproc("dbms_output.get_line", (line_var, status_var))
        if status_var.getvalue() != 0:
            break
        lines.append(line_var.getvalue())
    return lines


def run_script(connection, filename, on_result=None):
    """Execute one file from sql/. on_result(kind, payload) receives output."""
    text = (SQL_DIR / filename).read_text()
    cursor = connection.cursor()
    cursor.callproc("dbms_output.enable", (None,))
    for statement in split_script(text):
        cursor.execute(statement)
        if cursor.warning:
            # PL/SQL that compiled with errors only raises a warning; stop here
            errors = cursor.execute(
                "SELECT name, line, position, text FROM user_errors ORDER BY name, sequence"
            ).fetchall()
            raise RuntimeError(f"{filename}: compilation error {cursor.warning}\n{errors}")
        if cursor.description and on_result:
            columns = [d[0] for d in cursor.description]
            on_result("rows", (columns, cursor.fetchall()))
        for line in read_dbms_output(cursor):
            if on_result:
                on_result("output", line)
    connection.commit()
