-- =====================================================================
-- MediTrack : 06_triggers.sql
-- Row-level triggers that enforce rules no CHECK constraint can express.
--
-- Business-rule error codes raised here (RAISE_APPLICATION_ERROR):
--   -20003  Slot clash: doctor or patient already booked   (trg_no_double_booking)
--   -20030  Result entered for a REJECTED sample           (trg_flag_result)
--   -20031  Sample does not exist                          (trg_flag_result)
--
-- Run BEFORE 02_seed_data.sql so the seed rows pass through the triggers
-- (flags and payment statuses in the seed are set by the triggers).
-- =====================================================================
SET SERVEROUTPUT ON

-- ---------------------------------------------------------------------
-- trg_no_double_booking                                  Transaction T1
-- A doctor cannot see two patients, and a patient cannot see two
-- doctors, in the same date + slot. CANCELLED rows are ignored, so a
-- cancelled slot can be booked again (why this is a trigger and not a
-- UNIQUE constraint).
--
-- BEFORE INSERT only: a row trigger may not query its own table during
-- an UPDATE (ORA-04091 mutating table). Rescheduling = cancel + rebook.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TRIGGER trg_no_double_booking
BEFORE INSERT ON appointment
FOR EACH ROW
DECLARE
    v_clashes  NUMBER;
BEGIN
    IF :NEW.status <> 'CANCELLED' THEN
        SELECT COUNT(*)
          INTO v_clashes
          FROM appointment
         WHERE appt_date = :NEW.appt_date
           AND slot_time = :NEW.slot_time
           AND status   <> 'CANCELLED'
           AND (doctor_id = :NEW.doctor_id OR patient_id = :NEW.patient_id);

        IF v_clashes > 0 THEN
            RAISE_APPLICATION_ERROR(-20003, 'Slot ' || :NEW.slot_time || ' on '
                || TO_CHAR(:NEW.appt_date, 'DD-MON-YYYY')
                || ' is already taken by this doctor or this patient');
        END IF;
    END IF;
END;
/

-- ---------------------------------------------------------------------
-- trg_flag_result                                        Transaction T3
-- Looks up the test's normal range through SAMPLE -> TEST_CATALOG and
-- sets result_flag to LOW / NORMAL / HIGH, then marks the SAMPLE as
-- COMPLETED. The technician never types the flag.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TRIGGER trg_flag_result
BEFORE INSERT OR UPDATE OF result_value ON test_result
FOR EACH ROW
DECLARE
    v_min            test_catalog.normal_min%TYPE;
    v_max            test_catalog.normal_max%TYPE;
    v_sample_status  sample.status%TYPE;
BEGIN
    BEGIN
        SELECT tc.normal_min, tc.normal_max, s.status
          INTO v_min, v_max, v_sample_status
          FROM sample s
          JOIN test_catalog tc ON tc.test_code = s.test_code
         WHERE s.sample_id = :NEW.sample_id;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20031, 'Sample ' || :NEW.sample_id || ' does not exist');
    END;

    IF v_sample_status = 'REJECTED' THEN
        RAISE_APPLICATION_ERROR(-20030, 'Sample ' || :NEW.sample_id
            || ' was REJECTED; collect a new sample before entering a result');
    END IF;

    IF :NEW.result_value < v_min THEN
        :NEW.result_flag := 'LOW';
    ELSIF :NEW.result_value > v_max THEN
        :NEW.result_flag := 'HIGH';
    ELSE
        :NEW.result_flag := 'NORMAL';
    END IF;

    UPDATE sample
       SET status = 'COMPLETED'
     WHERE sample_id = :NEW.sample_id;
END;
/

-- ---------------------------------------------------------------------
-- trg_payment_status                                     Transaction T5
-- Keeps payment_status consistent with amount_paid on every payment.
-- ---------------------------------------------------------------------
CREATE OR REPLACE TRIGGER trg_payment_status
BEFORE UPDATE OF amount_paid ON bill
FOR EACH ROW
BEGIN
    IF :NEW.amount_paid = 0 THEN
        :NEW.payment_status := 'UNPAID';
    ELSIF :NEW.amount_paid >= :NEW.total_amt THEN
        :NEW.payment_status := 'PAID';
    ELSE
        :NEW.payment_status := 'PARTIAL';
    END IF;
END;
/
