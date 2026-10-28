-- =====================================================================
-- MediTrack : 07_dml_demo.sql
-- INSERT / UPDATE / DELETE demonstrations, walked through as the
-- clinic's transactions T1-T7. Each step prints what it did.
-- Run on freshly seeded data (99 -> 01 -> 04 -> 05 -> 06 -> 02 -> 07).
-- Failure cases are run inside BEGIN ... EXCEPTION blocks so the
-- business-rule error is printed and the script carries on.
-- =====================================================================
SET SERVEROUTPUT ON
SET DEFINE OFF

-- =====================================================================
-- T1. Register a patient and book an appointment
--     INSERT PATIENT, book_appointment, doctor_daily_load,
--     trg_no_double_booking
-- =====================================================================
INSERT INTO patient (patient_id, first_name, last_name, dob, gender, phone, email, address)
VALUES (seq_patient.NEXTVAL, 'Neha', 'Kapoor', DATE '1997-06-21', 'F', '9345678901',
        'neha.kapoor@gmail.com', '15 Sainathapuram, Vellore');

DECLARE
    v_patient_id  patient.patient_id%TYPE;
    v_appt_id     appointment.appointment_id%TYPE;
BEGIN
    SELECT patient_id INTO v_patient_id FROM patient WHERE phone = '9345678901';

    DBMS_OUTPUT.PUT_LINE('T1: Dr 1001 load tomorrow before booking = '
        || doctor_daily_load(1001, TRUNC(SYSDATE) + 1));

    book_appointment(v_patient_id, 1001, TRUNC(SYSDATE) + 1, '09:00', 'Annual health check', v_appt_id);

    DBMS_OUTPUT.PUT_LINE('T1: booked appointment ' || v_appt_id || ' for patient ' || v_patient_id);
    DBMS_OUTPUT.PUT_LINE('T1: Dr 1001 load tomorrow after booking  = '
        || doctor_daily_load(1001, TRUNC(SYSDATE) + 1));
END;
/

-- T1 failure: same doctor, same slot, different patient -> -20003 (trigger)
DECLARE
    v_appt_id  appointment.appointment_id%TYPE;
BEGIN
    book_appointment(100003, 1001, TRUNC(SYSDATE) + 1, '09:00', 'Follow-up', v_appt_id);
EXCEPTION
    WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('T1 rejected as expected: ' || SQLERRM);
END;
/

-- T1 failure: INACTIVE doctor -> -20001
DECLARE
    v_appt_id  appointment.appointment_id%TYPE;
BEGIN
    book_appointment(100003, 1010, TRUNC(SYSDATE) + 1, '11:00', 'General check', v_appt_id);
EXCEPTION
    WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('T1 rejected as expected: ' || SQLERRM);
END;
/

-- T1 failure: Dr 1009 allows 2 per day and already has 2 today -> -20002
DECLARE
    v_appt_id  appointment.appointment_id%TYPE;
BEGIN
    book_appointment(100010, 1009, TRUNC(SYSDATE), '16:00', 'Ear ache', v_appt_id);
EXCEPTION
    WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('T1 rejected as expected: ' || SQLERRM);
END;
/

-- =====================================================================
-- T2. Order tests and collect samples for today's visit 500018
--     (Aditya Menon with Dr. Rajesh Kumar)
--     INSERT SAMPLE, UPDATE SAMPLE status
-- =====================================================================
INSERT INTO sample (sample_id, appointment_id, test_code, sample_type, collected_by)
VALUES (seq_sample.NEXTVAL, 500018, 'FBS', 'BLOOD', 'Lakshmi (Tech)');

INSERT INTO sample (sample_id, appointment_id, test_code, sample_type, collected_by)
VALUES (seq_sample.NEXTVAL, 500018, 'HBA1C', 'BLOOD', 'Lakshmi (Tech)');

-- the FBS tube goes onto the analyser
UPDATE sample
   SET status = 'PROCESSING'
 WHERE appointment_id = 500018
   AND test_code = 'FBS';

-- T2 failure: ordering the same test twice in one visit -> uq_sample_appt_test
BEGIN
    INSERT INTO sample (sample_id, appointment_id, test_code, sample_type)
    VALUES (seq_sample.NEXTVAL, 500018, 'FBS', 'BLOOD');
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN DBMS_OUTPUT.PUT_LINE('T2 rejected as expected: ' || SQLERRM);
END;
/

SELECT sample_id, appointment_id, test_code, sample_type, status
  FROM sample
 WHERE appointment_id = 500018;

-- =====================================================================
-- T3. Enter test results (flag is set by trg_flag_result)
--     INSERT TEST_RESULT, trg_flag_result
-- =====================================================================
INSERT INTO test_result (result_id, sample_id, result_value, verified_by)
SELECT seq_test_result.NEXTVAL, sample_id, 165, 1004
  FROM sample
 WHERE appointment_id = 500018 AND test_code = 'FBS';

