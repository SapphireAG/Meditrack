-- =====================================================================
-- MediTrack : 02_seed_data.sql
-- Realistic sample data for every table (>= 10 rows each).
--
-- RUN ORDER: 99_drop_all -> 01_ddl -> 04_functions -> 05_procedures
--            -> 06_triggers -> 02_seed_data
-- The triggers must exist first: result flags, sample COMPLETED status
-- and bill payment statuses below are all set BY the triggers.
--
-- Dates are relative to TRUNC(SYSDATE) (written D below) so that
-- "today's schedule" and "overdue samples" always have data on demo day.
-- IDs come from the sequences; on a clean schema they are deterministic,
-- so the comment next to each row shows the ID it receives.
--
-- Built-in demo cases:
--   * Dr. Ramesh Patel (1010) is INACTIVE                 -> -20001 demo
--   * Dr. Sanjay Gupta (1009) max 2/day, full today       -> -20002 demo
--   * Today 09:00 with Dr. Nair: cancelled, then rebooked -> trigger allows it
--   * Test B12 is never ordered                           -> NOT EXISTS query
--   * Sample 700013 (PLT) resulted then REJECTED          -> T7 cascade delete
--   * Visits 500013 and 500014 are COMPLETED, not billed  -> T6 end-of-day
--   * Bills cover UNPAID / PARTIAL / PAID
-- =====================================================================
SET DEFINE OFF

-- ---------------------------------------------------------------------
-- PATIENT (12 rows)                                    IDs 100001-100012
-- ---------------------------------------------------------------------
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Aarav',    'Sharma', DATE '1985-03-12', 'M', '9876543210', 'aarav.sharma@gmail.com',   '12 Gandhi Road, Vellore',        TRUNC(SYSDATE) - 160);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Ananya',   'Iyer',   DATE '1990-07-25', 'F', '9845012345', 'ananya.iyer@yahoo.com',    '4 Anna Nagar, Chennai',          TRUNC(SYSDATE) - 150);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Rohan',    'Verma',  DATE '1978-11-02', 'M', '9810023456', 'rohan.verma@outlook.com',  '7 Katpadi Main Road, Vellore',   TRUNC(SYSDATE) - 130);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Diya',     'Reddy',  DATE '1995-01-18', 'F', '9900112233', 'diya.reddy@gmail.com',     '22 Sathuvachari, Vellore',       TRUNC(SYSDATE) - 115);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Vihaan',   'Gupta',  DATE '2001-05-30', 'M', '9123456780', 'vihaan.g@gmail.com',       'VIT Men''s Hostel, Vellore',     TRUNC(SYSDATE) - 95);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Ishita',   'Nair',   DATE '1988-09-14', 'F', '9988776655', 'ishita.nair@gmail.com',    '3 Gandhi Nagar, Vellore',        TRUNC(SYSDATE) - 80);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Kabir',    'Singh',  DATE '1972-12-05', 'M', '9001122334', 'kabir.singh@rediffmail.com','18 Arcot Road, Ranipet',        TRUNC(SYSDATE) - 62);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Meera',    'Pillai', DATE '1983-04-22', 'F', '9445566778', 'meera.pillai@gmail.com',   '9 Bagayam, Vellore',             TRUNC(SYSDATE) - 50);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Arjun',    'Das',    DATE '1999-08-09', 'M', '9556677889', 'arjun.das@gmail.com',      '41 Officers Line, Vellore',      TRUNC(SYSDATE) - 40);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Saanvi',   'Joshi',  DATE '2010-02-17', 'F', '9667788990', NULL,                       '5 Thottapalayam, Vellore',       TRUNC(SYSDATE) - 33);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Aditya',   'Menon',  DATE '1965-06-11', 'M', '9778899001', 'aditya.menon@gmail.com',   '11 Kosapet, Vellore',            TRUNC(SYSDATE) - 30);
INSERT INTO patient VALUES (seq_patient.NEXTVAL, 'Priyanka', 'Rao',    DATE '1992-10-03', 'F', '9889900112', 'priyanka.rao@gmail.com',   '27 Gudiyatham Road, Katpadi',    TRUNC(SYSDATE) - 23);

