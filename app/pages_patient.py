"""Patient portal: what a patient sees.

    Home          - upcoming visits, latest results, amount due
    Register      - T1a  INSERT PATIENT
    Book a visit  - T1b  book_appointment, doctor_daily_load, trg_no_double_booking
    My visits     - T7a  cancel (UPDATE APPOINTMENT)
    My reports    - results flagged by trg_flag_result
    Bills         - T5   record_payment, trg_payment_status, patient_total_due
"""

import re
from datetime import date

import streamlit as st

import services as svc
import ui
from ui import esc, pill

SLOTS = [f"{h:02d}:{m:02d}" for h in range(8, 20) for m in (0, 30)]


def _header(title, subtitle, tx=None, components=None):
    """Page header on the left, 'Signed in as' on the right. Returns the patient id."""
    left, right = st.columns([3, 1.4], vertical_alignment="bottom")
    with left:
        ui.page_header("Patient portal", title, subtitle, tx, components)
    with right:
        return ui.signed_in_patient()


def _appointment_row(r, show_patient=False):
    who = r["patient"] if show_patient else f"{r['doctor']} · {r['specialization']}"
    meta = f"{esc(r['slot_time'])} · {esc(r['reason'] or 'General consultation')} · Visit #{r['appointment_id']}"
    return ui.row(ui.date_badge(r["appt_date"]), esc(who), meta, pill(r["status"]))


def _dicts(columns, rows):
    names = [c.lower() for c in columns]
    return [dict(zip(names, r)) for r in rows]


# ---------------------------------------------------------------------------
def home():
    patient_id = _header("Your health, in one place",
                         "Upcoming visits, lab reports and bills from MediTrack Diagnostics.")
    profile = svc.patient_profile(ui.conn(), patient_id)
    appts = _dicts(*svc.list_appointments(ui.conn(), patient_id=patient_id))
    results = _dicts(*svc.list_results(ui.conn(), patient_id=patient_id))
    today = ui.today().isoformat()
    upcoming = [a for a in appts if a["status"] == "BOOKED" and a["appt_date"] >= today]
    abnormal = [r for r in results if r["result_flag"] != "NORMAL"]

    ui.kpis([
        ("event", "Upcoming visits", len(upcoming), "booked from today on", "blue"),
        ("lab_research", "Lab reports", len(results), "results ready", "green"),
        ("monitor_heart", "Outside normal range", len(abnormal), "flagged LOW or HIGH", "amber" if abnormal else "green"),
        ("account_balance_wallet", "Amount due", ui.money(profile["total_due"]), "patient_total_due()",
         "red" if profile["total_due"] else "green"),
    ])

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        ui.section("Upcoming visits", "next appointments first")
        ui.rows_list([_appointment_row(a) for a in sorted(upcoming, key=lambda a: (a["appt_date"], a["slot_time"]))],
                     "No upcoming visits. Book one below.")
        ui.section("Latest lab reports")
        ui.rows_list([_result_row(r) for r in results[:3]], "No results yet.")
    with right:
        ui.section("Profile")
        gender = {"M": "Male", "F": "Female", "O": "Other"}[profile["gender"]]
        ui.html(f'<div class="mt-kpi"><div class="mt-row-title" style="font-size:1.1rem">'
                f'{esc(profile["first_name"])} {esc(profile["last_name"])}</div>'
                f'<div class="mt-row-meta">Patient #{profile["patient_id"]} · {gender}, {profile["age"]} yrs</div>'
                f'<div class="mt-explain" style="margin:.8rem 0 0;grid-template-columns:90px 1fr">'
                f'<span class="k">Phone</span><span>{esc(profile["phone"])}</span>'
                f'<span class="k">Email</span><span>{esc(profile["email"] or "—")}</span>'
                f'<span class="k">Born</span><span>{esc(profile["dob"])}</span>'
                f'<span class="k">Address</span><span>{esc(profile["address"] or "—")}</span>'
                f'<span class="k">Since</span><span>{esc(profile["registered_on"])}</span></div></div>')
        ui.section("Quick actions")
        st.page_link(ui.PAGES["patient_book"], label="Book a visit", icon=":material/add_circle:")
        st.page_link(ui.PAGES["patient_bills"], label="View and pay bills", icon=":material/payments:")
        st.page_link(ui.PAGES["patient_reports"], label="Open lab reports", icon=":material/lab_research:")


