"""Administration: front office, lab and billing staff, plus the database view.

    Dashboard     - clinic at a glance (Q1, Q2, Q10 + counts)
    Lab desk      - T2b sample status, T3 enter result, T7b delete rejected sample
    Billing       - T5 payments, T6 end-of-day billing (cursor)
    Reports       - the 15 queries from sql/03_queries.sql
    Database      - schema, constraints, PL/SQL source, constraint lab, rebuild
    Activity log  - every transaction run in this browser session
"""


import pandas as pd
import streamlit as st

import services as svc
import ui
from db import BUILD_ORDER, run_script
from pages_patient import _dicts
from ui import esc, pill


def _header(title, subtitle, tx=None, components=None):
    ui.page_header("Administration", title, subtitle, tx, components)


def _queries():
    return {q["num"]: q for q in svc.load_queries()}


# ---------------------------------------------------------------------------
def dashboard():
    _header("Clinic dashboard", f"MediTrack Diagnostics · {ui.today():%A, %d %B %Y}")
    counts = svc.dashboard_counts(ui.conn())
    ui.kpis([
        ("groups", "Registered patients", counts["patients"], "PATIENT rows", "blue"),
        ("event", "Appointments today", counts["today_appts"], "not cancelled", "blue"),
        ("hourglass_top", "Samples in the lab", counts["pending_samples"], "collected or processing", "amber"),
        ("monitor_heart", "Abnormal results", counts["abnormal"], "flagged LOW / HIGH", "red"),
        ("account_balance_wallet", "Outstanding dues", f"₹{counts['outstanding']:,.0f}", "across all bills", "amber"),
    ])
    queries = _queries()

    left, right = st.columns([1.5, 1], gap="large")
    with left:
        ui.section("Today's schedule", "Q1 · APPOINTMENT ⋈ PATIENT ⋈ DOCTOR")
        ui.table(*svc.run_query(ui.conn(), queries[1]["sql"]))
        ui.section("Billed per day", "last 30 days")
        days, amounts = svc.billed_per_day(ui.conn())
        chart = pd.DataFrame(amounts, columns=["Day", "Billed (₹)"]).set_index("Day")
        st.bar_chart(chart, height=220, color="#1F6FC5")
    with right:
        overdue = _dicts(*svc.run_query(ui.conn(), queries[2]["sql"]))
        ui.section("Overdue samples", "Q2 · past turnaround time")
        ui.rows_list([ui.row(f'<div class="mt-kpi-icon amber">{ui.icon("hourglass_top")}</div>',
                             f"{esc(r['test_name'])} · {esc(r['patient'])}",
                             f"Sample #{r['sample_id']} · due {esc(r['due_by'])} · {r['hours_overdue']:g} h overdue",
                             pill(r["status"])) for r in overdue], "Nothing overdue.")
        unbilled = _dicts(*svc.run_query(ui.conn(), queries[10]["sql"]))
        ui.section("Completed but not billed", "Q10 · LEFT JOIN … IS NULL")
        ui.rows_list([ui.row(f'<div class="mt-kpi-icon red">{ui.icon("receipt_long")}</div>',
                             esc(r["patient"]), f"Visit #{r['appointment_id']} · {esc(r['appt_date'])} · {esc(r['doctor'])}",
                             pill("UNBILLED", "red")) for r in unbilled], "Every completed visit is billed.")
        st.write("")
        st.page_link(ui.PAGES["admin_billing"], label="Run end-of-day billing", icon=":material/nightlight:")
        st.page_link(ui.PAGES["admin_lab"], label="Open the lab desk", icon=":material/biotech:")


