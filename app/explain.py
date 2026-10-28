"""Plain-language explanations for the errors the database raises.

The database answers with a code (ORA-20003, ORA-02290, ...). That is exact but
robotic. explain() turns a code + message into four things a person can act on:

    title  - what went wrong, in one short line
    why    - the business reason the rule exists
    rule   - which database object enforced it (trigger / procedure / constraint)
    fix    - what to do next

Used by both front ends (streamlit_app.py and main.py).
"""

import re

# ---------------------------------------------------------------------------
# Our own business rules: RAISE_APPLICATION_ERROR(-20001 .. -20099)
# ---------------------------------------------------------------------------
BUSINESS_RULES = {
    20001: {
        "title": "This doctor is not taking appointments",
        "why": "The doctor's status is INACTIVE. Doctors who leave the clinic are deactivated, never "
               "deleted, so their past visits and bills stay intact, but no new visit can be booked.",
        "rule": "book_appointment procedure (checks DOCTOR.status)",
        "fix": "Choose an active doctor.",
    },
    20002: {
        "title": "The doctor's day is fully booked",
        "why": "Every doctor has a daily limit (DOCTOR.max_daily_appts). The function doctor_daily_load "
               "counted the non-cancelled appointments on that date and the limit is already reached.",
        "rule": "book_appointment procedure → doctor_daily_load function",
        "fix": "Pick another date, or another doctor with the same specialisation.",
    },
    20003: {
        "title": "That time slot is already taken",
        "why": "A doctor cannot see two patients at once, and a patient cannot be in two rooms at once. "
               "The doctor or the patient already has a non-cancelled appointment at this date and time.",
        "rule": "trg_no_double_booking (BEFORE INSERT trigger on APPOINTMENT)",
        "fix": "Choose another slot, or cancel the existing appointment first. Cancelled slots can be "
               "booked again; that is why this rule is a trigger, not a UNIQUE constraint.",
    },
    20004: {
        "title": "That date is in the past",
        "why": "Appointments can only be booked for today or later. Oracle CHECK constraints cannot "
               "use SYSDATE, so this date rule lives inside the procedure.",
        "rule": "book_appointment procedure",
        "fix": "Choose today or a future date.",
    },
    20005: {
        "title": "That doctor does not exist",
        "why": "The doctor id was not found in the DOCTOR table.",
        "rule": "book_appointment procedure",
        "fix": "Pick a doctor from the list.",
    },
    20010: {
        "title": "The visit has not been completed yet",
        "why": "A bill is raised only after the visit is COMPLETED. Billing a booked, cancelled or "
               "no-show visit would charge the patient for care that was never given.",
        "rule": "generate_bill procedure (checks APPOINTMENT.status)",
        "fix": "Mark the visit as completed first (Doctor → Complete visit).",
    },
    20011: {
        "title": "This visit already has a bill",
        "why": "Each appointment gets exactly one bill, so a patient can never be charged twice for "
               "the same visit (BILL.appointment_id is also UNIQUE).",
        "rule": "generate_bill procedure + uq_bill_appointment_id",
        "fix": "Record payments against the existing bill instead.",
    },
    20012: {
        "title": "That appointment does not exist",
        "why": "The appointment id was not found in the APPOINTMENT table.",
        "rule": "generate_bill procedure",
        "fix": "Pick an appointment from the list.",
    },
    20021: {
        "title": "That bill does not exist",
        "why": "The bill id was not found in the BILL table.",
        "rule": "record_payment procedure",
        "fix": "Pick a bill from the list.",
    },
    20030: {
        "title": "This sample was rejected",
        "why": "A rejected sample (clotted, haemolysed, mislabelled ...) cannot give a trustworthy "
               "reading, so the lab is not allowed to report a result for it.",
        "rule": "trg_flag_result (BEFORE INSERT trigger on TEST_RESULT)",
        "fix": "Collect a fresh sample for the test and enter the result against the new sample.",
    },
    20031: {
        "title": "That sample does not exist",
        "why": "A result must belong to a sample that was actually collected. The trigger looked the "
               "sample up to find its normal range and found nothing.",
        "rule": "trg_flag_result (BEFORE INSERT trigger on TEST_RESULT)",
        "fix": "Pick a sample from the list.",
    },
}

# -20020 has two cases (amount <= 0, and paying more than the balance)
PAYMENT_NOT_POSITIVE = {
    "title": "The payment amount must be more than zero",
    "why": "A payment of zero or a negative amount is not a real payment; refunds are out of scope.",
    "rule": "record_payment procedure",
    "fix": "Enter an amount above ₹0.",
}
PAYMENT_TOO_MUCH = {
    "title": "That is more than the balance due",
    "why": "The clinic never takes more money than the bill is for. amount_paid may never exceed "
           "total_amt; the procedure checks it, and ck_bill_paid_le_total backs it up in the table.",
    "rule": "record_payment procedure + ck_bill_paid_le_total",
    "fix": "Enter an amount up to the outstanding balance.",
}

