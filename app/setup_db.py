"""Build (or rebuild) the MediTrack database from the sql/ folder.

    python app/setup_db.py           # drop -> DDL -> PL/SQL -> triggers -> seed -> queries
    python app/setup_db.py --demo    # ... then also run 07_dml_demo.sql (T1-T7)

Same result as running sql/00_build_all.sql in SQL*Plus.
"""

import sys

import oracledb
from tabulate import tabulate

from db import BUILD_ORDER, get_connection, run_script


def print_result(kind, payload):
    if kind == "rows":
        columns, rows = payload
        print(tabulate(rows, headers=columns, tablefmt="simple"))
        print()
    else:
        print("  " + payload)


def main():
    files = list(BUILD_ORDER)
    if "--demo" in sys.argv:
        files.append("07_dml_demo.sql")
    quiet = "--quiet" in sys.argv

    connection = get_connection()
    for filename in files:
        print(f"==== {filename} ====")
        try:
            run_script(connection, filename, None if quiet else print_result)
        except oracledb.DatabaseError as exc:
            print(f"FAILED in {filename}: {exc}")
            sys.exit(1)
    print("Build complete.")


if __name__ == "__main__":
    main()