# ---------------------------------------------------------------------------
def lab_desk():
    _header("Lab desk", "Track samples, enter results, clear rejected samples.",
            ["T2b", "T3", "T7b"], ["UPDATE SAMPLE", "trg_flag_result", "ON DELETE CASCADE"])
    tab_result, tab_status, tab_delete = st.tabs(["Enter a result", "Update sample status", "Remove rejected sample"])
    open_samples = _dicts(*svc.list_samples(ui.conn(), statuses=["COLLECTED", "PROCESSING"]))
    label = lambda s: f"#{s['sample_id']} · {s['test_name']} · visit {s['appointment_id']} · {s['status']}"

    with tab_result:
        if not open_samples:
            ui.rows_list([], "No samples are waiting for a result.")
        else:
            by_label = {label(s): s for s in open_samples}
            sample = by_label[st.selectbox("Sample", list(by_label), key="result_sample")]
            test = next(t for t in _dicts(*svc.list_tests(ui.conn())) if t["test_code"] == sample["test_code"])
            ui.html(ui.row(f'<div class="mt-kpi-icon">{ui.icon("biotech")}</div>', esc(test["test_name"]),
                           f"Normal range {test['normal_min']:g} – {test['normal_max']:g} {esc(test['unit'])}. "
                           "You enter the value; the trigger decides LOW / NORMAL / HIGH.", pill("trigger sets flag", "blue")))
            doctors = {f"{d['full_name']}": d["doctor_id"] for d in _dicts(*svc.list_doctors(ui.conn(), active_only=True))}
            with st.form("result", border=False):
                c1, c2 = st.columns(2)
                value = c1.number_input(f"Result ({test['unit']})", value=float(test["normal_max"]), step=0.1, format="%.2f")
                names = list(doctors)
                verifier = c2.selectbox("Verified by", names,
                                        index=names.index("Dr. Sunita Rao") if "Dr. Sunita Rao" in names else 0)
                remarks = st.text_input("Remarks")
                submitted = st.form_submit_button("Save result", type="primary", icon=":material/save:")
            if submitted:
                ui.submit("result", svc.t3_enter_result(ui.conn(), sample["sample_id"], value,
                                                        doctors[verifier], remarks))
        ui.flash("result")

    with tab_status:
        if open_samples:
            by_label = {label(s): s for s in open_samples}
            with st.form("status", border=False):
                sample = by_label[st.selectbox("Sample", list(by_label), key="status_sample")]
                status = st.selectbox("New status", ["PROCESSING", "REJECTED", "COLLECTED"])
                remarks = st.text_input("Remarks", placeholder="e.g. Haemolysed, recollect")
                submitted = st.form_submit_button("Update status", type="primary", icon=":material/sync:")
            if submitted:
                ui.submit("status", svc.t2_update_sample_status(ui.conn(), sample["sample_id"], status, remarks))
        ui.flash("status")
        ui.section("Samples in the lab", f"{len(open_samples)} open")
        ui.rows_list([ui.row(f'<div class="mt-kpi-icon amber">{ui.icon("science")}</div>', esc(s["test_name"]),
                             f"Sample #{s['sample_id']} · visit {s['appointment_id']} · {esc(s['collected_on'])}",
                             pill(s["status"])) for s in open_samples], "No open samples.")

    with tab_delete:
        ui.flash("delete")
        rejected = _dicts(*svc.list_samples(ui.conn(), statuses=["REJECTED"]))
        if not rejected:
            ui.rows_list([], "No rejected samples. Reject one under 'Update sample status'.")
        for s in rejected:
            c1, c2 = st.columns([6, 1.2], vertical_alignment="center")
            result = (f"has a result ({s['result_value']:g}) that will be removed by CASCADE"
                      if s["result_value"] is not None else "no result attached")
            c1.markdown(ui.row(f'<div class="mt-kpi-icon red">{ui.icon("delete")}</div>', esc(s["test_name"]),
                               f"Sample #{s['sample_id']} · visit {s['appointment_id']} · {result}",
                               pill(s["status"])), unsafe_allow_html=True)
            if c2.button("Delete", key=f"del_{s['sample_id']}", icon=":material/delete:", width="stretch"):
                ui.submit("delete", svc.t7_delete_rejected_sample(ui.conn(), s["sample_id"]))


# ---------------------------------------------------------------------------
def billing():
    _header("Billing", "Take payments and close the day.",
            ["T5", "T6"], ["record_payment", "trg_payment_status", "end_of_day_billing (cursor)"])
    tab_pay, tab_eod, tab_all = st.tabs(["Record a payment", "End-of-day billing", "All bills"])

    with tab_pay:
        open_bills = _dicts(*svc.list_bills(ui.conn(), open_only=True))
        if not open_bills:
            ui.rows_list([], "Every bill is fully paid.")
        else:
            by_label = {f"#{b['bill_id']} · {b['patient']} · balance {ui.money(b['balance'])} · {b['payment_status']}": b
                        for b in open_bills}
            with st.form("admin_pay", border=False):
                bill = by_label[st.selectbox("Bill", list(by_label))]
                c1, c2 = st.columns(2)
                amount = c1.number_input("Amount (₹)", min_value=0.0, value=500.0, step=100.0)
                mode = c2.selectbox("Mode", ["UPI", "CASH", "CARD", "INSURANCE"])
                submitted = st.form_submit_button("Record payment", type="primary", icon=":material/payments:")
            if submitted:
                ui.submit("admin_pay", svc.t5_record_payment(ui.conn(), bill["bill_id"], amount, mode))
        ui.flash("admin_pay")

    with tab_eod:
        queries = _queries()
        ui.section("Completed visits without a bill", "these are what the cursor will pick up")
        ui.table(*svc.run_query(ui.conn(), queries[10]["sql"]))
        with st.form("eod", border=False):
            bill_date = st.date_input("Bill every completed visit on", value=ui.today())
            submitted = st.form_submit_button("Run end-of-day billing", type="primary", icon=":material/nightlight:")
        if submitted:
            ui.submit("eod", svc.t6_end_of_day_billing(ui.conn(), bill_date))
        ui.flash("eod")
        with st.expander("Procedure source (USER_SOURCE)", icon=":material/code:"):
            st.code(svc.plsql_source(ui.conn(), "END_OF_DAY_BILLING"), language="sql")

    with tab_all:
        ui.table(*svc.list_bills(ui.conn()))