-- ---------------------------------------------------------------------
-- DOCTOR (10 rows)                                       IDs 1001-1010
-- columns: id, name, specialization, phone, fee, max_daily_appts, status
-- ---------------------------------------------------------------------
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Rajesh Kumar',  'General Physician',  '9840011001',  500, 20, 'ACTIVE');
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Priya Sharma',  'Endocrinologist',    '9840011002',  800, 15, 'ACTIVE');
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Anil Mehta',    'Cardiologist',       '9840011003', 1000, 12, 'ACTIVE');
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Sunita Rao',    'Pathologist',        '9840011004',  600, 20, 'ACTIVE');
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Vikram Singh',  'Nephrologist',       '9840011005',  900, 10, 'ACTIVE');
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Kavita Iyer',   'Gynaecologist',      '9840011006',  700, 15, 'ACTIVE');
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Arjun Nair',    'Orthopaedic Surgeon','9840011007',  750, 10, 'ACTIVE');
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Meera Joshi',   'Dermatologist',      '9840011008',  600, 15, 'ACTIVE');
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Sanjay Gupta',  'ENT Specialist',     '9840011009',  550,  2, 'ACTIVE');
INSERT INTO doctor VALUES (seq_doctor.NEXTVAL, 'Dr. Ramesh Patel',  'General Physician',  '9840011010',  450, 20, 'INACTIVE');

-- ---------------------------------------------------------------------
-- TEST_CATALOG (12 rows)
-- columns: code, name, category, price (INR), unit, normal_min, normal_max, turnaround_hrs
-- ---------------------------------------------------------------------
INSERT INTO test_catalog VALUES ('CBC_HB', 'Haemoglobin',                 'Haematology',   250, 'g/dL',    12,    17,    6);
INSERT INTO test_catalog VALUES ('WBC',    'White Blood Cell Count',      'Haematology',   200, '10^3/uL', 4,     11,    6);
INSERT INTO test_catalog VALUES ('PLT',    'Platelet Count',              'Haematology',   200, '10^3/uL', 150,   450,   6);
INSERT INTO test_catalog VALUES ('FBS',    'Fasting Blood Sugar',         'Biochemistry',  150, 'mg/dL',   70,    100,   4);
INSERT INTO test_catalog VALUES ('HBA1C',  'Glycated Haemoglobin HbA1c',  'Biochemistry',  550, '%',       4,     5.7,   24);
INSERT INTO test_catalog VALUES ('LDL',    'LDL Cholesterol',             'Biochemistry',  400, 'mg/dL',   0,     100,   24);
INSERT INTO test_catalog VALUES ('CREAT',  'Serum Creatinine',            'Biochemistry',  300, 'mg/dL',   0.6,   1.2,   12);
INSERT INTO test_catalog VALUES ('TSH',    'Thyroid Stimulating Hormone', 'Endocrinology', 450, 'mIU/L',   0.4,   4.0,   24);
INSERT INTO test_catalog VALUES ('VITD',   'Vitamin D (25-OH)',           'Endocrinology', 1200,'ng/mL',   30,    100,   48);
INSERT INTO test_catalog VALUES ('B12',    'Vitamin B12',                 'Endocrinology', 900, 'pg/mL',   200,   900,   48);
INSERT INTO test_catalog VALUES ('UPROT',  'Urine Protein',               'Urinalysis',    180, 'mg/dL',   0,     14,    6);
INSERT INTO test_catalog VALUES ('CRP',    'C-Reactive Protein',          'Immunology',    500, 'mg/L',    0,     10,    12);

