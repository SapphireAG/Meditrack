# CLAUDE.md — MediTrack: Diagnostic Clinic Management System

Course project for **BCSE302L Database Systems** (VIT, School of Computer Science Engineering and Information Systems).
A diagnostic clinic database: patients book doctor appointments, doctors order lab tests, technicians record samples
and results, and billing staff raise bills and record payments.

The project is graded in three reviews. Everything built here must serve a real clinic operation — the guidelines
explicitly reject "a collection of independent SQL/PLSQL programs". Every query, procedure, function, cursor and
trigger must be traceable to a transaction (T1–T7 below).

## Stack

- **Database:** Oracle Database (SQL + PL/SQL). Target Oracle XE 21c / the lab's Oracle version.
- **Application:** Python 3 with the `oracledb` driver (thin mode, no Instant Client needed).
- **Interface:** menu-driven CLI (`app/main.py`). Optional: Streamlit front end if time allows.
- Do NOT use MySQL/PostgreSQL syntax. No `AUTO_INCREMENT`, no `LIMIT`, no `BOOLEAN` columns.

## Repository layout

```
sql/
  00_build_all.sql      -- SQL*Plus master script, runs the files below in build order
  01_ddl.sql            -- CREATE TABLE with all constraints, sequences, in dependency order
  02_seed_data.sql      -- >= 10 meaningful rows per table
  03_queries.sql        -- >= 15 queries, each with a comment: purpose + FR it serves
  04_functions.sql      -- patient_total_due, doctor_daily_load
  05_procedures.sql     -- book_appointment, generate_bill, record_payment, end_of_day_billing (cursor)
  06_triggers.sql       -- trg_no_double_booking, trg_flag_result, trg_payment_status
  07_dml_demo.sql       -- INSERT / UPDATE / DELETE demonstrations
  99_drop_all.sql       -- drops everything in reverse order (for clean re-runs)
app/
  db.py                 -- connection helper (reads credentials from env vars)
  services.py           -- one function per transaction T1–T7 (shared by both front ends)
  explain.py            -- ORA code -> plain-language title / why / enforcing rule / fix (both front ends)
  main.py               -- menu; one menu item per transaction T1–T7 + reports
  streamlit_app.py      -- Streamlit site map: home + Patient / Doctor / Administration portals
  pages_patient.py, pages_doctor.py, pages_admin.py  -- the portal pages
  ui.py                 -- theme CSS and shared components (cards, pills, error panel, trace)
  assets/               -- logo SVGs + icon.png
  setup_db.py           -- builds the DB from sql/ (same order as 00_build_all.sql)
  .env.example          -- ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN
.streamlit/config.toml  -- light-blue/white theme (run streamlit from the project root)
docs/
  review1_report        -- lives as a Claude Doc (problem, requirements, ER, schema)
```

## Schema (7 tables, 7 PKs, 7 FKs) — source of truth

Create tables in this order: PATIENT, DOCTOR, TEST_CATALOG, APPOINTMENT, SAMPLE, TEST_RESULT, BILL.

| Table | PK | FKs | Key constraints |
|---|---|---|---|
| PATIENT | patient_id NUMBER(6) | — | gender CHECK IN ('M','F','O'); phone NOT NULL UNIQUE, 10 digits; email UNIQUE; registered_on DEFAULT SYSDATE |
| DOCTOR | doctor_id NUMBER(4) | — | consultation_fee CHECK > 0; max_daily_appts DEFAULT 20 CHECK 1–50; status DEFAULT 'ACTIVE' CHECK IN ('ACTIVE','INACTIVE'); phone UNIQUE |
| TEST_CATALOG | test_code VARCHAR2(10) | — | test_name UNIQUE; price CHECK > 0; CHECK (normal_min <= normal_max); turnaround_hrs DEFAULT 24 |
| APPOINTMENT | appointment_id NUMBER(8) | patient_id → PATIENT, doctor_id → DOCTOR | slot_time 'HH:MI' via REGEXP_LIKE CHECK; status DEFAULT 'BOOKED' CHECK IN ('BOOKED','COMPLETED','CANCELLED','NO_SHOW'); booked_on DEFAULT SYSDATE |
| SAMPLE | sample_id NUMBER(8) | appointment_id → APPOINTMENT, test_code → TEST_CATALOG | UNIQUE (appointment_id, test_code); sample_type CHECK IN ('BLOOD','URINE','SALIVA','SWAB','OTHER'); status DEFAULT 'COLLECTED' CHECK IN ('COLLECTED','PROCESSING','COMPLETED','REJECTED') |
| TEST_RESULT | result_id NUMBER(8) | sample_id → SAMPLE (UNIQUE, ON DELETE CASCADE), verified_by → DOCTOR (ON DELETE SET NULL) | result_flag DEFAULT 'NORMAL' CHECK IN ('LOW','NORMAL','HIGH'), set by trigger |
| BILL | bill_id NUMBER(8) | appointment_id → APPOINTMENT (UNIQUE) | discount_pct DEFAULT 0 CHECK 0–50; CHECK (amount_paid <= total_amt); payment_status DEFAULT 'UNPAID' CHECK IN ('UNPAID','PARTIAL','PAID'); payment_mode CHECK IN ('CASH','CARD','UPI','INSURANCE') |

