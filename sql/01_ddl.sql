-- =====================================================================
-- MediTrack : 01_ddl.sql
-- Creates the 7 tables (in dependency order) with every constraint
-- named, plus one sequence per surrogate key.
--
-- Constraint naming:  pk_<table>  fk_<table>_<col>  uq_<table>_<col>
--                     ck_<table>_<col>
-- Run 99_drop_all.sql first for a clean re-run.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Sequences (NOCACHE so numbers stay consecutive and readable in a demo)
-- ---------------------------------------------------------------------
CREATE SEQUENCE seq_patient     START WITH 100001 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_doctor      START WITH 1001   INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_appointment START WITH 500001 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_sample      START WITH 700001 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_test_result START WITH 800001 INCREMENT BY 1 NOCACHE;
CREATE SEQUENCE seq_bill        START WITH 900001 INCREMENT BY 1 NOCACHE;

-- ---------------------------------------------------------------------
-- 1. PATIENT : one row per registered person
-- ---------------------------------------------------------------------
CREATE TABLE patient (
    patient_id     NUMBER(6)     CONSTRAINT pk_patient PRIMARY KEY,
    first_name     VARCHAR2(30)  CONSTRAINT nn_patient_first_name NOT NULL,
    last_name      VARCHAR2(30)  CONSTRAINT nn_patient_last_name NOT NULL,
    dob            DATE          CONSTRAINT nn_patient_dob NOT NULL,
    gender         CHAR(1)       CONSTRAINT nn_patient_gender NOT NULL,
    phone          VARCHAR2(10)  CONSTRAINT nn_patient_phone NOT NULL,
    email          VARCHAR2(60),
    address        VARCHAR2(150),
    registered_on  DATE          DEFAULT SYSDATE
                                 CONSTRAINT nn_patient_registered_on NOT NULL,
    CONSTRAINT ck_patient_gender CHECK (gender IN ('M', 'F', 'O')),
    CONSTRAINT ck_patient_phone  CHECK (REGEXP_LIKE(phone, '^[0-9]{10}$')),
    CONSTRAINT uq_patient_phone  UNIQUE (phone),
    CONSTRAINT uq_patient_email  UNIQUE (email)
);

-- ---------------------------------------------------------------------
-- 2. DOCTOR : consultants; deactivated (status = 'INACTIVE'), never deleted
-- ---------------------------------------------------------------------
CREATE TABLE doctor (
    doctor_id         NUMBER(4)     CONSTRAINT pk_doctor PRIMARY KEY,
    full_name         VARCHAR2(60)  CONSTRAINT nn_doctor_full_name NOT NULL,
    specialization    VARCHAR2(40)  CONSTRAINT nn_doctor_specialization NOT NULL,
    phone             VARCHAR2(10),
    consultation_fee  NUMBER(8,2)   CONSTRAINT nn_doctor_consultation_fee NOT NULL,
    max_daily_appts   NUMBER(2)     DEFAULT 20
                                    CONSTRAINT nn_doctor_max_daily_appts NOT NULL,
    status            VARCHAR2(8)   DEFAULT 'ACTIVE'
                                    CONSTRAINT nn_doctor_status NOT NULL,
    CONSTRAINT ck_doctor_consultation_fee CHECK (consultation_fee > 0),
    CONSTRAINT ck_doctor_max_daily_appts  CHECK (max_daily_appts BETWEEN 1 AND 50),
    CONSTRAINT ck_doctor_status           CHECK (status IN ('ACTIVE', 'INACTIVE')),
    CONSTRAINT ck_doctor_phone            CHECK (REGEXP_LIKE(phone, '^[0-9]{10}$')),
    CONSTRAINT uq_doctor_phone            UNIQUE (phone)
);

