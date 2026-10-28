"""MediTrack service layer: one function per clinic transaction (T1-T7).

Both front ends (the CLI in main.py and the Streamlit UI in streamlit_app.py)
call these functions, so the database logic lives in exactly one place.

Every transaction returns a TxResult describing the
"User Operation -> SQL/PL/SQL -> Database -> Result" flow:
the operation, the tables touched, the components run, the statements
executed, the rows affected and the outcome.

Rules:
  * every value from the user goes in through a bind variable (:name)
  * procedures via cursor.callproc, functions via cursor.callfunc
  * one commit per transaction; any error rolls the whole unit back
"""

import re
from dataclasses import dataclass, field

import oracledb

from db import SQL_DIR, business_error, read_dbms_output


@dataclass
class TxResult:
    operation: str
    tables: list
    components: list
    statements: list = field(default_factory=list)
    rows_affected: dict = field(default_factory=dict)
    result: str = ""
    ok: bool = True
    error_code: int = None
    columns: list = None
    rows: list = None
    output: list = field(default_factory=list)


def _fail(tx, connection, exc):
    """Roll back the unit of work and record the business-rule message."""
    connection.rollback()
    tx.ok = False
    tx.rows_affected = {}          # everything in this unit of work was rolled back
    tx.error_code, tx.result = business_error(exc)
    return tx


def _select(connection, sql, params=None):
    cursor = connection.cursor()
    cursor.execute(sql, params or {})
    columns = [d[0] for d in cursor.description]
    return columns, cursor.fetchall()


# ---------------------------------------------------------------------------
# Lookups used by the menus / forms
# ---------------------------------------------------------------------------
def list_patients(connection):
    return _select(connection, """
        SELECT patient_id, first_name || ' ' || last_name AS name, phone,
               patient_total_due(patient_id) AS total_due
          FROM patient ORDER BY patient_id""")


def list_doctors(connection, active_only=False):
    sql = """SELECT doctor_id, full_name, specialization, consultation_fee,
                    max_daily_appts, status,
                    doctor_daily_load(doctor_id, TRUNC(SYSDATE)) AS load_today
               FROM doctor"""
    if active_only:
        sql += " WHERE status = 'ACTIVE'"
    return _select(connection, sql + " ORDER BY doctor_id")


def list_tests(connection):
    return _select(connection, """
        SELECT test_code, test_name, category, price, unit, normal_min, normal_max,
               turnaround_hrs
          FROM test_catalog ORDER BY category, test_code""")


def list_appointments(connection, statuses=None, patient_id=None, doctor_id=None, on_date=None):
    sql = """SELECT a.appointment_id, TO_CHAR(a.appt_date, 'YYYY-MM-DD') AS appt_date,
                    a.slot_time, p.first_name || ' ' || p.last_name AS patient,
                    d.full_name AS doctor, a.status,
                    (SELECT COUNT(*) FROM bill b WHERE b.appointment_id = a.appointment_id) AS billed,
                    a.reason, d.specialization, a.patient_id, a.doctor_id
               FROM appointment a
               JOIN patient p ON p.patient_id = a.patient_id
               JOIN doctor  d ON d.doctor_id  = a.doctor_id
              WHERE 1 = 1"""
    params = {}
    if statuses:
        names = [f":s{i}" for i in range(len(statuses))]
        sql += f" AND a.status IN ({', '.join(names)})"
        params.update({f"s{i}": s for i, s in enumerate(statuses)})
    if patient_id:
        sql += " AND a.patient_id = :patient_id"
        params["patient_id"] = patient_id
    if doctor_id:
        sql += " AND a.doctor_id = :doctor_id"
        params["doctor_id"] = doctor_id
    if on_date:
        sql += " AND a.appt_date = TRUNC(:on_date)"
        params["on_date"] = on_date
    return _select(connection, sql + " ORDER BY a.appt_date DESC, a.slot_time", params)


