"""Shared look-and-feel for the Streamlit front end.

Styling (CSS), the connection, and the small building blocks every page uses:
page headers, status pills, KPI tiles, list cards, the friendly error panel and
the "User Operation -> SQL/PL-SQL -> Database -> Result" trace.

Every piece of text that came from the database or the user is passed through
esc() before it goes into HTML.
"""

from html import escape
from pathlib import Path

import oracledb
import pandas as pd
import streamlit as st

import services as svc
from db import get_connection
from explain import explain

ASSETS = Path(__file__).resolve().parent / "assets"

# st.Page objects by key, filled in by streamlit_app.py, so pages can link to each other
PAGES = {}


def esc(value):
    return escape("" if value is None else str(value))


# ---------------------------------------------------------------------------
# Connection: one per browser session, re-opened if it dropped
# ---------------------------------------------------------------------------
def conn():
    if "conn" not in st.session_state:
        st.session_state.conn = get_connection()
    connection = st.session_state.conn
    try:
        connection.ping()
    except oracledb.Error:
        st.session_state.conn = get_connection()
    return st.session_state.conn


def today():
    """The database's current date (see services.db_today)."""
    return svc.db_today(conn())


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
CSS = """
<style>
:root {
  --mt-blue: #1F6FC5;
  --mt-blue-dark: #155AA6;
  --mt-blue-50: #F4F9FE;
  --mt-blue-100: #E8F2FC;
  --mt-blue-200: #CFE3F7;
  --mt-navy: #12395E;
  --mt-muted: #5A7590;
  --mt-border: #D6E6F5;
  --mt-green: #2EAD4B;
  --mt-green-bg: #EAF7EE;
  --mt-amber: #A86200;
  --mt-amber-bg: #FFF4E0;
  --mt-red: #C4323A;
  --mt-red-bg: #FDEEEF;
  --mt-gray: #5F6F80;
  --mt-gray-bg: #EEF2F6;
  --mt-shadow: 0 1px 2px rgba(18, 57, 94, .06), 0 4px 14px rgba(18, 57, 94, .06);
  --mt-shadow-hover: 0 2px 4px rgba(18, 57, 94, .08), 0 10px 24px rgba(31, 111, 197, .16);
}

/* page frame: centred, website-like width */
[data-testid="stMainBlockContainer"] { max-width: 1180px; padding-top: 4.2rem; padding-bottom: 4rem; }
[data-testid="stAppViewContainer"] { background: linear-gradient(180deg, #F4F9FE 0px, #FFFFFF 340px); }
[data-testid="stHeader"] { background: rgba(255, 255, 255, .92); backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--mt-border); }
h1, h2, h3, h4 { color: var(--mt-navy); letter-spacing: -0.01em; }

/* buttons: soft lift on hover, press-down on click */
[data-testid^="stBaseButton"] {
  font-weight: 600; transition: transform .16s ease, box-shadow .16s ease,
  background-color .16s ease, border-color .16s ease, color .16s ease;
}
[data-testid^="stBaseButton"]:hover { transform: translateY(-2px); box-shadow: var(--mt-shadow-hover); }
[data-testid^="stBaseButton"]:active { transform: translateY(0); box-shadow: none; }
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(180deg, #2B7DD3, var(--mt-blue)); border: 1px solid var(--mt-blue-dark);
}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: linear-gradient(180deg, #2A86E0, var(--mt-blue-dark)); border-color: var(--mt-blue-dark);
}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {
  background: #fff; border: 1px solid var(--mt-blue-200); color: var(--mt-blue);
}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-secondaryFormSubmit"]:hover {
  background: var(--mt-blue-50); border-color: var(--mt-blue); color: var(--mt-blue-dark);
}
[data-testid="stPageLink"] a {
  border: 1px solid var(--mt-blue-200); border-radius: 10px; padding: .45rem .9rem; background: #fff;
  transition: transform .16s ease, box-shadow .16s ease, background-color .16s ease;
}
[data-testid="stPageLink"] a:hover { transform: translateY(-2px); box-shadow: var(--mt-shadow-hover);
  background: var(--mt-blue-50); }
[data-testid="stPageLink"] a p { color: var(--mt-blue); font-weight: 600; }

/* forms and bordered containers read as cards */
[data-testid="stForm"] { background: #fff; border: 1px solid var(--mt-border); border-radius: 14px;
  box-shadow: var(--mt-shadow); padding: 1.3rem 1.4rem; }
.mt-hover-card, [class*="st-key-card_"] { transition: transform .18s ease, box-shadow .18s ease,
  border-color .18s ease; }
[class*="st-key-card_"] { background: #fff; border: 1px solid var(--mt-border) !important;
  border-radius: 16px; box-shadow: var(--mt-shadow); padding: 1.2rem 1.3rem; }
.mt-hover-card:hover, [class*="st-key-card_"]:hover { transform: translateY(-3px);
  box-shadow: var(--mt-shadow-hover); border-color: var(--mt-blue-200) !important; }

/* tabs */
[data-baseweb="tab-list"] { gap: .25rem; border-bottom: 1px solid var(--mt-border); }
[data-baseweb="tab"] { padding: .4rem .9rem; border-radius: 10px 10px 0 0; transition: background-color .15s; }
[data-baseweb="tab"]:hover { background: var(--mt-blue-50); }
[data-baseweb="tab"] p { font-weight: 600; }

/* expanders */
[data-testid="stExpander"] details { border-radius: 12px; border-color: var(--mt-border); background: #fff; }
[data-testid="stExpander"] summary:hover { background: var(--mt-blue-50); }

/* ---- custom HTML blocks ---- */
.mt-icon { font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal;
  font-size: 22px; line-height: 1; display: inline-block; -webkit-font-smoothing: antialiased;
  font-feature-settings: 'liga'; vertical-align: middle; }

.mt-head { display: flex; flex-direction: column; gap: .35rem; margin-bottom: .6rem; }
.mt-eyebrow { display: inline-flex; align-items: center; gap: .35rem; font-size: .78rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .06em; color: var(--mt-blue); }
.mt-head h1.mt-title { font-size: 2rem; font-weight: 700; color: var(--mt-navy); margin: 0; padding: .15rem 0;
  line-height: 1.2; }
.mt-sub { color: var(--mt-muted); font-size: 1rem; margin: 0; }
.mt-chips { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .25rem; }
.mt-chip { font-size: .74rem; font-weight: 600; color: var(--mt-navy); background: var(--mt-blue-100);
  border: 1px solid var(--mt-blue-200); border-radius: 999px; padding: .12rem .6rem; }
.mt-chip.tx { background: var(--mt-navy); border-color: var(--mt-navy); color: #fff; }
.mt-chip code, .mt-chip { font-family: inherit; }

.mt-pill { display: inline-block; font-size: .72rem; font-weight: 700; letter-spacing: .03em;
  border-radius: 999px; padding: .15rem .6rem; white-space: nowrap; }
.mt-pill.blue  { background: var(--mt-blue-100); color: var(--mt-blue-dark); }
.mt-pill.green { background: var(--mt-green-bg); color: #1D7A33; }
.mt-pill.amber { background: var(--mt-amber-bg); color: var(--mt-amber); }
.mt-pill.red   { background: var(--mt-red-bg); color: var(--mt-red); }
.mt-pill.gray  { background: var(--mt-gray-bg); color: var(--mt-gray); }

.mt-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: .9rem; margin: .4rem 0 1.2rem; }
.mt-kpi { background: #fff; border: 1px solid var(--mt-border); border-radius: 16px; padding: 1rem 1.1rem;
  box-shadow: var(--mt-shadow); }
.mt-kpi-top { display: flex; align-items: center; justify-content: space-between; color: var(--mt-muted);
  font-size: .85rem; font-weight: 600; }
.mt-kpi-icon { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center;
  background: var(--mt-blue-100); color: var(--mt-blue); }
.mt-kpi-icon.green { background: var(--mt-green-bg); color: var(--mt-green); }
.mt-kpi-icon.amber { background: var(--mt-amber-bg); color: var(--mt-amber); }
.mt-kpi-icon.red   { background: var(--mt-red-bg); color: var(--mt-red); }
.mt-kpi-value { font-size: 1.75rem; font-weight: 700; color: var(--mt-navy); margin-top: .35rem; }
.mt-kpi-note { font-size: .8rem; color: var(--mt-muted); }

.mt-section { display: flex; align-items: baseline; justify-content: space-between; margin: 1.4rem 0 .5rem; }
.mt-section-title { font-size: 1.15rem; font-weight: 700; color: var(--mt-navy); }
.mt-section span { color: var(--mt-muted); font-size: .85rem; }

.mt-list { display: flex; flex-direction: column; gap: .55rem; }
.mt-row { display: flex; align-items: center; gap: 1rem; background: #fff; border: 1px solid var(--mt-border);
  border-radius: 14px; padding: .8rem 1rem; }
.mt-row-date { min-width: 58px; text-align: center; border-radius: 10px; background: var(--mt-blue-50);
  border: 1px solid var(--mt-blue-200); padding: .3rem .2rem; line-height: 1.15; }
.mt-row-date b { display: block; font-size: 1.15rem; color: var(--mt-navy); }
.mt-row-date small { font-size: .7rem; font-weight: 700; color: var(--mt-blue); text-transform: uppercase; }
.mt-row-main { flex: 1; min-width: 0; }
.mt-row-title { font-weight: 600; color: var(--mt-navy); }
.mt-row-meta { font-size: .85rem; color: var(--mt-muted); }
.mt-row-right { text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: .25rem; }
.mt-row-amount { font-weight: 700; color: var(--mt-navy); }

.mt-range { position: relative; height: 6px; background: var(--mt-gray-bg); border-radius: 99px; margin-top: .45rem; }
.mt-range-ok { position: absolute; top: 0; bottom: 0; background: #BFE6C9; border-radius: 99px; }
.mt-range-dot { position: absolute; top: -4px; width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid #fff; box-shadow: 0 0 0 1px rgba(18,57,94,.25); transform: translateX(-50%); }

/* result + error panels */
.mt-alert { border-radius: 16px; padding: 1rem 1.2rem; margin: .8rem 0; border: 1px solid; }
.mt-alert.ok  { background: var(--mt-green-bg); border-color: #BFE6C9; }
.mt-alert.err { background: #FFF8F8; border-color: #F3C9CC; }
.mt-alert-top { display: flex; align-items: flex-start; gap: .7rem; }
.mt-alert-icon { width: 30px; height: 30px; flex: none; border-radius: 50%; display: grid; place-items: center;
  color: #fff; font-weight: 800; }
.mt-alert.ok .mt-alert-icon { background: var(--mt-green); }
.mt-alert.err .mt-alert-icon { background: var(--mt-red); }
.mt-alert-title { font-weight: 700; color: var(--mt-navy); font-size: 1.05rem; flex: 1; padding-top: .2rem; }
.mt-alert-detail { color: var(--mt-muted); font-size: .9rem; margin-top: .1rem; }
.mt-code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .75rem; font-weight: 700;
  background: #fff; border: 1px solid #F3C9CC; color: var(--mt-red); padding: .15rem .5rem; border-radius: 8px; }
.mt-explain { display: grid; grid-template-columns: 120px 1fr; gap: .45rem 1rem; margin: .9rem 0 .2rem 2.6rem;
  font-size: .92rem; color: var(--mt-navy); }
.mt-explain .k { color: var(--mt-muted); font-weight: 600; font-size: .82rem; text-transform: uppercase;
  letter-spacing: .04em; padding-top: .1rem; }
.mt-explain code { background: #fff; border: 1px solid var(--mt-border); color: var(--mt-blue-dark);
  padding: .05rem .4rem; border-radius: 6px; font-size: .82rem; }
.mt-alert-foot { margin: .7rem 0 0 2.6rem; font-size: .82rem; color: var(--mt-muted); }

.mt-trace { background: #fff; border: 1px solid var(--mt-border); border-radius: 16px; padding: 1rem 1.1rem;
  margin: .4rem 0 .6rem; }
.mt-trace-head { font-size: .78rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em;
  color: var(--mt-blue); margin-bottom: .7rem; }
.mt-steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: .6rem; }
.mt-step { position: relative; background: var(--mt-blue-50); border: 1px solid var(--mt-blue-200);
  border-radius: 12px; padding: .7rem .8rem; font-size: .86rem; color: var(--mt-navy); }
.mt-step:not(:last-child)::after { content: "→"; position: absolute; right: -.62rem; top: 50%;
  transform: translateY(-50%); color: var(--mt-blue); font-weight: 700; background: #fff; border-radius: 50%;
  width: 1.1rem; height: 1.1rem; display: grid; place-items: center; font-size: .8rem; z-index: 1; }
.mt-step-n { font-size: .72rem; font-weight: 700; color: var(--mt-blue); text-transform: uppercase;
  letter-spacing: .05em; margin-bottom: .3rem; }
.mt-step ul { margin: 0; padding-left: 1rem; }
.mt-step li { margin: 0; }

/* home page */
.mt-hero { display: grid; grid-template-columns: 1.4fr 1fr; gap: 2rem; align-items: center;
  background: linear-gradient(135deg, #E8F2FC 0%, #F7FBFF 60%, #FFFFFF 100%); border: 1px solid var(--mt-border);
  border-radius: 24px; padding: 2.4rem 2.6rem; margin-bottom: 1.6rem; }
.mt-hero h1 { font-size: 2.4rem; line-height: 1.15; margin: .5rem 0 .7rem; padding: 0; }
.mt-hero p { color: var(--mt-muted); font-size: 1.05rem; margin: 0; }
.mt-hero-art { display: grid; place-items: center; }
.mt-hero-art .ring svg { width: 112px; height: 112px; }
.mt-hero-art .ring { width: 190px; height: 190px; border-radius: 50%; display: grid; place-items: center;
  background: radial-gradient(circle, #FFFFFF 55%, #E8F2FC 56%, #E8F2FC 70%, #F4F9FE 71%);
  box-shadow: var(--mt-shadow); }
.mt-role-icon { width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center;
  background: var(--mt-blue-100); color: var(--mt-blue); margin-bottom: .7rem; }
.mt-role-icon .mt-icon { font-size: 26px; }
.mt-role-title { font-size: 1.15rem; font-weight: 700; color: var(--mt-navy); }
.mt-role-text { color: var(--mt-muted); font-size: .92rem; margin: .3rem 0 .6rem; min-height: 4.6em; }
.mt-role-list { font-size: .85rem; color: var(--mt-navy); margin: 0 0 .8rem; padding-left: 1.1rem; }
.mt-flow { display: grid; grid-template-columns: repeat(7, 1fr); gap: .5rem; }
.mt-flow-step { background: #fff; border: 1px solid var(--mt-border); border-radius: 14px; padding: .8rem .7rem;
  font-size: .82rem; color: var(--mt-navy); }
.mt-flow-step b { display: block; font-size: .9rem; margin: .35rem 0 .2rem; }
.mt-flow-step small { color: var(--mt-muted); }
.mt-footer { text-align: center; color: var(--mt-muted); font-size: .8rem; margin-top: 2.5rem; }

@media (max-width: 900px) {
  .mt-hero { grid-template-columns: 1fr; padding: 1.6rem; }
  .mt-hero-art { display: none; }
  .mt-steps { grid-template-columns: 1fr 1fr; }
  .mt-flow { grid-template-columns: repeat(2, 1fr); }
  .mt-explain { grid-template-columns: 1fr; margin-left: 0; }
}
</style>
"""


