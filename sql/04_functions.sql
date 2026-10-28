-- =====================================================================
-- MediTrack : 04_functions.sql
-- Stored functions. Both are read-only (no DML), so they can also be
-- called from plain SQL, e.g. SELECT patient_total_due(100001) FROM dual;
-- =====================================================================
SET SERVEROUTPUT ON

-- ---------------------------------------------------------------------
-- doctor_daily_load
-- Used by : T1 (book_appointment checks it against max_daily_appts)
-- Returns : number of non-CANCELLED appointments a doctor has on a day
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION doctor_daily_load (
    p_doctor_id  IN doctor.doctor_id%TYPE,
    p_date       IN DATE
) RETURN NUMBER
IS
    v_count  NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM appointment
     WHERE doctor_id = p_doctor_id
       AND appt_date = TRUNC(p_date)
       AND status   <> 'CANCELLED';

    RETURN v_count;
END doctor_daily_load;
/

-- ---------------------------------------------------------------------
-- patient_total_due
-- Used by : T5 (dues check after a payment), reports
-- Returns : SUM(total_amt - amount_paid) over the patient's bills, 0 if none
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION patient_total_due (
    p_patient_id  IN patient.patient_id%TYPE
) RETURN NUMBER
IS
    v_due  NUMBER;
BEGIN
    SELECT NVL(SUM(b.total_amt - b.amount_paid), 0)
      INTO v_due
      FROM bill b
      JOIN appointment a ON a.appointment_id = b.appointment_id
     WHERE a.patient_id = p_patient_id;

    RETURN v_due;
END patient_total_due;
/
