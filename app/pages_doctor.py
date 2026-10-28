"""Doctor portal: what a doctor sees.

    My day          - schedule + doctor_daily_load
    Order tests     - T2a  INSERT SAMPLE (uq_sample_appt_test)
    Complete visit  - T4   UPDATE APPOINTMENT + generate_bill, one unit of work
    Patient results - results of this doctor's patients, flagged by trg_flag_result
"""


import streamlit as st

import services as svc
import ui
from pages_patient import _dicts, _result_row
from ui import esc, pill


def _header(title, subtitle, tx=None, components=None):
    left, right = st.columns([3, 1.4], vertical_alignment="bottom")
    with left:
        ui.page_header("Doctor portal", title, subtitle, tx, components)
    with right:
        return ui.signed_in_doctor()


def _visit_label(a):
    return f"#{a['appointment_id']} · {a['appt_date']} {a['slot_time']} · {a['patient']} · {a['status']}"


# ---------------------------------------------------------------------------
def my_day():
    doctor_id = _header("My day", "Today's patients, open lab work and results that need a look.",
                        None, ["doctor_daily_load", "Q1 today's schedule"])
    doctor = next(d for d in _dicts(*svc.list_doctors(ui.conn())) if d["doctor_id"] == doctor_id)
    on_date = st.date_input("Schedule for", value=ui.today(), width=220)
    schedule = sorted(_dicts(*svc.list_appointments(ui.conn(), doctor_id=doctor_id, on_date=on_date)),
                      key=lambda a: a["slot_time"])
    pending = _dicts(*svc.list_samples(ui.conn(), doctor_id=doctor_id, statuses=["COLLECTED", "PROCESSING"]))
    abnormal = _dicts(*svc.list_results(ui.conn(), doctor_id=doctor_id, abnormal_only=True))
    load = svc.doctor_load(ui.conn(), doctor_id, on_date)
    limit = doctor["max_daily_appts"]

    ui.kpis([
        ("event", "Booked that day", f"{load} / {limit}", "doctor_daily_load() vs limit",
         "red" if load >= limit else "blue"),
        ("task_alt", "Completed", sum(a["status"] == "COMPLETED" for a in schedule), "visits closed", "green"),
        ("hourglass_top", "Samples in the lab", len(pending), "collected or processing", "amber" if pending else "green"),
        ("monitor_heart", "Abnormal results", len(abnormal), "your patients, LOW or HIGH", "red" if abnormal else "green"),
    ])
    if doctor["status"] == "INACTIVE":
        ui.html(f'<div class="mt-alert err"><div class="mt-alert-title">This doctor is INACTIVE</div>'
                f'<div class="mt-alert-detail">Kept for history; no new bookings are accepted.</div></div>')

    left, right = st.columns([1.5, 1], gap="large")
    with left:
        ui.section(f"Schedule · {on_date:%a %d %b}", f"{len(schedule)} appointment(s)")
        ui.rows_list([ui.row(f'<div class="mt-row-date"><b style="font-size:.95rem">{esc(a["slot_time"])}</b>'
                             f'<small>slot</small></div>', esc(a["patient"]),
                             f"{esc(a['reason'] or 'General consultation')} · Visit #{a['appointment_id']}",
                             pill(a["status"])) for a in schedule], "No appointments that day.")
    with right:
        ui.section("Needs your attention")
        ui.rows_list([ui.row(f'<div class="mt-kpi-icon red">{ui.icon("priority_high")}</div>',
                             f"{esc(r['patient'])} · {esc(r['test_name'])}",
                             f"{r['result_value']:g} {esc(r['unit'])} (normal {r['normal_min']:g}–{r['normal_max']:g})",
                             pill(r["result_flag"])) for r in abnormal[:6]], "No abnormal results.")
        st.write("")
        st.page_link(ui.PAGES["doctor_order"], label="Order tests", icon=":material/biotech:")
        st.page_link(ui.PAGES["doctor_complete"], label="Complete a visit", icon=":material/task_alt:")