-- ---------------------------------------------------------------------
-- 3. TEST_CATALOG : master list of lab tests, price and normal range
-- ---------------------------------------------------------------------
CREATE TABLE test_catalog (
    test_code       VARCHAR2(10)  CONSTRAINT pk_test_catalog PRIMARY KEY,
    test_name       VARCHAR2(60)  CONSTRAINT nn_test_catalog_test_name NOT NULL,
    category        VARCHAR2(30)  CONSTRAINT nn_test_catalog_category NOT NULL,
    price           NUMBER(8,2)   CONSTRAINT nn_test_catalog_price NOT NULL,
    unit            VARCHAR2(15)  CONSTRAINT nn_test_catalog_unit NOT NULL,
    normal_min      NUMBER(10,2)  CONSTRAINT nn_test_catalog_normal_min NOT NULL,
    normal_max      NUMBER(10,2)  CONSTRAINT nn_test_catalog_normal_max NOT NULL,
    turnaround_hrs  NUMBER(3)     DEFAULT 24
                                  CONSTRAINT nn_test_catalog_turnaround NOT NULL,
    CONSTRAINT uq_test_catalog_test_name  UNIQUE (test_name),
    CONSTRAINT ck_test_catalog_price      CHECK (price > 0),
    CONSTRAINT ck_test_catalog_range      CHECK (normal_min <= normal_max),
    CONSTRAINT ck_test_catalog_turnaround CHECK (turnaround_hrs > 0)
);

-- ---------------------------------------------------------------------
-- 4. APPOINTMENT : a patient's visit to one doctor in one slot
--    Double booking is blocked by trg_no_double_booking (not a UNIQUE
--    constraint) so that a CANCELLED slot can be booked again.
-- ---------------------------------------------------------------------
CREATE TABLE appointment (
    appointment_id  NUMBER(8)      CONSTRAINT pk_appointment PRIMARY KEY,
    patient_id      NUMBER(6)      CONSTRAINT nn_appointment_patient_id NOT NULL,
    doctor_id       NUMBER(4)      CONSTRAINT nn_appointment_doctor_id NOT NULL,
    appt_date       DATE           CONSTRAINT nn_appointment_appt_date NOT NULL,
    slot_time       VARCHAR2(5)    CONSTRAINT nn_appointment_slot_time NOT NULL,
    reason          VARCHAR2(200),
    status          VARCHAR2(10)   DEFAULT 'BOOKED'
                                   CONSTRAINT nn_appointment_status NOT NULL,
    booked_on       DATE           DEFAULT SYSDATE
                                   CONSTRAINT nn_appointment_booked_on NOT NULL,
    CONSTRAINT fk_appointment_patient_id FOREIGN KEY (patient_id)
        REFERENCES patient (patient_id),
    CONSTRAINT fk_appointment_doctor_id FOREIGN KEY (doctor_id)
        REFERENCES doctor (doctor_id),
    -- 'HH:MI' in 24-hour form, e.g. '09:30', '16:00'
    CONSTRAINT ck_appointment_slot_time
        CHECK (REGEXP_LIKE(slot_time, '^([01][0-9]|2[0-3]):[0-5][0-9]$')),
    -- appt_date holds the day only; the time lives in slot_time
    CONSTRAINT ck_appointment_appt_date CHECK (appt_date = TRUNC(appt_date)),
    CONSTRAINT ck_appointment_status
        CHECK (status IN ('BOOKED', 'COMPLETED', 'CANCELLED', 'NO_SHOW'))
);

-- ---------------------------------------------------------------------
-- 5. SAMPLE : resolves the M:N between APPOINTMENT and TEST_CATALOG.
--    One row = one test ordered in one visit + the specimen collected.
-- ---------------------------------------------------------------------
CREATE TABLE sample (
    sample_id       NUMBER(8)     CONSTRAINT pk_sample PRIMARY KEY,
    appointment_id  NUMBER(8)     CONSTRAINT nn_sample_appointment_id NOT NULL,
    test_code       VARCHAR2(10)  CONSTRAINT nn_sample_test_code NOT NULL,
    sample_type     VARCHAR2(6)   CONSTRAINT nn_sample_sample_type NOT NULL,
    collected_on    DATE          DEFAULT SYSDATE
                                  CONSTRAINT nn_sample_collected_on NOT NULL,
    collected_by    VARCHAR2(40),
    status          VARCHAR2(10)  DEFAULT 'COLLECTED'
                                  CONSTRAINT nn_sample_status NOT NULL,
    remarks         VARCHAR2(100),
    CONSTRAINT fk_sample_appointment_id FOREIGN KEY (appointment_id)
        REFERENCES appointment (appointment_id),
    CONSTRAINT fk_sample_test_code FOREIGN KEY (test_code)
        REFERENCES test_catalog (test_code),
    -- the same test cannot be ordered twice in one visit
    CONSTRAINT uq_sample_appt_test UNIQUE (appointment_id, test_code),
    CONSTRAINT ck_sample_sample_type
        CHECK (sample_type IN ('BLOOD', 'URINE', 'SALIVA', 'SWAB', 'OTHER')),
    CONSTRAINT ck_sample_status
        CHECK (status IN ('COLLECTED', 'PROCESSING', 'COMPLETED', 'REJECTED'))
);