def list_samples(connection, appointment_id=None, statuses=None, doctor_id=None, patient_id=None):
    sql = """SELECT s.sample_id, s.appointment_id, s.test_code, tc.test_name, s.sample_type,
                    s.status, TO_CHAR(s.collected_on, 'YYYY-MM-DD HH24:MI') AS collected_on,
                    r.result_value, r.result_flag
               FROM sample s
               JOIN test_catalog tc ON tc.test_code = s.test_code
               LEFT JOIN test_result r ON r.sample_id = s.sample_id
              WHERE 1 = 1"""
    params = {}
    if appointment_id:
        sql += " AND s.appointment_id = :appt_id"
        params["appt_id"] = appointment_id
    if statuses:
        names = [f":st{i}" for i in range(len(statuses))]
        sql += f" AND s.status IN ({', '.join(names)})"
        params.update({f"st{i}": s for i, s in enumerate(statuses)})
    if doctor_id:
        sql += """ AND s.appointment_id IN (SELECT appointment_id FROM appointment
                                             WHERE doctor_id = :doctor_id)"""
        params["doctor_id"] = doctor_id
    if patient_id:
        sql += """ AND s.appointment_id IN (SELECT appointment_id FROM appointment
                                             WHERE patient_id = :patient_id)"""
        params["patient_id"] = patient_id
    return _select(connection, sql + " ORDER BY s.sample_id DESC", params)


def list_bills(connection, open_only=False, patient_id=None):
    sql = """SELECT bill_id, appointment_id, patient_id, patient, doctor, total_amt,
                    amount_paid, balance, payment_status, payment_mode,
                    TO_CHAR(bill_date, 'YYYY-MM-DD') AS bill_date, consultation_amt, test_amt,
                    discount_pct
               FROM v_bill_summary
              WHERE 1 = 1"""
    params = {}
    if open_only:
        sql += " AND payment_status <> 'PAID'"
    if patient_id:
        sql += " AND patient_id = :patient_id"
        params["patient_id"] = patient_id
    return _select(connection, sql + " ORDER BY bill_id DESC", params)


def list_results(connection, patient_id=None, doctor_id=None, abnormal_only=False):
    """Test results with the patient, the ordering doctor and the normal range."""
    sql = """SELECT r.result_id, s.sample_id, a.appointment_id,
                    TO_CHAR(r.result_date, 'YYYY-MM-DD') AS result_date,
                    tc.test_name, r.result_value, tc.unit, tc.normal_min, tc.normal_max,
                    r.result_flag, p.first_name || ' ' || p.last_name AS patient,
                    d.full_name AS doctor
               FROM test_result r
               JOIN sample s        ON s.sample_id      = r.sample_id
               JOIN test_catalog tc ON tc.test_code     = s.test_code
               JOIN appointment a   ON a.appointment_id = s.appointment_id
               JOIN patient p       ON p.patient_id     = a.patient_id
               JOIN doctor d        ON d.doctor_id      = a.doctor_id
              WHERE 1 = 1"""
    params = {}
    if patient_id:
        sql += " AND a.patient_id = :patient_id"
        params["patient_id"] = patient_id
    if doctor_id:
        sql += " AND a.doctor_id = :doctor_id"
        params["doctor_id"] = doctor_id
    if abnormal_only:
        sql += " AND r.result_flag <> 'NORMAL'"
    return _select(connection, sql + " ORDER BY r.result_date DESC, r.result_id DESC", params)


def patient_profile(connection, patient_id):
    """One patient as a dict, with their total due from patient_total_due()."""
    columns, rows = _select(connection, """
        SELECT patient_id, first_name, last_name, TO_CHAR(dob, 'YYYY-MM-DD') AS dob,
               gender, phone, email, address, TO_CHAR(registered_on, 'YYYY-MM-DD') AS registered_on,
               TRUNC(MONTHS_BETWEEN(SYSDATE, dob) / 12) AS age
          FROM patient WHERE patient_id = :patient_id""", {"patient_id": patient_id})
    if not rows:
        return None
    profile = dict(zip([c.lower() for c in columns], rows[0]))
    profile["total_due"] = connection.cursor().callfunc("patient_total_due", float, [patient_id])
    return profile