# ---------------------------------------------------------------------------
def order_tests():
    doctor_id = _header("Order tests", "Pick a visit and the tests; the lab collects a sample for each.",
                        ["T2a"], ["INSERT SAMPLE", "seq_sample", "uq_sample_appt_test"])
    visits = _dicts(*svc.list_appointments(ui.conn(), ["BOOKED", "COMPLETED"], doctor_id=doctor_id))
    visits = [v for v in visits if not v["billed"]]
    if not visits:
        ui.rows_list([], "No open visits for this doctor.")
        return
    t_cols, t_rows = svc.list_tests(ui.conn())
    tests = {f"{r[1]} ({r[0]}) · {r[2]} · ₹{r[3]:,.0f}": r[0] for r in t_rows}
    by_label = {_visit_label(v): v for v in visits}

    with st.form("order", border=False):
        visit = by_label[st.selectbox("Visit", list(by_label))]
        chosen = st.multiselect("Tests to order", list(tests), placeholder="Choose one or more tests")
        c1, c2 = st.columns(2)
        sample_type = c1.selectbox("Sample type", ["BLOOD", "URINE", "SALIVA", "SWAB", "OTHER"])
        collected_by = c2.text_input("Collected by", value="Lakshmi (Lab technician)")
        submitted = st.form_submit_button("Send to lab", type="primary", icon=":material/send:")
    if submitted:
        if not chosen:
            st.warning("Choose at least one test.", icon=":material/info:")
        else:
            ui.submit("order", svc.t2_order_tests(ui.conn(), visit["appointment_id"],
                                                  [(tests[t], sample_type) for t in chosen], collected_by))
    ui.flash("order")
    ui.section("Already ordered for this visit", "ordering one of these again is refused (composite UNIQUE)")
    ordered = _dicts(*svc.list_samples(ui.conn(), appointment_id=visit["appointment_id"]))
    ui.rows_list([ui.row(f'<div class="mt-kpi-icon">{ui.icon("biotech")}</div>', esc(s["test_name"]),
                         f"Sample #{s['sample_id']} · {esc(s['sample_type'])} · {esc(s['collected_on'])}",
                         pill(s["status"])) for s in ordered], "No tests ordered yet.")


# ---------------------------------------------------------------------------
def complete_visit():
    doctor_id = _header("Complete a visit", "Closing the visit raises the bill in the same transaction.",
                        ["T4"], ["UPDATE APPOINTMENT", "generate_bill", "ck_bill_total_amt", "one COMMIT"])
    today = ui.today().isoformat()
    visits = _dicts(*svc.list_appointments(ui.conn(), ["BOOKED", "COMPLETED"], doctor_id=doctor_id))
    # unbilled visits dated today or earlier (a future visit cannot be completed yet)
    visits = [v for v in visits if not v["billed"] and v["appt_date"] <= today]
    if not visits:
        ui.flash("complete")
        ui.rows_list([], "Nothing to close: every past visit of this doctor is billed.")
        return
    by_label = {_visit_label(v): v for v in visits}
    visit = by_label[st.selectbox("Visit", list(by_label))]
    doctor = next(d for d in _dicts(*svc.list_doctors(ui.conn())) if d["doctor_id"] == doctor_id)
    samples = _dicts(*svc.list_samples(ui.conn(), appointment_id=visit["appointment_id"]))
    prices = {r[0]: r[3] for r in svc.list_tests(ui.conn())[1]}

    ui.section("Bill preview", "what generate_bill will charge")
    items = [ui.row(f'<div class="mt-kpi-icon">{ui.icon("stethoscope")}</div>', "Consultation",
                    esc(doctor["full_name"]), f'<span class="mt-row-amount">{ui.money(doctor["consultation_fee"])}</span>')]
    for s in samples:
        rejected = s["status"] == "REJECTED"
        amount = "not charged" if rejected else ui.money(prices[s["test_code"]])
        items.append(ui.row(f'<div class="mt-kpi-icon {"red" if rejected else "green"}">{ui.icon("biotech")}</div>',
                            esc(s["test_name"]), f"Sample #{s['sample_id']}",
                            f'<span class="mt-row-amount">{amount}</span>' + pill(s["status"])))
    ui.rows_list(items)
    st.write("")
    with st.expander("Billing desk options", icon=":material/percent:"):
        discount = st.slider("Discount %", 0, 60, 0, help="ck_bill_discount_pct allows 0–50; try 60 to see it refused")
    if st.button("Complete visit and raise bill", type="primary", icon=":material/task_alt:"):
        ui.submit("complete", svc.t4_complete_and_bill(ui.conn(), visit["appointment_id"], discount))
    ui.flash("complete")


# ---------------------------------------------------------------------------
def results():
    doctor_id = _header("Patient results", "Results for your patients. LOW / HIGH is decided by the trigger.",
                        None, ["trg_flag_result", "Q3 abnormal results"])
    only_abnormal = st.toggle("Only LOW / HIGH", value=False)
    rows = _dicts(*svc.list_results(ui.conn(), doctor_id=doctor_id, abnormal_only=only_abnormal))
    items = []
    for r in rows:
        line = _result_row(r)
        items.append(line.replace(f"ordered by {esc(r['doctor'])}", f"patient {esc(r['patient'])}"))
    ui.rows_list(items, "No results for this doctor's patients.")