def inject_css():
    st.html(CSS)


# ---------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------
STATUS_TONE = {
    "BOOKED": "blue", "COMPLETED": "green", "CANCELLED": "gray", "NO_SHOW": "amber",
    "COLLECTED": "blue", "PROCESSING": "amber", "REJECTED": "red",
    "PAID": "green", "PARTIAL": "amber", "UNPAID": "red",
    "NORMAL": "green", "LOW": "amber", "HIGH": "red",
    "ACTIVE": "green", "INACTIVE": "gray",
}


def icon(name):
    """A Material Symbols icon (the font Streamlit already ships)."""
    return f'<span class="mt-icon">{esc(name)}</span>'


def pill(text, tone=None):
    tone = tone or STATUS_TONE.get(str(text), "gray")
    return f'<span class="mt-pill {tone}">{esc(str(text).replace("_", " "))}</span>'


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


def page_header(eyebrow, title, subtitle, tx=None, components=None):
    """Eyebrow + title + subtitle, then chips naming the transaction and DB objects it runs."""
    chips = ""
    if tx or components:
        chips = '<div class="mt-chips">'
        chips += "".join(f'<span class="mt-chip tx">{esc(t)}</span>' for t in (tx or []))
        chips += "".join(f'<span class="mt-chip">{esc(c)}</span>' for c in (components or []))
        chips += "</div>"
    html(f'<div class="mt-head"><span class="mt-eyebrow">{esc(eyebrow)}</span>'
         f'<h1 class="mt-title">{esc(title)}</h1><p class="mt-sub">{esc(subtitle)}</p>{chips}</div>')