def taken_slots(connection, doctor_id, patient_id, appt_date):
    """Slots on appt_date already held (non-CANCELLED) by this doctor or this patient."""
    columns, rows = _select(connection, """
        SELECT slot_time,
               CASE WHEN doctor_id = :doctor_id THEN 'doctor' ELSE 'patient' END AS held_by
          FROM appointment
         WHERE appt_date = TRUNC(:appt_date)
           AND status <> 'CANCELLED'
           AND (doctor_id = :doctor_id OR patient_id = :patient_id)""",
        {"doctor_id": doctor_id, "patient_id": patient_id, "appt_date": appt_date})
    return {slot: held_by for slot, held_by in rows}


def db_today(connection):
    """TRUNC(SYSDATE) as a Python date. The UI uses the database's idea of 'today' so that
    the screen and the procedures (which use SYSDATE) always agree, even across time zones."""
    return connection.cursor().execute("SELECT TRUNC(SYSDATE) FROM dual").fetchone()[0].date()


def doctor_load(connection, doctor_id, on_date):
    """doctor_daily_load(): non-cancelled appointments the doctor has on that date."""
    return connection.cursor().callfunc("doctor_daily_load", int, [doctor_id, on_date])


def billed_per_day(connection, days=30):
    """Total billed per day over the last `days` days (admin dashboard chart)."""
    return _select(connection, """
        SELECT TO_CHAR(bill_date, 'YYYY-MM-DD') AS bill_day, SUM(total_amt) AS billed
          FROM bill
         WHERE bill_date >= TRUNC(SYSDATE) - :days
         GROUP BY TO_CHAR(bill_date, 'YYYY-MM-DD')
         ORDER BY bill_day""", {"days": days})


def dashboard_counts(connection):
    columns, rows = _select(connection, """
        SELECT (SELECT COUNT(*) FROM patient) AS patients,
               (SELECT COUNT(*) FROM appointment
                 WHERE appt_date = TRUNC(SYSDATE) AND status <> 'CANCELLED') AS today_appts,
               (SELECT COUNT(*) FROM sample
                 WHERE status IN ('COLLECTED', 'PROCESSING')) AS pending_samples,
               (SELECT NVL(SUM(total_amt - amount_paid), 0) FROM bill) AS outstanding,
               (SELECT COUNT(*) FROM test_result WHERE result_flag <> 'NORMAL') AS abnormal
          FROM dual""")
    return dict(zip([c.lower() for c in columns], rows[0]))


# ---------------------------------------------------------------------------
# T1. Register patient + book appointment
# ---------------------------------------------------------------------------
def t1_register_patient(connection, first_name, last_name, dob, gender, phone, email, address):
    tx = TxResult("T1a. Register patient", ["PATIENT"], ["INSERT PATIENT", "seq_patient"])
    sql = """INSERT INTO patient (patient_id, first_name, last_name, dob, gender, phone, email, address)
             VALUES (seq_patient.NEXTVAL, :first_name, :last_name, :dob, :gender, :phone, :email, :address)
             RETURNING patient_id INTO :new_id"""
    tx.statements.append(sql)
    cursor = connection.cursor()
    new_id = cursor.var(int)
    try:
        cursor.execute(sql, first_name=first_name, last_name=last_name, dob=dob, gender=gender,
                       phone=phone, email=email or None, address=address or None, new_id=new_id)
        tx.rows_affected["PATIENT inserted"] = cursor.rowcount
        connection.commit()
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    tx.result = f"Registered patient {new_id.getvalue()[0]}"
    return tx