INSERT INTO test_result (result_id, sample_id, result_value, verified_by)
SELECT seq_test_result.NEXTVAL, sample_id, 5.4, 1004
  FROM sample
 WHERE appointment_id = 500018 AND test_code = 'HBA1C';

-- both samples are now COMPLETED and each result carries its flag
SELECT s.sample_id, s.test_code, s.status AS sample_status, r.result_value, r.result_flag
  FROM sample s
  JOIN test_result r ON r.sample_id = s.sample_id
 WHERE s.appointment_id = 500018;

-- T3 failure: a result for the REJECTED sample 700013 -> -20030
BEGIN
    UPDATE test_result SET result_value = 160 WHERE sample_id = 700013;
EXCEPTION
    WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('T3 rejected as expected: ' || SQLERRM);
END;
/

-- =====================================================================
-- T4. Complete the visit and raise the bill (one unit of work)
--     UPDATE APPOINTMENT, generate_bill
-- =====================================================================
UPDATE appointment
   SET status = 'COMPLETED'
 WHERE appointment_id = 500018;

BEGIN
    generate_bill(500018, 10);   -- 10% senior-citizen discount
    DBMS_OUTPUT.PUT_LINE('T4: bill raised for appointment 500018');
END;
/

-- T4 failures: billing a BOOKED visit (-20010) and billing twice (-20011)
BEGIN
    generate_bill(500019);
EXCEPTION
    WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('T4 rejected as expected: ' || SQLERRM);
END;
/
BEGIN
    generate_bill(500018);
EXCEPTION
    WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('T4 rejected as expected: ' || SQLERRM);
END;
/

SELECT bill_id, appointment_id, consultation_amt, test_amt, discount_pct, total_amt, payment_status
  FROM bill
 WHERE appointment_id = 500018;

COMMIT;

-- =====================================================================
-- T5. Take a payment and check the patient's dues
--     record_payment, trg_payment_status, patient_total_due
-- =====================================================================
DECLARE
    v_bill_id  bill.bill_id%TYPE;
BEGIN
    SELECT bill_id INTO v_bill_id FROM bill WHERE appointment_id = 500018;

    DBMS_OUTPUT.PUT_LINE('T5: patient 100011 due before payment = ' || patient_total_due(100011));
    record_payment(v_bill_id, 500, 'UPI');
    DBMS_OUTPUT.PUT_LINE('T5: paid 500 by UPI on bill ' || v_bill_id);
    DBMS_OUTPUT.PUT_LINE('T5: patient 100011 due after payment  = ' || patient_total_due(100011));
END;
/

-- T5 failure: paying more than the balance -> -20020
BEGIN
    record_payment(900005, 5000, 'CASH');
EXCEPTION
    WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('T5 rejected as expected: ' || SQLERRM);
END;
/

SELECT bill_id, total_amt, amount_paid, payment_status, payment_mode
  FROM bill
 WHERE appointment_id = 500018;

COMMIT;

-- =====================================================================
-- T6. End-of-day billing for the last two days (explicit cursor)
--     end_of_day_billing -> generate_bill for each unbilled visit
-- =====================================================================
BEGIN
    end_of_day_billing(TRUNC(SYSDATE) - 2);
    end_of_day_billing(TRUNC(SYSDATE) - 1);
END;
/

SELECT bill_id, appointment_id, total_amt, payment_status
  FROM bill
 WHERE appointment_id IN (500013, 500014);

-- =====================================================================
-- T7. Cancel a visit and delete a rejected sample
--     UPDATE APPOINTMENT, DELETE SAMPLE (cascades to TEST_RESULT)
-- =====================================================================
UPDATE appointment
   SET status = 'CANCELLED'
 WHERE appointment_id = 500019
   AND status = 'BOOKED';

-- the freed 10:30 slot can now be booked by someone else
DECLARE
    v_appt_id  appointment.appointment_id%TYPE;
BEGIN
    book_appointment(100005, 1001, TRUNC(SYSDATE), '10:30', 'Fever follow-up', v_appt_id);
    DBMS_OUTPUT.PUT_LINE('T7: cancelled slot rebooked as appointment ' || v_appt_id);
END;
/

SELECT COUNT(*) AS results_for_700013_before FROM test_result WHERE sample_id = 700013;

DELETE FROM sample
 WHERE sample_id = 700013
   AND status = 'REJECTED';

-- ON DELETE CASCADE removed the result as well
SELECT COUNT(*) AS results_for_700013_after FROM test_result WHERE sample_id = 700013;

COMMIT;