def section(title, note=""):
    html(f'<div class="mt-section"><span class="mt-section-title">{esc(title)}</span><span>{esc(note)}</span></div>')


def kpis(items):
    """items: (icon name, label, value, note, tone)."""
    tiles = "".join(
        f'<div class="mt-kpi mt-hover-card"><div class="mt-kpi-top"><span>{esc(label)}</span>'
        f'<span class="mt-kpi-icon {tone}">{icon(ico)}</span></div>'
        f'<div class="mt-kpi-value">{esc(value)}</div><div class="mt-kpi-note">{esc(note)}</div></div>'
        for ico, label, value, note, tone in items)
    html(f'<div class="mt-kpis">{tiles}</div>')


def date_badge(iso_date):
    """'2026-10-25' -> a small calendar block: 25 / OCT."""
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    year, month, day = str(iso_date)[:10].split("-")
    return f'<div class="mt-row-date"><b>{int(day)}</b><small>{months[int(month) - 1]}</small></div>'


def row(left, title, meta, right=""):
    return (f'<div class="mt-row mt-hover-card">{left}<div class="mt-row-main">'
            f'<div class="mt-row-title">{title}</div><div class="mt-row-meta">{meta}</div></div>'
            f'<div class="mt-row-right">{right}</div></div>')


def rows_list(items, empty="Nothing to show yet."):
    if not items:
        html(f'<div class="mt-row"><div class="mt-row-meta">{esc(empty)}</div></div>')
    else:
        html(f'<div class="mt-list">{"".join(items)}</div>')