def t1_book_appointment(connection, patient_id, doctor_id, appt_date, slot, reason):
    tx = TxResult("T1b. Book appointment", ["DOCTOR", "APPOINTMENT"],
                  ["doctor_daily_load (function)", "book_appointment (procedure)",
                   "trg_no_double_booking (trigger)"])
    cursor = connection.cursor()
    try:
        load_before = cursor.callfunc("doctor_daily_load", int, [doctor_id, appt_date])
        tx.statements.append(f"doctor_daily_load({doctor_id}, {appt_date}) -> {load_before}")
        appt_id = cursor.var(int)
        cursor.callproc("book_appointment", [patient_id, doctor_id, appt_date, slot, reason, appt_id])
        tx.statements.append(
            f"book_appointment({patient_id}, {doctor_id}, {appt_date}, '{slot}', :reason, :appt_id OUT)")
        connection.commit()
        load_after = cursor.callfunc("doctor_daily_load", int, [doctor_id, appt_date])
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    tx.rows_affected["APPOINTMENT inserted"] = 1
    tx.result = (f"Booked appointment {appt_id.getvalue()} — doctor's load on {appt_date}: "
                 f"{load_before} -> {load_after}")
    return tx


# ---------------------------------------------------------------------------
# T2. Order tests / collect samples, update sample status
# ---------------------------------------------------------------------------
def t2_order_tests(connection, appointment_id, tests, collected_by):
    """tests = list of (test_code, sample_type). All inserted in one transaction."""
    tx = TxResult("T2a. Order tests and collect samples", ["SAMPLE"],
                  ["INSERT SAMPLE", "seq_sample", "uq_sample_appt_test (constraint)"])
    sql = """INSERT INTO sample (sample_id, appointment_id, test_code, sample_type, collected_by)
             VALUES (seq_sample.NEXTVAL, :appt_id, :test_code, :sample_type, :collected_by)"""
    tx.statements.append(sql)
    cursor = connection.cursor()
    try:
        for test_code, sample_type in tests:
            cursor.execute(sql, appt_id=appointment_id, test_code=test_code,
                           sample_type=sample_type, collected_by=collected_by or None)
        connection.commit()
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    tx.rows_affected["SAMPLE inserted"] = len(tests)
    tx.columns, tx.rows = list_samples(connection, appointment_id=appointment_id)
    tx.result = f"{len(tests)} sample(s) collected for appointment {appointment_id}"
    return tx


def t2_update_sample_status(connection, sample_id, status, remarks):
    tx = TxResult("T2b. Update sample status", ["SAMPLE"], ["UPDATE SAMPLE", "ck_sample_status"])
    sql = """UPDATE sample SET status = :status, remarks = NVL(:remarks, remarks)
              WHERE sample_id = :sample_id"""
    tx.statements.append(sql)
    cursor = connection.cursor()
    try:
        cursor.execute(sql, status=status, remarks=remarks or None, sample_id=sample_id)
        tx.rows_affected["SAMPLE updated"] = cursor.rowcount
        connection.commit()
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    tx.result = (f"Sample {sample_id} is now {status}" if cursor.rowcount
                 else f"No sample with id {sample_id}")
    tx.ok = cursor.rowcount > 0
    return tx


