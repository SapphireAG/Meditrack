"""MediTrack menu-driven CLI.

    python app/main.py

One menu item per clinic transaction (T1-T7) plus the 15 reports. After
every transaction the app prints the full trace:
    Operation -> Tables touched -> SQL/PL/SQL run -> Rows affected -> Result
"""

from datetime import datetime

from tabulate import tabulate

import services as svc
from db import get_connection
from explain import explain


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------
def ask(prompt, default=None, cast=str, allow_blank=False):
    """Prompt until the value converts with `cast`."""
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {prompt}{suffix}: ").strip()
        if not raw and default is not None:
            raw = str(default)
        if not raw and allow_blank:
            return None
        try:
            return cast(raw)
        except ValueError:
            print("    ! invalid value, try again")


def as_date(text):
    return datetime.strptime(text, "%Y-%m-%d")


def show_table(columns, rows, limit=None):
    rows = rows[:limit] if limit else rows
    print(tabulate(rows, headers=columns, tablefmt="rounded_outline", floatfmt=".2f"))


def show_trace(tx):
    """Print the User Operation -> SQL/PLSQL -> Database -> Result flow."""
    status = "SUCCESS" if tx.ok else "REJECTED"
    print()
    print(f"  ┌─ {tx.operation}  [{status}]")
    print(f"  │ Tables touched : {', '.join(tx.tables)}")
    print(f"  │ Components run : {', '.join(tx.components)}")
    for statement in tx.statements:
        first, *rest = statement.strip().splitlines()
        print(f"  │ SQL/PL-SQL     : {first.strip()}")
        for line in rest:
            print(f"  │                  {line.strip()}")
    if tx.rows_affected:
        affected = ", ".join(f"{k}: {v}" for k, v in tx.rows_affected.items())
        print(f"  │ Rows affected  : {affected}")
    for line in tx.output:
        print(f"  │ DBMS_OUTPUT    : {line}")
    code = f" (ORA-{tx.error_code:05d})" if tx.error_code else ""
    print(f"  └─ Result{code}: {tx.result}")
    if not tx.ok:
        info = explain(tx.error_code, tx.result)
        print(f"     ✕ {info['title']}")
        for label, key in (("Why", "why"), ("Enforced by", "rule"), ("What to do", "fix")):
            if info[key]:
                print(f"       {label:<12}: {info[key]}")
    if tx.rows:
        show_table(tx.columns, tx.rows)
    print()


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------
def menu_t1(conn):
    print("\nT1. Register patient + book appointment")
    if ask("Register a new patient first? (y/n)", "n").lower() == "y":
        tx = svc.t1_register_patient(
            conn,
            ask("First name"), ask("Last name"),
            ask("Date of birth (YYYY-MM-DD)", cast=as_date),
            ask("Gender M/F/O").upper(), ask("Phone (10 digits)"),
            ask("Email", allow_blank=True), ask("Address", allow_blank=True))
        show_trace(tx)
        if not tx.ok:
            return
    show_table(*svc.list_doctors(conn))
    patient_id = ask("Patient ID", cast=int)
    doctor_id = ask("Doctor ID", cast=int)
    appt_date = ask("Date (YYYY-MM-DD)", svc.db_today(conn).isoformat(), cast=as_date)
    slot = ask("Slot (HH:MI, 24h)", "09:00")
    reason = ask("Reason", allow_blank=True)
    show_trace(svc.t1_book_appointment(conn, patient_id, doctor_id, appt_date, slot, reason))


def menu_t2(conn):
    print("\nT2. Order tests / collect samples")
    choice = ask("1 = order tests for a visit, 2 = update a sample's status", "1")
    if choice == "1":
        show_table(*svc.list_appointments(conn, ["BOOKED", "COMPLETED"]), limit=15)
        appt_id = ask("Appointment ID", cast=int)
        show_table(*svc.list_tests(conn))
        codes = ask("Test codes, comma separated (e.g. FBS,HBA1C)").upper().split(",")
        sample_type = ask("Sample type BLOOD/URINE/SALIVA/SWAB/OTHER", "BLOOD").upper()
        collected_by = ask("Collected by", "Lakshmi (Tech)")
        tests = [(code.strip(), sample_type) for code in codes if code.strip()]
        show_trace(svc.t2_order_tests(conn, appt_id, tests, collected_by))
    else:
        show_table(*svc.list_samples(conn, statuses=["COLLECTED", "PROCESSING"]))
        sample_id = ask("Sample ID", cast=int)
        status = ask("New status COLLECTED/PROCESSING/COMPLETED/REJECTED", "PROCESSING").upper()
        remarks = ask("Remarks", allow_blank=True)
        show_trace(svc.t2_update_sample_status(conn, sample_id, status, remarks))