def range_bar(value, low, high, flag):
    """A track showing the normal range (green band) and where the value falls."""
    low, high, value = float(low), float(high), float(value)
    span = (high - low) or 1
    start, end = low - span * 0.6, high + span * 0.6
    pos = lambda x: max(0, min(100, (x - start) / (end - start) * 100))
    colour = {"NORMAL": "#2EAD4B", "LOW": "#D98A00", "HIGH": "#C4323A"}.get(flag, "#5F6F80")
    return (f'<div class="mt-range"><div class="mt-range-ok" style="left:{pos(low):.1f}%;'
            f'width:{pos(high) - pos(low):.1f}%"></div><div class="mt-range-dot" '
            f'style="left:{pos(value):.1f}%;background:{colour}"></div></div>')


def money(value):
    return f"₹{float(value or 0):,.2f}"


def frame(columns, rows):
    return pd.DataFrame(rows, columns=[c.lower() for c in columns])


def table(columns, rows, height="auto"):
    st.dataframe(frame(columns, rows), hide_index=True, width="stretch", height=height)


def options(columns, rows, label_fn):
    """Map 'label' -> id for a selectbox."""
    return {label_fn(dict(zip([c.lower() for c in columns], r))): r[0] for r in rows}


# ---------------------------------------------------------------------------
# "Signed in as" pickers for the patient and doctor portals
# ---------------------------------------------------------------------------
def _picker(kind, labels, default_id):
    """A selectbox whose choice survives page changes (kept in session_state[kind])."""
    ids = list(labels.values())
    st.session_state.setdefault(kind, default_id if default_id in ids else ids[0])
    if st.session_state[kind] not in ids:
        st.session_state[kind] = ids[0]
    widget_key = f"{kind}_picker"

    def remember():
        st.session_state[kind] = labels[st.session_state[widget_key]]
        clear_flashes()          # results belong to the previous person

    current = ids.index(st.session_state[kind])
    st.selectbox("Signed in as", list(labels), index=current, key=widget_key, on_change=remember)
    return st.session_state[kind]