# ---------------------------------------------------------------------------
def register():
    left, _ = st.columns([3, 1.4])
    with left:
        ui.page_header("Patient portal", "Register as a new patient",
                       "One registration; every visit, report and bill is linked to it.",
                       ["T1a"], ["INSERT PATIENT", "seq_patient", "uq_patient_phone", "ck_patient_phone"])
    with st.form("register", border=False):
        c1, c2 = st.columns(2)
        first = c1.text_input("First name", placeholder="e.g. Ananya")
        last = c2.text_input("Last name", placeholder="e.g. Sharma")
        dob = c1.date_input("Date of birth", value=date(1995, 1, 1), min_value=date(1900, 1, 1),
                            max_value=ui.today())
        gender = c2.selectbox("Gender", ["M", "F", "O"],
                              format_func={"M": "Male", "F": "Female", "O": "Other"}.get)
        phone = c1.text_input("Mobile number", max_chars=10, placeholder="10 digits, e.g. 9876500000")
        email = c2.text_input("Email (optional)")
        address = st.text_input("Address (optional)")
        submitted = st.form_submit_button("Create my record", type="primary", icon=":material/person_add:")
    if submitted:
        tx = svc.t1_register_patient(ui.conn(), first, last, dob, gender, phone, email, address)
        if tx.ok:
            st.session_state.patient_id = int(re.search(r"\d+", tx.result).group())
        ui.submit("register", tx)
    ui.flash("register")
    if st.session_state.get("flash_register") and st.session_state.flash_register.ok:
        st.page_link(ui.PAGES["patient_book"], label="Now book your first visit",
                     icon=":material/arrow_forward:")


# ---------------------------------------------------------------------------
def book():
    patient_id = _header("Book a visit", "Choose a doctor, a day and a free slot.",
                         ["T1b"], ["book_appointment", "doctor_daily_load", "trg_no_double_booking"])
    d_cols, d_rows = svc.list_doctors(ui.conn())
    doctors = _dicts(d_cols, d_rows)
    specialities = ["All specialities"] + sorted({d["specialization"] for d in doctors})

    c1, c2 = st.columns(2)
    speciality = c1.selectbox("Speciality", specialities)
    shown = [d for d in doctors if speciality == specialities[0] or d["specialization"] == speciality]
    by_label = {f"{d['full_name']} · {d['specialization']}"
                + (" (not taking bookings)" if d["status"] == "INACTIVE" else ""): d for d in shown}
    doctor = by_label[c2.selectbox("Doctor", list(by_label))]
    c3, c4 = st.columns(2)
    appt_date = c3.date_input("Day", value=ui.today())

    taken = svc.taken_slots(ui.conn(), doctor["doctor_id"], patient_id, appt_date)
    slots = sorted(set(SLOTS) | set(taken))

    def slot_label(slot):
        if slot not in taken:
            return f"{slot}  ·  free"
        return f"{slot}  ·  taken (" + ("doctor busy" if taken[slot] == "doctor" else "you have a visit") + ")"

    free = [s for s in slots if s not in taken]
    slot = c4.selectbox("Time slot", slots, index=slots.index(free[0]) if free else 0, format_func=slot_label)
    reason = st.text_input("Reason for visit", placeholder="e.g. Fever and body ache")

    load = svc.doctor_load(ui.conn(), doctor["doctor_id"], appt_date)
    limit = doctor["max_daily_appts"]
    tone = "red" if load >= limit else "amber" if load >= limit * 0.75 else "green"
    status = pill(doctor["status"]) + " " + pill(f"{load} of {limit} booked", tone)
    ui.html(ui.row(f'<div class="mt-kpi-icon">{ui.icon("stethoscope")}</div>', esc(doctor["full_name"]),
                   f"{esc(doctor['specialization'])} · consultation fee {ui.money(doctor['consultation_fee'])} "
                   f"· {appt_date:%d %b %Y}", status))
    st.write("")
    if st.button("Confirm booking", type="primary", icon=":material/event_available:"):
        ui.submit("book", svc.t1_book_appointment(ui.conn(), patient_id, doctor["doctor_id"],
                                                  appt_date, slot, reason))
    ui.flash("book")

    with st.expander("Try the rules (for the demo)", icon=":material/science:"):
        st.markdown(
            "- **Dr. Ramesh Patel** is inactive → *-20001, doctor not taking bookings*\n"
            "- **Dr. Sanjay Gupta** today is full (2 of 2) → *-20002, day fully booked*\n"
            "- **Dr. Rajesh Kumar** today, pick the slot marked *taken* → *-20003, trigger blocks the double booking*\n"
            "- Any doctor, a **past date** → *-20004, cannot book in the past*")