# ---------------------------------------------------------------------------
# T3. Enter a test result (flag set by trigger)
# ---------------------------------------------------------------------------
def t3_enter_result(connection, sample_id, value, verified_by, remarks):
    tx = TxResult("T3. Enter test result", ["TEST_RESULT", "SAMPLE", "TEST_CATALOG"],
                  ["INSERT TEST_RESULT", "trg_flag_result (trigger)"])
    sql = """INSERT INTO test_result (result_id, sample_id, result_value, verified_by, remarks)
             VALUES (seq_test_result.NEXTVAL, :sample_id, :value, :verified_by, :remarks)"""
    tx.statements.append(sql)
    cursor = connection.cursor()
    try:
        cursor.execute(sql, sample_id=sample_id, value=value,
                       verified_by=verified_by or None, remarks=remarks or None)
        tx.rows_affected["TEST_RESULT inserted"] = cursor.rowcount
        tx.rows_affected["SAMPLE updated by trigger"] = 1
        connection.commit()
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    check_sql = """SELECT r.result_value, tc.unit, tc.normal_min, tc.normal_max,
                          r.result_flag, s.status AS sample_status
                     FROM test_result r
                     JOIN sample s        ON s.sample_id  = r.sample_id
                     JOIN test_catalog tc ON tc.test_code = s.test_code
                    WHERE r.sample_id = :sample_id"""
    tx.columns, tx.rows = _select(connection, check_sql, {"sample_id": sample_id})
    flag, sample_status = tx.rows[0][4], tx.rows[0][5]
    tx.result = f"Result saved. Trigger set flag = {flag} and sample status = {sample_status}"
    return tx


# ---------------------------------------------------------------------------
# T4. Complete the visit and generate the bill — ONE unit of work
# ---------------------------------------------------------------------------
def t4_complete_and_bill(connection, appointment_id, discount_pct):
    tx = TxResult("T4. Complete visit and generate bill",
                  ["APPOINTMENT", "DOCTOR", "SAMPLE", "TEST_CATALOG", "BILL"],
                  ["UPDATE APPOINTMENT", "generate_bill (procedure)", "ck_bill_total_amt"])
    sql = """UPDATE appointment SET status = 'COMPLETED'
              WHERE appointment_id = :appt_id AND status = 'BOOKED'"""
    tx.statements.append(sql)
    tx.statements.append(f"generate_bill({appointment_id}, {discount_pct})")
    cursor = connection.cursor()
    try:
        cursor.execute(sql, appt_id=appointment_id)
        tx.rows_affected["APPOINTMENT updated"] = cursor.rowcount
        cursor.callproc("generate_bill", [appointment_id, discount_pct])
        tx.rows_affected["BILL inserted"] = 1
        connection.commit()          # both steps succeed together, or neither does
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    tx.columns, tx.rows = _select(connection, """
        SELECT bill_id, consultation_amt, test_amt, discount_pct, total_amt, payment_status
          FROM bill WHERE appointment_id = :appt_id""", {"appt_id": appointment_id})
    tx.result = f"Bill {tx.rows[0][0]} raised for appointment {appointment_id}: total ₹{tx.rows[0][4]:,.2f}"
    return tx


# ---------------------------------------------------------------------------
# T5. Record a payment and check dues
# ---------------------------------------------------------------------------
def t5_record_payment(connection, bill_id, amount, mode):
    tx = TxResult("T5. Record payment and check dues", ["BILL", "APPOINTMENT"],
                  ["record_payment (procedure)", "trg_payment_status (trigger)",
                   "patient_total_due (function)"])
    cursor = connection.cursor()
    try:
        cursor.execute("""SELECT a.patient_id FROM bill b
                            JOIN appointment a ON a.appointment_id = b.appointment_id
                           WHERE b.bill_id = :bill_id""", bill_id=bill_id)
        row = cursor.fetchone()
        patient_id = row[0] if row else None
        due_before = cursor.callfunc("patient_total_due", float, [patient_id]) if patient_id else 0
        cursor.callproc("record_payment", [bill_id, amount, mode])
        tx.statements.append(f"record_payment({bill_id}, {amount}, '{mode}')")
        connection.commit()
        due_after = cursor.callfunc("patient_total_due", float, [patient_id])
        tx.statements.append(f"patient_total_due({patient_id}) -> {due_before} then {due_after}")
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    tx.rows_affected["BILL updated"] = 1
    tx.columns, tx.rows = _select(connection, """
        SELECT bill_id, total_amt, amount_paid, total_amt - amount_paid AS balance,
               payment_status, payment_mode
          FROM bill WHERE bill_id = :bill_id""", {"bill_id": bill_id})
    tx.result = (f"Payment of ₹{amount:,.2f} recorded; bill is {tx.rows[0][4]}. "
                 f"Patient {patient_id} total due: ₹{due_before:,.2f} -> ₹{due_after:,.2f}")
    return tx