-- ---------------------------------------------------------------------
-- APPOINTMENT (24 rows)                                IDs 500001-500024
-- Inserted one row at a time in date order: every row passes through
-- trg_no_double_booking. booked_on is set to before the visit.
-- columns: id, patient, doctor, appt_date, slot, reason, status, booked_on
-- ---------------------------------------------------------------------
-- Past visits
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100011, 1005, TRUNC(SYSDATE) - 25, '09:00', 'Routine kidney function review',   'COMPLETED', TRUNC(SYSDATE) - 27); -- 500001
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100012, 1006, TRUNC(SYSDATE) - 22, '15:30', 'Antenatal consultation',           'COMPLETED', TRUNC(SYSDATE) - 23); -- 500002
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100001, 1001, TRUNC(SYSDATE) - 20, '10:00', 'Fatigue and frequent thirst',      'COMPLETED', TRUNC(SYSDATE) - 21); -- 500003
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100002, 1002, TRUNC(SYSDATE) - 18, '10:30', 'Diabetes follow-up',               'COMPLETED', TRUNC(SYSDATE) - 20); -- 500004
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100003, 1003, TRUNC(SYSDATE) - 15, '11:00', 'Chest discomfort on exertion',     'COMPLETED', TRUNC(SYSDATE) - 16); -- 500005
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100009, 1009, TRUNC(SYSDATE) - 14, '12:30', 'Recurring ear infection',          'COMPLETED', TRUNC(SYSDATE) - 15); -- 500006
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100004, 1005, TRUNC(SYSDATE) - 12, '09:30', 'Swelling in feet',                 'COMPLETED', TRUNC(SYSDATE) - 13); -- 500007
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100005, 1001, TRUNC(SYSDATE) - 10, '10:00', 'Fever',                            'CANCELLED', TRUNC(SYSDATE) - 11); -- 500008
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100001, 1002, TRUNC(SYSDATE) - 8,  '12:00', 'Thyroid and sugar review',         'COMPLETED', TRUNC(SYSDATE) - 9);  -- 500009
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100006, 1008, TRUNC(SYSDATE) - 7,  '16:00', 'Skin rash',                        'NO_SHOW',   TRUNC(SYSDATE) - 8);  -- 500010
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100007, 1004, TRUNC(SYSDATE) - 5,  '10:00', 'Recurrent infections, low energy', 'COMPLETED', TRUNC(SYSDATE) - 6);  -- 500011
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100008, 1002, TRUNC(SYSDATE) - 3,  '11:30', 'Weight gain and tiredness',        'COMPLETED', TRUNC(SYSDATE) - 4);  -- 500012
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100009, 1006, TRUNC(SYSDATE) - 2,  '15:00', 'Anaemia check',                    'COMPLETED', TRUNC(SYSDATE) - 3);  -- 500013 (not billed)
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100010, 1001, TRUNC(SYSDATE) - 1,  '10:00', 'Persistent cough and fever',       'COMPLETED', TRUNC(SYSDATE) - 2);  -- 500014 (not billed)
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100002, 1003, TRUNC(SYSDATE) - 1,  '12:00', 'Blood pressure review',            'COMPLETED', TRUNC(SYSDATE) - 3);  -- 500015
-- Today: the 09:00 slot with Dr. Nair is cancelled, then rebooked by another patient
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100004, 1007, TRUNC(SYSDATE),      '09:00', 'Knee pain',                        'CANCELLED', TRUNC(SYSDATE) - 4);  -- 500016
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100006, 1007, TRUNC(SYSDATE),      '09:00', 'Lower back pain',                  'BOOKED',    TRUNC(SYSDATE) - 1);  -- 500017
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100011, 1001, TRUNC(SYSDATE),      '10:00', 'Blood sugar check',                'BOOKED',    TRUNC(SYSDATE) - 2);  -- 500018
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100012, 1001, TRUNC(SYSDATE),      '10:30', 'Headache and dizziness',           'BOOKED',    TRUNC(SYSDATE) - 1);  -- 500019
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100003, 1002, TRUNC(SYSDATE),      '11:00', 'Cholesterol follow-up',            'BOOKED',    TRUNC(SYSDATE) - 5);  -- 500020
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100005, 1009, TRUNC(SYSDATE),      '14:00', 'Sore throat',                      'BOOKED',    TRUNC(SYSDATE) - 1);  -- 500021
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100008, 1009, TRUNC(SYSDATE),      '14:30', 'Sinus congestion',                 'BOOKED',    TRUNC(SYSDATE) - 1);  -- 500022
-- Upcoming
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100006, 1008, TRUNC(SYSDATE) + 2,  '10:00', 'Skin rash (rebooked after no-show)','BOOKED',   TRUNC(SYSDATE));      -- 500023
INSERT INTO appointment VALUES (seq_appointment.NEXTVAL, 100007, 1003, TRUNC(SYSDATE) + 3,  '11:00', 'ECG review',                       'BOOKED',    TRUNC(SYSDATE));      -- 500024

