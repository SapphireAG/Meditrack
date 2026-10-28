-- =====================================================================
-- MediTrack : 05_procedures.sql
-- Stored procedures for the clinic's transactions.
--
-- Business-rule error codes raised here (RAISE_APPLICATION_ERROR):
--   -20001  Doctor is INACTIVE                          (book_appointment)
--   -20002  Doctor's day is full (max_daily_appts)      (book_appointment)
--   -20004  Appointment date is in the past             (book_appointment)
--   -20005  Doctor does not exist                       (book_appointment)
--   -20010  Appointment is not COMPLETED                (generate_bill)
--   -20011  Appointment already has a bill              (generate_bill)
--   -20012  Appointment does not exist                  (generate_bill)
--   -20020  Payment amount <= 0 or exceeds the balance  (record_payment)
--   -20021  Bill does not exist                         (record_payment)
--   (-20003 and -20030/-20031 are raised by triggers, see 06_triggers.sql)
--
-- Transaction control: book_appointment, generate_bill and
-- record_payment do NOT commit. The caller (the app, or the batch job
-- end_of_day_billing) decides when the unit of work is complete and
-- commits once, so several steps succeed or fail together.
-- =====================================================================
SET SERVEROUTPUT ON

-- ---------------------------------------------------------------------
-- book_appointment                                     Transaction T1
-- Checks the doctor is ACTIVE and has room on that day (using
-- doctor_daily_load), then inserts the appointment. The INSERT fires
-- trg_no_double_booking, which rejects a clash in the same slot.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE book_appointment (
    p_patient_id  IN  appointment.patient_id%TYPE,
    p_doctor_id   IN  appointment.doctor_id%TYPE,
    p_date        IN  DATE,
    p_slot        IN  appointment.slot_time%TYPE,
    p_reason      IN  appointment.reason%TYPE,
    p_appt_id     OUT appointment.appointment_id%TYPE
)
IS
    v_status  doctor.status%TYPE;
    v_max     doctor.max_daily_appts%TYPE;
BEGIN
    IF TRUNC(p_date) < TRUNC(SYSDATE) THEN
        RAISE_APPLICATION_ERROR(-20004, 'Cannot book an appointment in the past');
    END IF;

    BEGIN
        SELECT status, max_daily_appts
          INTO v_status, v_max
          FROM doctor
         WHERE doctor_id = p_doctor_id;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20005, 'Doctor ' || p_doctor_id || ' does not exist');
    END;

    IF v_status = 'INACTIVE' THEN
        RAISE_APPLICATION_ERROR(-20001, 'Doctor ' || p_doctor_id || ' is INACTIVE and cannot take bookings');
    END IF;

    IF doctor_daily_load(p_doctor_id, p_date) >= v_max THEN
        RAISE_APPLICATION_ERROR(-20002, 'Doctor ' || p_doctor_id || ' already has '
            || v_max || ' appointments on ' || TO_CHAR(p_date, 'DD-MON-YYYY'));
    END IF;

    INSERT INTO appointment (appointment_id, patient_id, doctor_id, appt_date, slot_time, reason)
    VALUES (seq_appointment.NEXTVAL, p_patient_id, p_doctor_id, TRUNC(p_date), p_slot, p_reason)
    RETURNING appointment_id INTO p_appt_id;
END book_appointment;
/

-- ---------------------------------------------------------------------
-- generate_bill                                     Transactions T4, T6
-- Bill = consultation fee (from DOCTOR) + SUM(price) of the visit's
-- non-REJECTED samples, less the discount. The amounts are copied into
-- BILL as a snapshot.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE generate_bill (
    p_appointment_id  IN bill.appointment_id%TYPE,
    p_discount_pct    IN bill.discount_pct%TYPE DEFAULT 0
)
IS
    v_status        appointment.status%TYPE;
    v_fee           doctor.consultation_fee%TYPE;
    v_test_amt      bill.test_amt%TYPE;
    v_total         bill.total_amt%TYPE;
    v_bill_count    NUMBER;