# ---------------------------------------------------------------------------
# T6. End-of-day billing (procedure with an explicit cursor)
# ---------------------------------------------------------------------------
def t6_end_of_day_billing(connection, bill_date):
    tx = TxResult("T6. End-of-day billing", ["APPOINTMENT", "BILL", "DOCTOR", "SAMPLE", "TEST_CATALOG"],
                  ["end_of_day_billing (procedure, cursor c_unbilled)", "generate_bill (procedure)"])
    cursor = connection.cursor()
    try:
        cursor.callproc("dbms_output.enable", [None])
        cursor.callproc("end_of_day_billing", [bill_date])   # commits once inside
        tx.statements.append(f"end_of_day_billing({bill_date})")
        tx.output = read_dbms_output(cursor)
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    billed = sum(1 for line in tx.output if line.startswith("Billed"))
    tx.rows_affected["BILL inserted"] = billed
    tx.result = tx.output[-1] if tx.output else "No output"
    return tx


# ---------------------------------------------------------------------------
# T7. Cancel a visit; delete a rejected sample (cascade to TEST_RESULT)
# ---------------------------------------------------------------------------
def t7_cancel_appointment(connection, appointment_id):
    tx = TxResult("T7a. Cancel appointment", ["APPOINTMENT"], ["UPDATE APPOINTMENT"])
    sql = """UPDATE appointment SET status = 'CANCELLED'
              WHERE appointment_id = :appt_id AND status = 'BOOKED'"""
    tx.statements.append(sql)
    cursor = connection.cursor()
    try:
        cursor.execute(sql, appt_id=appointment_id)
        tx.rows_affected["APPOINTMENT updated"] = cursor.rowcount
        connection.commit()
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    if cursor.rowcount == 0:
        tx.ok = False
        tx.result = f"Appointment {appointment_id} is not BOOKED, nothing cancelled"
    else:
        tx.result = f"Appointment {appointment_id} cancelled; its slot can be booked again"
    return tx


def t7_delete_rejected_sample(connection, sample_id):
    tx = TxResult("T7b. Delete rejected sample", ["SAMPLE", "TEST_RESULT"],
                  ["DELETE SAMPLE", "fk_test_result_sample_id ON DELETE CASCADE"])
    count_sql = "SELECT COUNT(*) FROM test_result WHERE sample_id = :sample_id"
    sql = "DELETE FROM sample WHERE sample_id = :sample_id AND status = 'REJECTED'"
    tx.statements.append(sql)
    cursor = connection.cursor()
    try:
        results_before = cursor.execute(count_sql, sample_id=sample_id).fetchone()[0]
        cursor.execute(sql, sample_id=sample_id)
        deleted = cursor.rowcount
        results_after = cursor.execute(count_sql, sample_id=sample_id).fetchone()[0]
        connection.commit()
    except oracledb.DatabaseError as exc:
        return _fail(tx, connection, exc)
    tx.rows_affected["SAMPLE deleted"] = deleted
    tx.rows_affected["TEST_RESULT deleted by cascade"] = results_before - results_after
    if deleted == 0:
        tx.ok = False
        tx.result = f"Sample {sample_id} is not REJECTED (or does not exist); nothing deleted"
    else:
        tx.result = (f"Sample {sample_id} deleted; ON DELETE CASCADE removed "
                     f"{results_before - results_after} result row(s)")
    return tx