-- ---------------------------------------------------------------------
-- SAMPLE (18 rows)                                     IDs 700001-700018
-- All inserted as COLLECTED; trg_flag_result moves them to COMPLETED
-- when their result is entered below.
-- columns: id, appointment, test, sample_type, collected_on, collected_by, status, remarks
-- ---------------------------------------------------------------------
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500001, 'CREAT',  'BLOOD', TRUNC(SYSDATE) - 25 + 9.5/24,  'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700001
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500003, 'CBC_HB', 'BLOOD', TRUNC(SYSDATE) - 20 + 10.5/24, 'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700002
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500003, 'FBS',    'BLOOD', TRUNC(SYSDATE) - 20 + 10.5/24, 'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700003
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500004, 'FBS',    'BLOOD', TRUNC(SYSDATE) - 18 + 11/24,   'Ravi (Tech)',    'COLLECTED', NULL); -- 700004
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500004, 'HBA1C',  'BLOOD', TRUNC(SYSDATE) - 18 + 11/24,   'Ravi (Tech)',    'COLLECTED', NULL); -- 700005
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500005, 'LDL',    'BLOOD', TRUNC(SYSDATE) - 15 + 11.5/24, 'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700006
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500005, 'CRP',    'BLOOD', TRUNC(SYSDATE) - 15 + 11.5/24, 'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700007
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500007, 'CREAT',  'BLOOD', TRUNC(SYSDATE) - 12 + 10/24,   'Ravi (Tech)',    'COLLECTED', NULL); -- 700008
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500007, 'UPROT',  'URINE', TRUNC(SYSDATE) - 12 + 10/24,   'Ravi (Tech)',    'COLLECTED', NULL); -- 700009
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500009, 'HBA1C',  'BLOOD', TRUNC(SYSDATE) - 8 + 12.5/24,  'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700010
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500009, 'TSH',    'BLOOD', TRUNC(SYSDATE) - 8 + 12.5/24,  'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700011
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500011, 'WBC',    'BLOOD', TRUNC(SYSDATE) - 5 + 10.5/24,  'Ravi (Tech)',    'COLLECTED', NULL); -- 700012
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500011, 'PLT',    'BLOOD', TRUNC(SYSDATE) - 5 + 10.5/24,  'Ravi (Tech)',    'COLLECTED', NULL); -- 700013
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500012, 'TSH',    'BLOOD', TRUNC(SYSDATE) - 3 + 12/24,    'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700014
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500012, 'VITD',   'BLOOD', TRUNC(SYSDATE) - 3 + 12/24,    'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700015
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500013, 'CBC_HB', 'BLOOD', TRUNC(SYSDATE) - 2 + 15.5/24,  'Ravi (Tech)',    'COLLECTED', NULL); -- 700016
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500014, 'FBS',    'BLOOD', TRUNC(SYSDATE) - 1 + 10.5/24,  'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700017
INSERT INTO sample VALUES (seq_sample.NEXTVAL, 500014, 'CRP',    'BLOOD', TRUNC(SYSDATE) - 1 + 10.5/24,  'Lakshmi (Tech)', 'COLLECTED', NULL); -- 700018

-- Sample 700017 has gone to the analyser but no result yet (overdue: FBS turnaround is 4 h)
UPDATE sample SET status = 'PROCESSING' WHERE sample_id = 700017;

-- ---------------------------------------------------------------------
-- TEST_RESULT (16 rows)                                IDs 800001-800016
-- result_flag is NOT supplied: trg_flag_result sets it from the
-- test's normal range and marks the sample COMPLETED.
-- ---------------------------------------------------------------------
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700001, 1.0,  TRUNC(SYSDATE) - 25 + 20/24, 1004, NULL);                             -- NORMAL
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700002, 13.5, TRUNC(SYSDATE) - 20 + 16/24, 1004, NULL);                             -- NORMAL
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700003, 128,  TRUNC(SYSDATE) - 20 + 14/24, 1004, 'Suggest HbA1c');                  -- HIGH
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700004, 142,  TRUNC(SYSDATE) - 18 + 15/24, 1004, NULL);                             -- HIGH
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700005, 7.2,  TRUNC(SYSDATE) - 17 + 10/24, 1002, 'Poor glycaemic control');         -- HIGH
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700006, 165,  TRUNC(SYSDATE) - 14 + 10/24, 1004, NULL);                             -- HIGH
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700007, 4,    TRUNC(SYSDATE) - 15 + 22/24, 1004, NULL);                             -- NORMAL
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700008, 1.9,  TRUNC(SYSDATE) - 12 + 20/24, 1004, 'Refer nephrology follow-up');     -- HIGH
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700009, 30,   TRUNC(SYSDATE) - 12 + 15/24, 1004, NULL);                             -- HIGH
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700010, 6.4,  TRUNC(SYSDATE) - 7 + 11/24,  1002, NULL);                             -- HIGH
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700011, 0.2,  TRUNC(SYSDATE) - 7 + 11/24,  1002, 'Possible hyperthyroidism');       -- LOW
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700012, 3.1,  TRUNC(SYSDATE) - 5 + 15/24,  1004, NULL);                             -- LOW
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700013, 95,   TRUNC(SYSDATE) - 5 + 15/24,  1004, NULL);                             -- LOW (sample rejected below)
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700014, 6.8,  TRUNC(SYSDATE) - 2 + 11/24,  1002, NULL);                             -- HIGH
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700015, 18,   TRUNC(SYSDATE) - 1 + 12/24,  1002, 'Start supplementation');         -- LOW
INSERT INTO test_result (result_id, sample_id, result_value, result_date, verified_by, remarks) VALUES (seq_test_result.NEXTVAL, 700016, 10.2, TRUNC(SYSDATE) - 2 + 21/24,  1004, NULL);                             -- LOW