def menu_t3(conn):
    print("\nT3. Enter test result")
    show_table(*svc.list_samples(conn, statuses=["COLLECTED", "PROCESSING"]))
    sample_id = ask("Sample ID", cast=int)
    value = ask("Result value", cast=float)
    verified_by = ask("Verified by (doctor ID)", 1004, cast=int)
    remarks = ask("Remarks", allow_blank=True)
    show_trace(svc.t3_enter_result(conn, sample_id, value, verified_by, remarks))


def menu_t4(conn):
    print("\nT4. Complete visit + generate bill")
    show_table(*svc.list_appointments(conn, ["BOOKED", "COMPLETED"]), limit=15)
    appt_id = ask("Appointment ID", cast=int)
    discount = ask("Discount % (0-50)", 0, cast=float)
    show_trace(svc.t4_complete_and_bill(conn, appt_id, discount))


def menu_t5(conn):
    print("\nT5. Record payment + dues check")
    show_table(*svc.list_bills(conn, open_only=True))
    bill_id = ask("Bill ID", cast=int)
    amount = ask("Amount (INR)", cast=float)
    mode = ask("Mode CASH/CARD/UPI/INSURANCE", "UPI").upper()
    show_trace(svc.t5_record_payment(conn, bill_id, amount, mode))


def menu_t6(conn):
    print("\nT6. End-of-day billing")
    bill_date = ask("Bill all completed visits of date (YYYY-MM-DD)", svc.db_today(conn).isoformat(), cast=as_date)
    show_trace(svc.t6_end_of_day_billing(conn, bill_date))


def menu_t7(conn):
    print("\nT7. Cancel visit / delete rejected sample")
    choice = ask("1 = cancel an appointment, 2 = delete a rejected sample", "1")
    if choice == "1":
        show_table(*svc.list_appointments(conn, ["BOOKED"]))
        show_trace(svc.t7_cancel_appointment(conn, ask("Appointment ID", cast=int)))
    else:
        show_table(*svc.list_samples(conn, statuses=["REJECTED"]))
        show_trace(svc.t7_delete_rejected_sample(conn, ask("Sample ID", cast=int)))


def menu_reports(conn):
    queries = svc.load_queries()
    print()
    for q in queries:
        print(f"  {q['num']:>2}. {q['title']:<60} [{q['fr']}]")
    num = ask("Report number (0 = all)", 0, cast=int)
    for q in queries:
        if num in (0, q["num"]):
            print(f"\n  Q{q['num']}. {q['title']}")
            print(f"  Purpose: {q['purpose']}\n  Concept: {q['concept']}")
            columns, rows = svc.run_query(conn, q["sql"])
            show_table(columns, rows)


def menu_lookup(conn):
    print("\n  1 patients  2 doctors  3 tests  4 appointments  5 samples  6 bills")
    choice = ask("Show", "1")
    lookups = {
        "1": svc.list_patients, "2": svc.list_doctors, "3": svc.list_tests,
        "4": svc.list_appointments, "5": svc.list_samples, "6": svc.list_bills,
    }
    if choice in lookups:
        show_table(*lookups[choice](conn))


MENU = [
    ("1", "T1  Register patient + book appointment", menu_t1),
    ("2", "T2  Order tests / collect samples", menu_t2),
    ("3", "T3  Enter test result", menu_t3),
    ("4", "T4  Complete visit + generate bill", menu_t4),
    ("5", "T5  Record payment + dues check", menu_t5),
    ("6", "T6  End-of-day billing (cursor)", menu_t6),
    ("7", "T7  Cancel visit / delete rejected sample", menu_t7),
    ("8", "Reports (15 queries)", menu_reports),
    ("9", "Look up data", menu_lookup),
]


def main():
    conn = get_connection()
    while True:
        print("\n========== MediTrack — Diagnostic Clinic ==========")
        for key, label, _ in MENU:
            print(f"  {key}. {label}")
        print("  0. Exit")
        choice = input("Choose: ").strip()
        if choice == "0":
            break
        for key, _, action in MENU:
            if choice == key:
                try:
                    action(conn)
                except (KeyboardInterrupt, EOFError):
                    print("\n  (cancelled)")
                break
        else:
            print("  ! unknown option")
    conn.close()


if __name__ == "__main__":
    main()