def signed_in_patient():
    columns, rows = svc.list_patients(conn())
    labels = {f"{r[1]}  ·  #{r[0]}": r[0] for r in rows}
    return _picker("patient_id", labels, 100001)


def signed_in_doctor():
    columns, rows = svc.list_doctors(conn())
    labels = {f"{r[1]}  ·  {r[2]}" + ("  (inactive)" if r[5] == "INACTIVE" else ""): r[0] for r in rows}
    return _picker("doctor_id", labels, 1001)


# ---------------------------------------------------------------------------
# Outcome of a transaction: friendly result / error + the database trace
# ---------------------------------------------------------------------------
def error_panel(code, message, rolled_back=True):
    info = explain(code, message)
    code_html = f'<span class="mt-code">{esc(info["code_label"])}</span>' if info["code_label"] else ""
    lines = ""
    if info["why"]:
        lines += f'<span class="k">Why</span><span>{esc(info["why"])}</span>'
    if info["rule"]:
        lines += f'<span class="k">Enforced by</span><span><code>{esc(info["rule"])}</code></span>'
    if info["fix"]:
        lines += f'<span class="k">What to do</span><span>{esc(info["fix"])}</span>'
    detail = f'<div class="mt-alert-detail">Database said: {esc(info["detail"])}</div>' if info["detail"] else ""
    foot = ("Nothing was saved. The database rolled the whole transaction back."
            if rolled_back else "No rows were changed.")
    html(f'<div class="mt-alert err"><div class="mt-alert-top"><span class="mt-alert-icon">!</span>'
         f'<div style="flex:1"><div class="mt-alert-title">{esc(info["title"])}</div>{detail}</div>'
         f'{code_html}</div><div class="mt-explain">{lines}</div>'
         f'<div class="mt-alert-foot">{foot}</div></div>')