# ---------------------------------------------------------------------------
# Declarative constraints, keyed by constraint name
# ---------------------------------------------------------------------------
CONSTRAINTS = {
    # UNIQUE
    "UQ_PATIENT_PHONE": ("This phone number is already registered",
                         "Each patient is identified at the front desk by phone number, so two "
                         "patients cannot share one.",
                         "Search for the existing patient, or use a different number."),
    "UQ_PATIENT_EMAIL": ("This email is already registered",
                         "Two patient records with one email would mix up their reports.",
                         "Use a different email, or leave it blank."),
    "UQ_DOCTOR_PHONE": ("Another doctor already has this phone number",
                        "Doctor phone numbers are unique.", "Use a different number."),
    "UQ_TEST_CATALOG_TEST_NAME": ("A test with this name already exists",
                                  "Test names are unique so a test is never listed twice.",
                                  "Use the existing test."),
    "UQ_SAMPLE_APPT_TEST": ("This test is already ordered for this visit",
                            "SAMPLE links a visit to a test (it resolves the many-to-many). The pair "
                            "(appointment_id, test_code) is unique, so the same test is never collected "
                            "or billed twice for one visit.",
                            "Untick the tests already ordered for this visit."),
    "UQ_BILL_APPOINTMENT_ID": ("This visit already has a bill",
                               "One visit, one bill: BILL.appointment_id is UNIQUE.",
                               "Record payments against the existing bill."),
    "UQ_TEST_RESULT_SAMPLE_ID": ("This sample already has a result",
                                 "One sample gives one result (TEST_RESULT.sample_id is UNIQUE).",
                                 "Correct the existing result instead."),
    # CHECK
    "CK_PATIENT_PHONE": ("Phone number must be exactly 10 digits",
                         "Indian mobile numbers have 10 digits; anything else cannot be dialled.",
                         "Enter 10 digits with no spaces, +91 or dashes."),
    "CK_PATIENT_GENDER": ("Gender must be M, F or O",
                          "Gender is stored as a single code so reports group consistently.",
                          "Choose M, F or O."),
    "CK_DOCTOR_PHONE": ("Phone number must be exactly 10 digits",
                        "Indian mobile numbers have 10 digits.", "Enter 10 digits."),
    "CK_APPOINTMENT_SLOT_TIME": ("The time must look like HH:MM (24-hour)",
                                 "Slots are stored as text such as 09:30 or 14:00. A REGEXP_LIKE check "
                                 "keeps every slot in one format so clashes can be compared.",
                                 "Use a 24-hour time such as 09:00 or 16:30."),
    "CK_APPOINTMENT_APPT_DATE": ("The appointment date must not carry a time",
                                 "appt_date stores the day only; the time lives in slot_time.",
                                 "Pass a plain date."),
    "CK_APPOINTMENT_STATUS": ("That is not a valid appointment status",
                              "Allowed: BOOKED, COMPLETED, CANCELLED, NO_SHOW.", "Use one of those."),
    "CK_SAMPLE_STATUS": ("That is not a valid sample status",
                         "Allowed: COLLECTED, PROCESSING, COMPLETED, REJECTED.", "Use one of those."),
    "CK_SAMPLE_SAMPLE_TYPE": ("That is not a valid sample type",
                              "Allowed: BLOOD, URINE, SALIVA, SWAB, OTHER.", "Use one of those."),
    "CK_BILL_DISCOUNT_PCT": ("Discount can be at most 50%",
                             "Clinic policy caps discounts at 50% so a visit is never given away; "
                             "the table checks discount_pct BETWEEN 0 AND 50.",
                             "Enter a discount between 0 and 50."),
    "CK_BILL_PAID_LE_TOTAL": ("That is more than the bill total",
                              "amount_paid may never exceed total_amt.",
                              "Enter an amount up to the outstanding balance."),
    "CK_BILL_TOTAL_AMT": ("The bill total does not add up",
                          "total_amt must equal (consultation + tests) less the discount. The CHECK "
                          "stops a total being edited by hand without its parts.",
                          "Recalculate the total from its parts."),
    "CK_BILL_PAYMENT_MODE": ("That is not a valid payment mode",
                             "Allowed: CASH, CARD, UPI, INSURANCE.", "Use one of those."),
}