Full column list and data types are in the Review I report (section 6). If anything here and the report disagree,
fix both — they must stay in sync because the viva checks the report against the code.

Design decisions to preserve (they are justified in the viva):
- SAMPLE resolves the M:N between APPOINTMENT and TEST_CATALOG.
- Double booking is blocked by a trigger, NOT a UNIQUE constraint, so cancelled slots can be rebooked.
- BILL stores consultation_amt / test_amt / total_amt as a snapshot; do not "normalize" these away.
- Doctors are deactivated (status = 'INACTIVE'), not deleted.

## Naming and style conventions

- Tables and columns: UPPER_SNAKE for tables, lower_snake for columns, exactly as in the schema above.
- Constraints are always named: `pk_<table>`, `fk_<table>_<col>`, `uq_<table>_<col>`, `ck_<table>_<col>`.
- Sequences: `seq_<table>` (e.g. `seq_appointment`), START WITH a readable base (patients 100001, doctors 1001...).
- PL/SQL parameters prefixed `p_`, local variables `v_`, cursors `c_`.
- Business-rule errors use `RAISE_APPLICATION_ERROR` in the range -20001 to -20099, one code per rule,
  documented in a comment at the top of `06_triggers.sql` / `05_procedures.sql`.
- Every SQL file is re-runnable: start the session with `99_drop_all.sql`, end DML scripts with `COMMIT`.
- `SET SERVEROUTPUT ON` at the top of any script that uses `DBMS_OUTPUT`.

## PL/SQL components (minimums: 2 procedures, 2 functions, 1 cursor, 2 triggers)

| Component | Name | Behaviour |
|---|---|---|
| Function | `doctor_daily_load(p_doctor_id, p_date) RETURN NUMBER` | Count of non-CANCELLED appointments |
| Function | `patient_total_due(p_patient_id) RETURN NUMBER` | SUM(total_amt − amount_paid) over the patient's bills; 0 if none |
| Procedure | `book_appointment(p_patient_id, p_doctor_id, p_date, p_slot, p_reason, p_appt_id OUT)` | Rejects INACTIVE doctor (-20001) and full day via `doctor_daily_load` (-20002); inserts using `seq_appointment` |
| Procedure | `generate_bill(p_appointment_id, p_discount_pct DEFAULT 0)` | Requires status COMPLETED (-20010) and no existing bill (-20011); consultation fee from DOCTOR + SUM(price) of the visit's non-REJECTED samples |
| Procedure | `record_payment(p_bill_id, p_amount, p_mode)` | Rejects amount <= 0 or overpayment (-20020); updates amount_paid |
| Procedure + cursor | `end_of_day_billing(p_date)` | Explicit cursor over COMPLETED appointments on p_date with no BILL; calls `generate_bill` for each; prints count |
| Trigger | `trg_no_double_booking` BEFORE INSERT ON APPOINTMENT FOR EACH ROW | Rejects if the same doctor OR the same patient has a non-CANCELLED appointment at the same date + slot (-20003) |
| Trigger | `trg_flag_result` BEFORE INSERT OR UPDATE OF result_value ON TEST_RESULT FOR EACH ROW | Reads normal_min/max via SAMPLE → TEST_CATALOG, sets :NEW.result_flag; sets the SAMPLE row to COMPLETED |
| Trigger | `trg_payment_status` BEFORE UPDATE OF amount_paid ON BILL FOR EACH ROW | Sets :NEW.payment_status to UNPAID / PARTIAL / PAID |

Gotchas:
- **Mutating table:** a row-level trigger may not query its own table during UPDATE (ORA-04091). That is why
  `trg_no_double_booking` is BEFORE INSERT only; rescheduling = cancel + rebook. Do not add UPDATE to it unless
  converting to a compound trigger.
- Oracle CHECK constraints cannot use SYSDATE; date-relative rules (e.g. dob in the past) go in triggers or the app.
- `generate_bill` must not COMMIT inside the cursor loop of `end_of_day_billing`; commit once at the end.
  More generally, `book_appointment` / `generate_bill` / `record_payment` never commit — the caller owns the
  unit of work (T4 = UPDATE APPOINTMENT + generate_bill in one commit). Only `end_of_day_billing` commits.
- **Build order is not file-number order:** 99 → 01 → 04 → 05 → 06 → 02 → 03 (→ 07 for the demo). Triggers must
  exist before the seed so flags / sample status / payment status in the seed are set by triggers.
  `sql/00_build_all.sql` (SQL*Plus) and `app/setup_db.py` both follow this order.
- Seed inserts into APPOINTMENT must be single-row `INSERT ... VALUES` (a multi-row INSERT ... SELECT would hit
  ORA-04091 in `trg_no_double_booking`).