-- ---------------------------------------------------------------------
-- 6. TEST_RESULT : at most one result per sample (UNIQUE sample_id).
--    Deleting a sample deletes its result (ON DELETE CASCADE).
--    Removing a doctor keeps the result but clears verified_by.
-- ---------------------------------------------------------------------
CREATE TABLE test_result (
    result_id     NUMBER(8)      CONSTRAINT pk_test_result PRIMARY KEY,
    sample_id     NUMBER(8)      CONSTRAINT nn_test_result_sample_id NOT NULL,
    result_value  NUMBER(10,2)   CONSTRAINT nn_test_result_result_value NOT NULL,
    result_flag   VARCHAR2(6)    DEFAULT 'NORMAL'
                                 CONSTRAINT nn_test_result_result_flag NOT NULL,
    result_date   DATE           DEFAULT SYSDATE
                                 CONSTRAINT nn_test_result_result_date NOT NULL,
    verified_by   NUMBER(4),
    remarks       VARCHAR2(200),
    CONSTRAINT fk_test_result_sample_id FOREIGN KEY (sample_id)
        REFERENCES sample (sample_id) ON DELETE CASCADE,
    CONSTRAINT fk_test_result_verified_by FOREIGN KEY (verified_by)
        REFERENCES doctor (doctor_id) ON DELETE SET NULL,
    CONSTRAINT uq_test_result_sample_id UNIQUE (sample_id),
    CONSTRAINT ck_test_result_result_flag
        CHECK (result_flag IN ('LOW', 'NORMAL', 'HIGH'))
);

-- ---------------------------------------------------------------------
-- 7. BILL : one bill per appointment (UNIQUE appointment_id).
--    consultation_amt / test_amt / total_amt are a SNAPSHOT taken when
--    the bill is raised, so later fee or price changes never alter an
--    issued bill.
-- ---------------------------------------------------------------------
CREATE TABLE bill (
    bill_id           NUMBER(8)     CONSTRAINT pk_bill PRIMARY KEY,
    appointment_id    NUMBER(8)     CONSTRAINT nn_bill_appointment_id NOT NULL,
    bill_date         DATE          DEFAULT SYSDATE
                                    CONSTRAINT nn_bill_bill_date NOT NULL,
    consultation_amt  NUMBER(10,2)  CONSTRAINT nn_bill_consultation_amt NOT NULL,
    test_amt          NUMBER(10,2)  DEFAULT 0
                                    CONSTRAINT nn_bill_test_amt NOT NULL,
    discount_pct      NUMBER(5,2)   DEFAULT 0
                                    CONSTRAINT nn_bill_discount_pct NOT NULL,
    total_amt         NUMBER(10,2)  CONSTRAINT nn_bill_total_amt NOT NULL,
    amount_paid       NUMBER(10,2)  DEFAULT 0
                                    CONSTRAINT nn_bill_amount_paid NOT NULL,
    payment_status    VARCHAR2(7)   DEFAULT 'UNPAID'
                                    CONSTRAINT nn_bill_payment_status NOT NULL,
    payment_mode      VARCHAR2(10),
    CONSTRAINT fk_bill_appointment_id FOREIGN KEY (appointment_id)
        REFERENCES appointment (appointment_id),
    CONSTRAINT uq_bill_appointment_id UNIQUE (appointment_id),
    CONSTRAINT ck_bill_consultation_amt CHECK (consultation_amt >= 0),
    CONSTRAINT ck_bill_test_amt         CHECK (test_amt >= 0),
    CONSTRAINT ck_bill_discount_pct     CHECK (discount_pct BETWEEN 0 AND 50),
    -- the stored total must always equal the bill's own parts
    CONSTRAINT ck_bill_total_amt
        CHECK (total_amt = ROUND((consultation_amt + test_amt) * (1 - discount_pct / 100), 2)),
    CONSTRAINT ck_bill_amount_paid      CHECK (amount_paid >= 0),
    CONSTRAINT ck_bill_paid_le_total    CHECK (amount_paid <= total_amt),
    CONSTRAINT ck_bill_payment_status
        CHECK (payment_status IN ('UNPAID', 'PARTIAL', 'PAID')),
    CONSTRAINT ck_bill_payment_mode
        CHECK (payment_mode IN ('CASH', 'CARD', 'UPI', 'INSURANCE'))
);