# ---------------------------------------------------------------------------
def reports():
    _header("Reports", "The 15 queries, read live from sql/03_queries.sql (the file submitted for Review II).")
    queries = svc.load_queries()
    labels = {f"Q{q['num']}. {q['title']}": q for q in queries}
    q = labels[st.selectbox("Report", list(labels))]
    ui.html(f'<div class="mt-trace"><div class="mt-explain" style="margin:0;grid-template-columns:120px 1fr">'
            f'<span class="k">Purpose</span><span>{esc(q["purpose"])}</span>'
            f'<span class="k">SQL concept</span><span>{esc(q["concept"])}</span>'
            f'<span class="k">Requirement</span><span>{esc(q["fr"])}</span></div></div>')
    columns, rows = svc.run_query(ui.conn(), q["sql"])
    ui.section("Result", f"{len(rows)} row(s)")
    ui.table(columns, rows)
    with st.expander("SQL", expanded=True, icon=":material/code:"):
        st.code(q["full_sql"], language="sql")


# ---------------------------------------------------------------------------
def database():
    _header("Database", "Read from Oracle's data dictionary: USER_TAB_COLUMNS, USER_CONSTRAINTS, USER_SOURCE.")
    tab_tables, tab_constraints, tab_plsql, tab_lab, tab_admin = st.tabs(
        ["Tables", "Constraints", "PL/SQL objects", "Constraint lab", "Rebuild"])
    with tab_tables:
        c1, c2 = st.columns([1, 3], gap="large")
        with c1:
            ui.table(*svc.schema_row_counts(ui.conn()))
        with c2:
            name = st.selectbox("Table", ["PATIENT", "DOCTOR", "TEST_CATALOG", "APPOINTMENT",
                                          "SAMPLE", "TEST_RESULT", "BILL"])
            ui.table(*svc.schema_columns(ui.conn(), name))
            ui.table(*svc.schema_constraints(ui.conn(), name))
    with tab_constraints:
        ui.table(*svc.schema_constraints(ui.conn()), height=600)
    with tab_plsql:
        o_cols, o_rows = svc.schema_plsql(ui.conn())
        ui.table(o_cols, o_rows)
        names = [r[0] for r in o_rows if r[1] in ("PROCEDURE", "FUNCTION", "TRIGGER")]
        st.code(svc.plsql_source(ui.conn(), st.selectbox("Show source of", names)), language="sql")
    with tab_lab:
        st.markdown("Each card runs one statement that breaks a rule. The database refuses it and the "
                    "explanation says why. Every attempt is rolled back, so nothing changes.")
        for i, check in enumerate(svc.INTEGRITY_CHECKS):
            with st.container(key=f"card_lab{i}"):
                c1, c2 = st.columns([5, 1], vertical_alignment="center")
                c1.markdown(f"**{check['title']}**  \nenforced by `{check['rule']}`")
                clicked = c2.button("Try it", key=f"lab{i}", icon=":material/play_arrow:", width="stretch")
                st.code(check["sql"], language="sql")
                if clicked:
                    refused, code, message = svc.try_violation(ui.conn(), check["sql"])
                    if refused:
                        ui.error_panel(code, message)
                    else:
                        st.warning(message)
    with tab_admin:
        st.markdown("Drops everything and re-runs the build: DDL → functions → procedures → triggers → "
                    "seed → queries. Seed dates are relative to today, so rebuild on the day of the demo.")
        if st.button("Rebuild from sql/ files", type="primary", icon=":material/restart_alt:"):
            with st.spinner("Rebuilding..."):
                for filename in BUILD_ORDER:
                    run_script(ui.conn(), filename)
            st.session_state.log = []
            ui.clear_flashes()
            ui.success_panel("Fresh database loaded.")


# ---------------------------------------------------------------------------
def activity_log():
    _header("Activity log", "Every transaction run in this browser session, newest first.")
    log = st.session_state.get("log", [])
    if not log:
        ui.rows_list([], "Nothing run yet.")
    for tx in log:
        status = pill("SAVED", "green") if tx.ok else pill("REFUSED", "red")
        with st.expander(f"{'✓' if tx.ok else '✕'}  {tx.operation} — {tx.result}"):
            ui.html(status)
            if not tx.ok:
                ui.error_panel(tx.error_code, tx.result, rolled_back=tx.error_code is not None)
            ui.trace_panel(tx, with_statements=False)
            st.code("\n\n".join(tx.statements), language="sql")