Error codes in use (besides the ones in the table above): -20004 booking in the past, -20005 doctor not found
(book_appointment); -20012 appointment not found (generate_bill); -20021 bill not found (record_payment);
-20030 result for a REJECTED sample, -20031 sample not found (trg_flag_result).

Extra CHECKs beyond the schema table: `ck_appointment_appt_date` (appt_date = TRUNC(appt_date)),
`ck_bill_total_amt` (total = ROUND((consultation_amt + test_amt) * (1 - discount_pct/100), 2)),
`ck_test_catalog_turnaround` (> 0), `ck_doctor_phone` (10 digits). NOT NULLs are named `nn_<table>_<col>`.
The report's section 6 must list these too.

## Transactions to demonstrate (Review III needs >= 5)

| # | Operation | Components exercised |
|---|---|---|
| T1 | Register patient + book appointment | INSERT PATIENT, `book_appointment`, `doctor_daily_load`, `trg_no_double_booking` |
| T2 | Order tests, collect samples | INSERT SAMPLE, UPDATE SAMPLE status |
| T3 | Enter test result | INSERT TEST_RESULT, `trg_flag_result` |
| T4 | Complete visit + bill | UPDATE APPOINTMENT, `generate_bill` |
| T5 | Payment + dues check | `record_payment`, `trg_payment_status`, `patient_total_due` |
| T6 | End-of-day billing | `end_of_day_billing` (cursor) |
| T7 | Cancel visit, delete rejected sample | UPDATE APPOINTMENT, DELETE SAMPLE (cascades to TEST_RESULT) |

For each, the app must print: the operation, tables touched, the SQL/PL/SQL component run, the rows affected,
and the result — this mirrors the "User Operation → SQL/PL/SQL → Database → Result" flow the evaluators ask about.

## Query set (>= 15, in `03_queries.sql`)

Cover: simple retrieval with filters, INNER and LEFT joins (3+ tables), GROUP BY + HAVING, aggregate functions,
correlated and non-correlated subqueries, EXISTS / NOT EXISTS, set operator (UNION/MINUS), ORDER BY with ranking
(`RANK()`/`DENSE_RANK()`), a view. Planned examples:
1. Today's schedule per doctor (join APPOINTMENT, PATIENT, DOCTOR)
2. Pending samples older than their test's turnaround time
3. All abnormal (LOW/HIGH) results with patient and test names
4. Revenue by day and by payment mode (GROUP BY)
5. Doctors with more than N appointments in a month (HAVING)
6. Patients with outstanding dues above the average due (subquery)
7. Tests never ordered (NOT EXISTS)
8. Most-ordered test per category (RANK)
9. Patients who visited more than one doctor
10. Completed appointments without a bill (LEFT JOIN … IS NULL)
11. Average result value per test vs normal range
12. Doctor-wise share of total revenue
13. Patients with both a HIGH and a LOW result (INTERSECT)
14. Monthly new-patient registrations
15. View `v_bill_summary` joining bill, patient, doctor
Each query gets a header comment: purpose, functional requirement (FR1–FR12), expected output shape.

## Seed data rules

- At least 10 rows per table, realistic Indian names, +91-style 10-digit phones, INR amounts.
- Data must make every query return non-empty, meaningful output — include some CANCELLED appointments,
  a REJECTED sample, LOW and HIGH results, UNPAID / PARTIAL / PAID bills, an INACTIVE doctor,
  and a test that is never ordered (for the NOT EXISTS query).
- Seed data must satisfy every trigger (insert in an order that never double-books).

## Python app

- Credentials only from environment variables; never hard-code passwords.
- Use bind variables (`:name`) for every query — no string concatenation of user input.
- Call procedures with `cursor.callproc`, functions with `cursor.callfunc`.
- Catch `oracledb.DatabaseError`, extract the ORA-200xx code and show the business-rule message cleanly.
- Show results as aligned tables (`tabulate` is fine).
- New error codes or constraints need an entry in `app/explain.py` so the UI can explain them.
- "Today" in the UI comes from the database (`services.db_today`), never `date.today()`: the Docker
  Oracle runs in UTC, so the two disagree between 00:00 and 05:30 IST.

## Review milestones

- **Review I (10 marks):** problem definition, requirements, ER diagram, relational schema, viva — DONE in the report doc.
- **Review II (10 marks):** DDL + constraints, DML + seed data, 15 queries, procedures/functions, cursor/triggers, viva.
- **Review III (10 marks):** integrated app, >= 5 transactions, SQL/PL/SQL interaction, reports, final report, viva.

## Working rules for Claude

- Keep everything explainable by students in a viva: clear comments, no clever one-liners, no features beyond scope.
- Out of scope: multi-branch, inventory, insurance claims, online portal, pharmacy. Don't add them.
- When changing the schema, update this file, `01_ddl.sql`, seed data, and flag that the report needs updating.
- After writing SQL, run it end-to-end against a clean schema (drop → DDL → seed → queries → PL/SQL → demos)
  and fix every error before calling the task done.