# ---------------------------------------------------------------------------
# Reports: the 15 queries, read straight from sql/03_queries.sql
# ---------------------------------------------------------------------------
def load_queries():
    """Parse 03_queries.sql into a list of {num, title, purpose, fr, concept, output, sql}."""
    text = (SQL_DIR / "03_queries.sql").read_text()
    blocks = re.split(r"^-- -{20,}\n(?=-- Q\d+\.)", text, flags=re.MULTILINE)
    queries = []
    for block in blocks:
        header = re.match(r"-- Q(\d+)\.\s*(.+)", block)
        if not header:
            continue
        meta = dict(re.findall(r"^-- (Purpose|FR|Concept|Output)\s*:\s*(.+)$", block, re.MULTILINE))
        body = re.split(r"^-- -{20,}\n", block, maxsplit=1, flags=re.MULTILINE)[1]
        statements = [s.strip() for s in body.split(";") if s.strip()]
        select_sql = [s for s in statements if s.upper().startswith(("SELECT", "WITH"))][-1]
        queries.append({
            "num": int(header.group(1)),
            "title": header.group(2).strip(),
            "purpose": meta.get("Purpose", ""),
            "fr": meta.get("FR", ""),
            "concept": meta.get("Concept", ""),
            "output": meta.get("Output", ""),
            "sql": select_sql,
            "full_sql": body.strip(),
        })
    return queries


def run_query(connection, sql):
    return _select(connection, sql)


# ---------------------------------------------------------------------------
# Schema explorer: read constraints, triggers, procedures from the data dictionary
# ---------------------------------------------------------------------------
def schema_constraints(connection, table_name=None):
    sql = """SELECT c.table_name, c.constraint_name,
                    DECODE(c.constraint_type, 'P', 'PRIMARY KEY', 'R', 'FOREIGN KEY',
                           'U', 'UNIQUE', 'C', 'CHECK / NOT NULL') AS type,
                    LISTAGG(cc.column_name, ', ') WITHIN GROUP (ORDER BY cc.position) AS columns,
                    r.table_name AS references_table,
                    c.delete_rule
               FROM user_constraints c
               JOIN user_cons_columns cc ON cc.constraint_name = c.constraint_name
               LEFT JOIN user_constraints r ON r.constraint_name = c.r_constraint_name
              WHERE c.table_name IN ('PATIENT', 'DOCTOR', 'TEST_CATALOG', 'APPOINTMENT',
                                     'SAMPLE', 'TEST_RESULT', 'BILL')"""
    params = {}
    if table_name:
        sql += " AND c.table_name = :table_name"
        params["table_name"] = table_name
    sql += """ GROUP BY c.table_name, c.constraint_name, c.constraint_type, r.table_name, c.delete_rule
               ORDER BY c.table_name, DECODE(c.constraint_type, 'P', 1, 'R', 2, 'U', 3, 4), c.constraint_name"""
    return _select(connection, sql, params)


def schema_columns(connection, table_name):
    return _select(connection, """
        SELECT column_name, data_type ||
               CASE WHEN data_type IN ('VARCHAR2', 'CHAR') THEN '(' || char_length || ')'
                    WHEN data_type = 'NUMBER' AND data_precision IS NOT NULL
                         THEN '(' || data_precision || NVL2(NULLIF(data_scale, 0), ',' || data_scale, '') || ')'
               END AS data_type,
               nullable, data_default
          FROM user_tab_columns
         WHERE table_name = :table_name
         ORDER BY column_id""", {"table_name": table_name})


def schema_plsql(connection):
    return _select(connection, """
        SELECT object_name, object_type, status, TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI') AS compiled
          FROM user_objects
         WHERE object_type IN ('PROCEDURE', 'FUNCTION', 'TRIGGER', 'VIEW', 'SEQUENCE')
         ORDER BY object_type, object_name""")


def schema_row_counts(connection):
    tables = ["PATIENT", "DOCTOR", "TEST_CATALOG", "APPOINTMENT", "SAMPLE", "TEST_RESULT", "BILL"]
    cursor = connection.cursor()
    counts = []
    for table in tables:   # table names come from this fixed list, never from user input
        counts.append((table, cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]))
    return ["TABLE_NAME", "ROWS"], counts


