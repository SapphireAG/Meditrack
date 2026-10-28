"""MediTrack Streamlit front end.

    streamlit run app/streamlit_app.py

A small clinic website with three portals over the same service layer as the
CLI (services.py):

    Patient         register, book, visits, lab reports, bills      (T1, T5, T7a)
    Doctor          day view, order tests, complete visit, results  (T2a, T4)
    Administration  dashboard, lab desk, billing, reports, database (T2b, T3, T5, T6, T7b)

Every transaction shows a plain-language outcome (errors explained by
explain.py) and the "User Operation -> SQL/PL-SQL -> Database -> Result" trace.
"""

import streamlit as st

import pages_admin as admin
import pages_doctor as doctor
import pages_patient as patient
import ui
from ui import ASSETS

st.set_page_config(page_title="MediTrack Diagnostics", page_icon=str(ASSETS / "icon.png"), layout="wide")
ui.inject_css()
st.logo(str(ASSETS / "logo_wordmark.svg"), size="large")

LOGO_MARK = (ASSETS / "logo_mark.svg").read_text()

ROLES = [
    ("patient_home", "personal_injury", "Patient",
     "Book a visit with a doctor, see your lab reports the moment they are ready, and pay bills online.",
     ["Register and book (T1)", "Cancel a visit (T7)", "Reports and bills (T5)"]),
    ("doctor_day", "stethoscope", "Doctor",
     "See the day's patients, order lab tests, review abnormal results and close visits.",
     ["Order tests (T2)", "Complete visit and bill (T4)", "Results to review"]),
    ("admin_dashboard", "admin_panel_settings", "Administration",
     "Run the front office, the lab and billing, and look inside the database itself.",
     ["Lab desk (T2, T3, T7)", "Billing and end of day (T5, T6)", "Reports and constraint lab"]),
]

JOURNEY = [
    ("T1", "Register and book", "Patient", "book_appointment"),
    ("T2", "Order tests", "Doctor, Lab", "INSERT SAMPLE"),
    ("T3", "Enter result", "Lab", "trg_flag_result"),
    ("T4", "Complete and bill", "Doctor", "generate_bill"),
    ("T5", "Pay", "Patient, Billing", "record_payment"),
    ("T6", "Close the day", "Billing", "cursor c_unbilled"),
    ("T7", "Cancel / clean up", "Patient, Lab", "ON DELETE CASCADE"),
]


def home():
    ui.html(f'<div class="mt-hero"><div><span class="mt-eyebrow">{ui.icon("verified")} Diagnostic clinic</span>'
            f'<h1>Care, tests and billing in one connected record.</h1>'
            f'<p>MediTrack follows every visit from booking to lab report to payment. Pick a portal to see '
            f'the clinic from the patient\'s, the doctor\'s or the administrator\'s side.</p></div>'
            f'<div class="mt-hero-art"><div class="ring">{LOGO_MARK}</div></div></div>')

    columns = st.columns(3, gap="medium")
    for column, (page_key, ico, title, text, points) in zip(columns, ROLES):
        with column, st.container(key=f"card_role_{page_key}"):
            items = "".join(f"<li>{ui.esc(p)}</li>" for p in points)
            ui.html(f'<div class="mt-role-icon">{ui.icon(ico)}</div><div class="mt-role-title">{title}</div>'
                    f'<div class="mt-role-text">{ui.esc(text)}</div><ul class="mt-role-list">{items}</ul>')
            st.page_link(ui.PAGES[page_key], label=f"Open {title.lower()} portal", icon=":material/arrow_forward:")

    ui.section("A visit, end to end", "each step is one database transaction")
    steps = "".join(f'<div class="mt-flow-step mt-hover-card"><span class="mt-chip tx">{t}</span><b>{ui.esc(name)}</b>'
                    f'<small>{ui.esc(who)}<br><code>{ui.esc(component)}</code></small></div>'
                    for t, name, who, component in JOURNEY)
    ui.html(f'<div class="mt-flow">{steps}</div>')
    ui.html('<div class="mt-footer">MediTrack · BCSE302L Database Systems · Oracle SQL + PL/SQL · '
            '7 tables in 3NF/BCNF · 4 procedures · 2 functions · 1 cursor · 3 triggers</div>')


def connection_help(exc):
    ui.html(f'<div class="mt-alert err"><div class="mt-alert-top"><span class="mt-alert-icon">!</span>'
            f'<div style="flex:1"><div class="mt-alert-title">Cannot reach the Oracle database</div>'
            f'<div class="mt-alert-detail">{ui.esc(exc)}</div></div></div>'
            f'<div class="mt-explain"><span class="k">Why</span><span>The app needs a running Oracle '
            f'instance and the ORACLE_USER / ORACLE_PASSWORD / ORACLE_DSN variables.</span>'
            f'<span class="k">What to do</span><span>Start the database (see README → Quick start), '
            f'check app/.env, then reload this page.</span></div></div>')


# (section, key, page function, title, icon, url) - key is how pages link to each other (ui.PAGES)
SITE_MAP = [
    ("", "home", home, "Home", "home", "home"),
    ("Patient", "patient_home", patient.home, "My health", "favorite", "patient"),
    ("Patient", "patient_book", patient.book, "Book a visit", "calendar_add_on", "patient-book"),
    ("Patient", "patient_visits", patient.visits, "My visits", "event_note", "patient-visits"),
    ("Patient", "patient_reports", patient.reports, "Lab reports", "lab_research", "patient-reports"),
    ("Patient", "patient_bills", patient.bills, "Bills", "payments", "patient-bills"),
    ("Patient", "patient_register", patient.register, "New patient", "person_add", "patient-register"),
    ("Doctor", "doctor_day", doctor.my_day, "My day", "today", "doctor"),
    ("Doctor", "doctor_order", doctor.order_tests, "Order tests", "biotech", "doctor-order"),
    ("Doctor", "doctor_complete", doctor.complete_visit, "Complete visit", "task_alt", "doctor-complete"),
    ("Doctor", "doctor_results", doctor.results, "Patient results", "monitor_heart", "doctor-results"),
    ("Administration", "admin_dashboard", admin.dashboard, "Dashboard", "dashboard", "admin"),
    ("Administration", "admin_lab", admin.lab_desk, "Lab desk", "science", "admin-lab"),
    ("Administration", "admin_billing", admin.billing, "Billing", "receipt_long", "admin-billing"),
    ("Administration", "admin_reports", admin.reports, "Reports", "query_stats", "admin-reports"),
    ("Administration", "admin_database", admin.database, "Database", "database", "admin-database"),
    ("Administration", "admin_log", admin.activity_log, "Activity log", "history", "admin-log"),
]


def build_pages():
    """The site map grouped by portal; also fills ui.PAGES for cross-page links."""
    pages = {}
    for section, key, function, title, icon, url in SITE_MAP:
        page = st.Page(function, title=title, icon=f":material/{icon}:", url_path=url, default=(key == "home"))
        ui.PAGES[key] = page
        pages.setdefault(section, []).append(page)
    return pages


def main():
    current = st.navigation(build_pages(), position="top")
    try:
        ui.conn()
    except Exception as exc:  # show setup help instead of a stack trace
        connection_help(exc)
        st.stop()
    current.run()


if __name__ == "__main__":      # streamlit runs this file as __main__
    main()