# ---------------------------------------------------------------------------
def visits():
    patient_id = _header("My visits", "Cancel a booking you can no longer make; the slot is released at once.",
                         ["T7a"], ["UPDATE APPOINTMENT", "status = 'CANCELLED'"])
    ui.flash("visits")
    appts = _dicts(*svc.list_appointments(ui.conn(), patient_id=patient_id))
    today = ui.today().isoformat()
    upcoming = sorted([a for a in appts if a["appt_date"] >= today and a["status"] == "BOOKED"],
                      key=lambda a: (a["appt_date"], a["slot_time"]))
    past = [a for a in appts if a not in upcoming]

    ui.section("Upcoming", f"{len(upcoming)} booked")
    if not upcoming:
        ui.rows_list([], "No upcoming visits.")
    for a in upcoming:
        c1, c2 = st.columns([6, 1.1], vertical_alignment="center")
        c1.markdown(_appointment_row(a), unsafe_allow_html=True)
        if c2.button("Cancel", key=f"cancel_{a['appointment_id']}", icon=":material/event_busy:", width="stretch"):
            ui.submit("visits", svc.t7_cancel_appointment(ui.conn(), a["appointment_id"]))

    ui.section("History", f"{len(past)} visits")
    ui.rows_list([_appointment_row(a) for a in past], "No past visits.")


# ---------------------------------------------------------------------------
def _result_row(r):
    low, high = r["normal_min"], r["normal_max"]
    meta = (f"Normal {low:g}–{high:g} {esc(r['unit'])} · {esc(r['result_date'])} · ordered by {esc(r['doctor'])}"
            + ui.range_bar(r["result_value"], low, high, r["result_flag"]))
    value = f'<span class="mt-row-amount">{r["result_value"]:g} {esc(r["unit"])}</span>'
    return ui.row(f'<div class="mt-kpi-icon {ui.STATUS_TONE[r["result_flag"]]}">{ui.icon("biotech")}</div>',
                  esc(r["test_name"]), meta, value + pill(r["result_flag"]))


def reports():
    patient_id = _header("My lab reports", "The flag is set by the database, not typed by a person.",
                         None, ["trg_flag_result", "TEST_CATALOG.normal_min / normal_max"])
    results = _dicts(*svc.list_results(ui.conn(), patient_id=patient_id))
    waiting = _dicts(*svc.list_samples(ui.conn(), patient_id=patient_id, statuses=["COLLECTED", "PROCESSING"]))
    if waiting:
        ui.section("Awaiting results", f"{len(waiting)} sample(s) in the lab")
        ui.rows_list([ui.row(f'<div class="mt-kpi-icon amber">{ui.icon("hourglass_top")}</div>',
                             esc(s["test_name"]), f"Sample #{s['sample_id']} · collected {esc(s['collected_on'])}",
                             pill(s["status"])) for s in waiting])
    ui.section("Results", "green band = normal range")
    ui.rows_list([_result_row(r) for r in results], "No results yet.")


# ---------------------------------------------------------------------------
def bills():
    patient_id = _header("Bills and payments", "Pay all or part of a bill. The status updates itself.",
                         ["T5"], ["record_payment", "trg_payment_status", "patient_total_due"])
    profile = svc.patient_profile(ui.conn(), patient_id)
    all_bills = _dicts(*svc.list_bills(ui.conn(), patient_id=patient_id))
    open_bills = [b for b in all_bills if b["payment_status"] != "PAID"]
    ui.kpis([
        ("account_balance_wallet", "Total due", ui.money(profile["total_due"]), "patient_total_due()",
         "red" if profile["total_due"] else "green"),
        ("receipt_long", "Open bills", len(open_bills), "UNPAID or PARTIAL", "amber" if open_bills else "green"),
        ("task_alt", "Paid bills", len(all_bills) - len(open_bills), "settled in full", "green"),
    ])

    if open_bills:
        labels = {f"Bill #{b['bill_id']} · {b['doctor']} · balance {ui.money(b['balance'])}": b for b in open_bills}
        with st.form("pay", border=False):
            ui.section("Make a payment")
            bill = labels[st.selectbox("Bill", list(labels))]
            c1, c2 = st.columns(2)
            amount = c1.number_input("Amount (₹)", min_value=0.0, value=float(min(500, bill["balance"])), step=100.0,
                                     help="Try more than the balance to see the overpayment rule")
            mode = c2.selectbox("Pay with", ["UPI", "CARD", "CASH", "INSURANCE"])
            submitted = st.form_submit_button("Pay now", type="primary", icon=":material/payments:")
        if submitted:
            ui.submit("pay", svc.t5_record_payment(ui.conn(), bill["bill_id"], amount, mode))
    ui.flash("pay")

    ui.section("All bills")
    items = []
    for b in all_bills:
        meta = (f"{esc(b['bill_date'])} · {esc(b['doctor'])} · consultation {ui.money(b['consultation_amt'])}"
                f" + tests {ui.money(b['test_amt'])}" + (f" − {b['discount_pct']:g}%" if b["discount_pct"] else "")
                + f" · paid {ui.money(b['amount_paid'])}")
        right = f'<span class="mt-row-amount">{ui.money(b["total_amt"])}</span>' + pill(b["payment_status"])
        items.append(ui.row(f'<div class="mt-kpi-icon">{ui.icon("receipt_long")}</div>',
                            f"Bill #{b['bill_id']}", meta, right))
    ui.rows_list(items, "No bills yet.")