BEGIN
    BEGIN
        SELECT a.status, d.consultation_fee
          INTO v_status, v_fee
          FROM appointment a
          JOIN doctor d ON d.doctor_id = a.doctor_id
         WHERE a.appointment_id = p_appointment_id;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20012, 'Appointment ' || p_appointment_id || ' does not exist');
    END;

    IF v_status <> 'COMPLETED' THEN
        RAISE_APPLICATION_ERROR(-20010, 'Appointment ' || p_appointment_id
            || ' is ' || v_status || '; only COMPLETED visits can be billed');
    END IF;

    SELECT COUNT(*)
      INTO v_bill_count
      FROM bill
     WHERE appointment_id = p_appointment_id;

    IF v_bill_count > 0 THEN
        RAISE_APPLICATION_ERROR(-20011, 'Appointment ' || p_appointment_id || ' already has a bill');
    END IF;

    SELECT NVL(SUM(tc.price), 0)
      INTO v_test_amt
      FROM sample s
      JOIN test_catalog tc ON tc.test_code = s.test_code
     WHERE s.appointment_id = p_appointment_id
       AND s.status <> 'REJECTED';

    v_total := ROUND((v_fee + v_test_amt) * (1 - p_discount_pct / 100), 2);

    INSERT INTO bill (bill_id, appointment_id, consultation_amt, test_amt, discount_pct, total_amt)
    VALUES (seq_bill.NEXTVAL, p_appointment_id, v_fee, v_test_amt, p_discount_pct, v_total);
END generate_bill;
/

-- ---------------------------------------------------------------------
-- record_payment                                         Transaction T5
-- Adds a payment to a bill. The UPDATE of amount_paid fires
-- trg_payment_status, which sets UNPAID / PARTIAL / PAID.
-- SELECT ... FOR UPDATE locks the bill row so two counters cannot
-- take money against the same balance at the same time.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE record_payment (
    p_bill_id  IN bill.bill_id%TYPE,
    p_amount   IN bill.amount_paid%TYPE,
    p_mode     IN bill.payment_mode%TYPE
)
IS
    v_total  bill.total_amt%TYPE;
    v_paid   bill.amount_paid%TYPE;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20020, 'Payment amount must be greater than zero');
    END IF;

    BEGIN
        SELECT total_amt, amount_paid
          INTO v_total, v_paid
          FROM bill
         WHERE bill_id = p_bill_id
           FOR UPDATE;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20021, 'Bill ' || p_bill_id || ' does not exist');
    END;

    IF v_paid + p_amount > v_total THEN
        RAISE_APPLICATION_ERROR(-20020, 'Overpayment: balance on bill ' || p_bill_id
            || ' is ' || TO_CHAR(v_total - v_paid, 'FM999999990.00'));
    END IF;

    UPDATE bill
       SET amount_paid  = amount_paid + p_amount,
           payment_mode = p_mode
     WHERE bill_id = p_bill_id;
END record_payment;
/

-- ---------------------------------------------------------------------
-- end_of_day_billing                                     Transaction T6
-- Explicit cursor over the day's COMPLETED appointments that have no
-- bill yet; calls generate_bill for each one. Commits ONCE at the end:
-- either every visit of the day is billed or (on error) none is.
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE end_of_day_billing (
    p_date  IN DATE
)
IS
    CURSOR c_unbilled IS
        SELECT a.appointment_id
          FROM appointment a
         WHERE a.appt_date = TRUNC(p_date)
           AND a.status    = 'COMPLETED'
           AND NOT EXISTS (SELECT 1
                             FROM bill b
                            WHERE b.appointment_id = a.appointment_id)
         ORDER BY a.appointment_id;

    v_appt_id  appointment.appointment_id%TYPE;
    v_count    NUMBER := 0;
BEGIN
    OPEN c_unbilled;
    LOOP
        FETCH c_unbilled INTO v_appt_id;
        EXIT WHEN c_unbilled%NOTFOUND;

        generate_bill(v_appt_id);
        v_count := v_count + 1;
        DBMS_OUTPUT.PUT_LINE('Billed appointment ' || v_appt_id);
    END LOOP;
    CLOSE c_unbilled;

    COMMIT;
    DBMS_OUTPUT.PUT_LINE(v_count || ' bill(s) generated for ' || TO_CHAR(p_date, 'DD-MON-YYYY'));
EXCEPTION
    WHEN OTHERS THEN
        IF c_unbilled%ISOPEN THEN
            CLOSE c_unbilled;
        END IF;
        ROLLBACK;
        RAISE;
END end_of_day_billing;
/