-- Pathologist finds platelet clumping on the smear: sample 700013 is rejected,
-- so its result cannot be trusted and it is excluded from billing.
UPDATE sample
   SET status = 'REJECTED', remarks = 'Platelet clumping on smear; recollect'
 WHERE sample_id = 700013;

-- ---------------------------------------------------------------------
-- BILL (11 rows)                                       IDs 900001-900011
-- Snapshot amounts = doctor fee + SUM(price of non-REJECTED samples),
-- less discount (ck_bill_total_amt verifies the arithmetic).
-- Bills start UNPAID; payments are then applied with UPDATE so that
-- trg_payment_status sets PARTIAL / PAID.
-- columns: id, appointment, bill_date, consult, tests, disc%, total, paid, status, mode
-- ---------------------------------------------------------------------
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500001, TRUNC(SYSDATE) - 25,  900,  300,  0, 1200.00, 0, 'UNPAID', NULL); -- 900001
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500002, TRUNC(SYSDATE) - 22,  700,    0,  0,  700.00, 0, 'UNPAID', NULL); -- 900002
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500003, TRUNC(SYSDATE) - 20,  500,  400, 10,  810.00, 0, 'UNPAID', NULL); -- 900003
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500004, TRUNC(SYSDATE) - 18,  800,  700,  0, 1500.00, 0, 'UNPAID', NULL); -- 900004
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500005, TRUNC(SYSDATE) - 15, 1000,  900,  0, 1900.00, 0, 'UNPAID', NULL); -- 900005
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500006, TRUNC(SYSDATE) - 14,  550,    0,  0,  550.00, 0, 'UNPAID', NULL); -- 900006
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500007, TRUNC(SYSDATE) - 12,  900,  480,  5, 1311.00, 0, 'UNPAID', NULL); -- 900007
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500009, TRUNC(SYSDATE) - 8,   800, 1000,  0, 1800.00, 0, 'UNPAID', NULL); -- 900008
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500011, TRUNC(SYSDATE) - 5,   600,  200,  0,  800.00, 0, 'UNPAID', NULL); -- 900009 (PLT rejected, not charged)
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500012, TRUNC(SYSDATE) - 3,   800, 1650,  0, 2450.00, 0, 'UNPAID', NULL); -- 900010
INSERT INTO bill VALUES (seq_bill.NEXTVAL, 500015, TRUNC(SYSDATE) - 1,  1000,    0, 20,  800.00, 0, 'UNPAID', NULL); -- 900011

-- Payments (each UPDATE fires trg_payment_status)
UPDATE bill SET amount_paid = 1200, payment_mode = 'CARD'      WHERE bill_id = 900001; -- PAID
UPDATE bill SET amount_paid = 700,  payment_mode = 'CASH'      WHERE bill_id = 900002; -- PAID
UPDATE bill SET amount_paid = 810,  payment_mode = 'UPI'       WHERE bill_id = 900003; -- PAID
UPDATE bill SET amount_paid = 1000, payment_mode = 'CASH'      WHERE bill_id = 900004; -- PARTIAL
UPDATE bill SET amount_paid = 550,  payment_mode = 'INSURANCE' WHERE bill_id = 900006; -- PAID
UPDATE bill SET amount_paid = 1311, payment_mode = 'CARD'      WHERE bill_id = 900007; -- PAID
UPDATE bill SET amount_paid = 500,  payment_mode = 'UPI'       WHERE bill_id = 900008; -- PARTIAL
UPDATE bill SET amount_paid = 2450, payment_mode = 'UPI'       WHERE bill_id = 900010; -- PAID
UPDATE bill SET amount_paid = 800,  payment_mode = 'CARD'      WHERE bill_id = 900011; -- PAID
-- 900005 and 900009 stay UNPAID

COMMIT;