def plsql_source(connection, name):
    columns, rows = _select(connection, """
        SELECT text FROM user_source WHERE name = :name ORDER BY line""", {"name": name.upper()})
    return "".join(r[0] for r in rows)


# ---------------------------------------------------------------------------
# Constraint lab: deliberately break a rule, show the database refusing it
# ---------------------------------------------------------------------------
INTEGRITY_CHECKS = [
    {
        "title": "Double booking (same doctor, same slot)",
        "rule": "trg_no_double_booking → ORA-20003",
        "sql": "INSERT INTO appointment (appointment_id, patient_id, doctor_id, appt_date, slot_time) "
               "VALUES (seq_appointment.NEXTVAL, 100009, 1001, TRUNC(SYSDATE), '10:00')",
    },
    {
        "title": "Invalid gender code",
        "rule": "ck_patient_gender (CHECK)",
        "sql": "INSERT INTO patient (patient_id, first_name, last_name, dob, gender, phone) "
               "VALUES (seq_patient.NEXTVAL, 'Test', 'User', DATE '2000-01-01', 'X', '9000000001')",
    },
    {
        "title": "Duplicate phone number",
        "rule": "uq_patient_phone (UNIQUE)",
        "sql": "INSERT INTO patient (patient_id, first_name, last_name, dob, gender, phone) "
               "VALUES (seq_patient.NEXTVAL, 'Test', 'User', DATE '2000-01-01', 'M', '9876543210')",
    },
    {
        "title": "Appointment for a patient who does not exist",
        "rule": "fk_appointment_patient_id (FOREIGN KEY)",
        "sql": "INSERT INTO appointment (appointment_id, patient_id, doctor_id, appt_date, slot_time) "
               "VALUES (seq_appointment.NEXTVAL, 999999, 1001, TRUNC(SYSDATE) + 5, '09:00')",
    },
    {
        "title": "Slot time in the wrong format",
        "rule": "ck_appointment_slot_time (REGEXP_LIKE CHECK)",
        "sql": "INSERT INTO appointment (appointment_id, patient_id, doctor_id, appt_date, slot_time) "
               "VALUES (seq_appointment.NEXTVAL, 100001, 1001, TRUNC(SYSDATE) + 5, '9am')",
    },
    {
        "title": "Same test ordered twice in one visit",
        "rule": "uq_sample_appt_test (composite UNIQUE)",
        "sql": "INSERT INTO sample (sample_id, appointment_id, test_code, sample_type) "
               "VALUES (seq_sample.NEXTVAL, 500003, 'FBS', 'BLOOD')",
    },
    {
        "title": "Paying more than the bill total",
        "rule": "ck_bill_paid_le_total (CHECK)",
        "sql": "UPDATE bill SET amount_paid = total_amt + 100 WHERE bill_id = 900005",
    },
    {
        "title": "Discount above 50%",
        "rule": "ck_bill_discount_pct (CHECK)",
        "sql": "UPDATE bill SET discount_pct = 75, "
               "total_amt = ROUND((consultation_amt + test_amt) * 0.25, 2) WHERE bill_id = 900005",
    },
    {
        "title": "Deleting a doctor who has appointments",
        "rule": "fk_appointment_doctor_id (no ON DELETE → ORA-02292)",
        "sql": "DELETE FROM doctor WHERE doctor_id = 1001",
    },
    {
        "title": "Result for a sample that does not exist",
        "rule": "trg_flag_result → ORA-20031",
        "sql": "INSERT INTO test_result (result_id, sample_id, result_value) "
               "VALUES (seq_test_result.NEXTVAL, 999999, 5)",
    },
]


def try_violation(connection, sql):
    """Run a statement that should be refused; always roll back."""
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        rows = cursor.rowcount
        connection.rollback()
        return False, None, f"Statement was accepted ({rows} row(s)) and then rolled back"
    except oracledb.DatabaseError as exc:
        connection.rollback()
        code, message = business_error(exc)
        return True, code, message