def success_panel(message):
    html(f'<div class="mt-alert ok"><div class="mt-alert-top"><span class="mt-alert-icon">✓</span>'
         f'<div class="mt-alert-title">{esc(message)}</div></div></div>')


def trace_panel(tx, with_statements=True):
    """The four-step flow evaluators ask about: operation → SQL/PL-SQL → tables → rows."""
    bullets = lambda items: "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"
    if tx.rows_affected:
        affected = bullets(f"{k}: {v}" for k, v in tx.rows_affected.items())
    else:
        affected = "none (rolled back)" if not tx.ok else "—"
    html(f'<div class="mt-trace"><div class="mt-trace-head">Behind the scenes · '
         f'User operation → SQL / PL-SQL → Database → Result</div><div class="mt-steps">'
         f'<div class="mt-step"><div class="mt-step-n">1 · User operation</div>{esc(tx.operation)}</div>'
         f'<div class="mt-step"><div class="mt-step-n">2 · SQL / PL-SQL run</div>{bullets(tx.components)}</div>'
         f'<div class="mt-step"><div class="mt-step-n">3 · Tables touched</div>{esc(", ".join(tx.tables))}</div>'
         f'<div class="mt-step"><div class="mt-step-n">4 · Rows affected</div>{affected}</div>'
         f'</div></div>')
    if not with_statements:      # caller is already inside an expander (they cannot nest)
        return
    with st.expander("Statements executed", icon=":material/code:"):
        st.code("\n\n".join(tx.statements) or "(failed before any statement completed)", language="sql")
        for line in tx.output:
            st.text(f"DBMS_OUTPUT: {line}")


def submit(slot, tx):
    """Log a finished transaction, keep it for display at `slot`, and redraw the page.

    Re-running the script after a transaction means every list on the page is
    re-queried, so what you see is always what is now in the database.
    """
    st.session_state.setdefault("log", []).insert(0, tx)
    st.session_state[f"flash_{slot}"] = tx
    st.rerun()


def flash(slot):
    """Show the last transaction submitted at `slot` (if any)."""
    tx = st.session_state.get(f"flash_{slot}")
    if tx:
        show_result(tx)


def clear_flashes():
    for key in [k for k in st.session_state if str(k).startswith("flash_")]:
        del st.session_state[key]


def show_result(tx):
    """Render a TxResult: friendly outcome, any result rows, then the database trace."""
    if tx.ok:
        success_panel(tx.result)
    else:
        error_panel(tx.error_code, tx.result, rolled_back=tx.error_code is not None)
    if tx.rows:
        table(tx.columns, tx.rows)
    trace_panel(tx)