# FOREIGN KEY, ORA-02291: the parent row does not exist
FK_PARENT_MISSING = {
    "FK_APPOINTMENT_PATIENT_ID": ("That patient does not exist",
                                  "Every appointment must point to a registered patient.",
                                  "Register the patient first."),
    "FK_APPOINTMENT_DOCTOR_ID": ("That doctor does not exist",
                                 "Every appointment must point to a doctor on the DOCTOR table.",
                                 "Pick a doctor from the list."),
    "FK_SAMPLE_APPOINTMENT_ID": ("That appointment does not exist",
                                 "A sample must belong to a real visit.", "Pick a visit from the list."),
    "FK_SAMPLE_TEST_CODE": ("That test is not in the catalogue",
                            "A sample must be for a test the clinic offers.", "Pick a test from the list."),
    "FK_BILL_APPOINTMENT_ID": ("That appointment does not exist",
                               "A bill must belong to a real visit.", "Pick a visit from the list."),
}

# FOREIGN KEY, ORA-02292: child rows still point at the row being deleted
FK_CHILD_EXISTS = {
    "FK_APPOINTMENT_DOCTOR_ID": ("That doctor still has appointments",
                                 "Deleting the doctor would leave appointments pointing at nobody. "
                                 "The foreign key has no ON DELETE action, so Oracle blocks it. That is "
                                 "why doctors are deactivated (status = 'INACTIVE') instead of deleted.",
                                 "Set the doctor's status to INACTIVE."),
    "FK_APPOINTMENT_PATIENT_ID": ("That patient still has appointments",
                                  "Deleting the patient would orphan their visit history.",
                                  "Keep the patient record."),
    "FK_SAMPLE_APPOINTMENT_ID": ("That appointment still has samples",
                                 "Deleting the visit would orphan its samples. Cancel it instead.",
                                 "Set the appointment's status to CANCELLED."),
    "FK_BILL_APPOINTMENT_ID": ("That appointment has a bill",
                               "Bills are financial records and must keep their visit.",
                               "Cancel instead of deleting."),
}

GENERIC = {
    1: ("That value is already in use", "A UNIQUE or PRIMARY KEY constraint allows each value once."),
    1400: ("A required field is empty", "That column is NOT NULL. Note: Oracle treats an empty "
                                        "string '' as NULL."),
    2290: ("That value is not allowed", "A CHECK constraint on the table rejected it."),
    2291: ("A linked record does not exist", "A FOREIGN KEY requires the parent row to exist first."),
    2292: ("Other records still depend on this one", "A FOREIGN KEY without ON DELETE blocks deleting "
                                                     "a parent that still has child rows."),
}

RULE_KIND = {1: "UNIQUE constraint", 2290: "CHECK constraint",
             2291: "FOREIGN KEY constraint", 2292: "FOREIGN KEY constraint"}


def explain(code, message):
    """Return {title, detail, why, rule, fix, code_label} for an error.

    code    - the ORA number (20003, 2290, ...) or None for an app-level refusal
    message - the cleaned message from db.business_error / the service layer
    """
    code_label = f"ORA-{code:05d}" if code else None
    base = {"detail": message, "code_label": code_label, "rule": "", "fix": ""}

    if code == 20020:
        info = PAYMENT_TOO_MUCH if "Overpayment" in (message or "") else PAYMENT_NOT_POSITIVE
        return {**base, **info}
    if code in BUSINESS_RULES:
        return {**base, **BUSINESS_RULES[code]}

    if code == 1400:
        # ORA-01400: cannot insert NULL into ("MEDITRACK"."PATIENT"."FIRST_NAME")
        column = re.search(r'"(\w+)"\."(\w+)"\)', message or "")
        field = f"{column.group(1)}.{column.group(2)}" if column else "a required column"
        title, why = GENERIC[1400]
        return {**base, "title": f"{title}: {field.split('.')[-1].replace('_', ' ').lower()}",
                "why": f"{field} is mandatory. {why}", "rule": f"NOT NULL constraint on {field}",
                "fix": "Fill in the field and try again."}

    constraint = re.search(r"\b((?:PK|FK|UQ|CK|NN)_[A-Z0-9_]+)", message or "")
    name = constraint.group(1) if constraint else None
    lookup = {2291: FK_PARENT_MISSING, 2292: FK_CHILD_EXISTS}.get(code, CONSTRAINTS)
    if name in lookup:
        title, why, fix = lookup[name]
        kind = RULE_KIND.get(code, "constraint")
        return {**base, "title": title, "why": why, "rule": f"{name.lower()} ({kind})", "fix": fix}
    if code in GENERIC:
        title, why = GENERIC[code]
        rule = f"{name.lower()} ({RULE_KIND.get(code, 'constraint')})" if name else ""
        return {**base, "title": title, "why": why, "rule": rule, "fix": "Correct the value and try again."}

    # app-level refusal (e.g. "nothing to cancel") or an unexpected database error
    return {**base, "title": message or "The request was refused", "detail": "",
            "why": "The request did not change any rows.", "rule": "", "fix": ""}
