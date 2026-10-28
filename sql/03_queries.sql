-- =====================================================================
-- MediTrack : 03_queries.sql
-- 15 queries, each tied to a functional requirement (FR1-FR12, see
-- README "Functional requirements") and to a SQL concept.
--
-- Header format (the Python app reads these headers to build its
-- Reports menu, so keep the "-- Qn." line and the field names):
--   -- Qn. <title>
--   -- Purpose : what the clinic uses it for
--   -- FR      : requirement served
--   -- Concept : SQL feature demonstrated
--   -- Output  : columns returned
-- =====================================================================
SET DEFINE OFF

-- ---------------------------------------------------------------------
-- Q1. Today's schedule per doctor
-- Purpose : Front desk prints each doctor's list of patients for today
-- FR      : FR3
-- Concept : INNER JOIN across 3 tables, WHERE filter, ORDER BY
-- Output  : doctor | slot | patient | phone | reason | status
-- ---------------------------------------------------------------------
SELECT d.full_name                        AS doctor,
       a.slot_time                        AS slot,
       p.first_name || ' ' || p.last_name AS patient,
       p.phone,
       a.reason,
       a.status
  FROM appointment a
  JOIN patient p ON p.patient_id = a.patient_id
  JOIN doctor  d ON d.doctor_id  = a.doctor_id
 WHERE a.appt_date = TRUNC(SYSDATE)
 ORDER BY d.full_name, a.slot_time;

-- ---------------------------------------------------------------------
-- Q2. Pending samples older than their test's turnaround time
-- Purpose : Lab supervisor chases samples that are overdue
-- FR      : FR8
-- Concept : JOIN, date arithmetic (hours -> days), multi-condition WHERE
-- Output  : sample | test | patient | collected_on | due_by | hours_overdue | status
-- ---------------------------------------------------------------------
SELECT s.sample_id,
       tc.test_name,
       p.first_name || ' ' || p.last_name                      AS patient,
       TO_CHAR(s.collected_on, 'DD-MON HH24:MI')               AS collected_on,
       TO_CHAR(s.collected_on + tc.turnaround_hrs / 24, 'DD-MON HH24:MI') AS due_by,
       ROUND((SYSDATE - (s.collected_on + tc.turnaround_hrs / 24)) * 24, 1) AS hours_overdue,
       s.status
  FROM sample s
  JOIN test_catalog tc ON tc.test_code     = s.test_code
  JOIN appointment  a  ON a.appointment_id = s.appointment_id
  JOIN patient      p  ON p.patient_id     = a.patient_id
 WHERE s.status IN ('COLLECTED', 'PROCESSING')
   AND s.collected_on + tc.turnaround_hrs / 24 < SYSDATE
 ORDER BY hours_overdue DESC;

-- ---------------------------------------------------------------------
-- Q3. All abnormal (LOW / HIGH) results with patient and test names
-- Purpose : Doctors review results that need attention
-- FR      : FR7
-- Concept : 5-table INNER JOIN, IN list filter
-- Output  : patient | test | value | unit | normal range | flag | verified_by
-- ---------------------------------------------------------------------
SELECT p.first_name || ' ' || p.last_name           AS patient,
       tc.test_name,
       r.result_value,
       tc.unit,
       RTRIM(TO_CHAR(tc.normal_min, 'FM99990.99'), '.') || ' - ' ||
       RTRIM(TO_CHAR(tc.normal_max, 'FM99990.99'), '.') AS normal_range,
       r.result_flag,
       d.full_name                                  AS verified_by
  FROM test_result  r
  JOIN sample       s  ON s.sample_id      = r.sample_id
  JOIN test_catalog tc ON tc.test_code     = s.test_code
  JOIN appointment  a  ON a.appointment_id = s.appointment_id
  JOIN patient      p  ON p.patient_id     = a.patient_id
  LEFT JOIN doctor  d  ON d.doctor_id      = r.verified_by
 WHERE r.result_flag IN ('LOW', 'HIGH')
   AND s.status <> 'REJECTED'
 ORDER BY p.last_name, tc.test_name;

-- ---------------------------------------------------------------------
-- Q4. Revenue collected by day and by payment mode
-- Purpose : Accounts reconciles the cash drawer, card machine and UPI
-- FR      : FR12
-- Concept : GROUP BY on two columns, SUM / COUNT aggregates
-- Output  : bill_date | payment_mode | bills | billed | collected
-- ---------------------------------------------------------------------
SELECT TO_CHAR(b.bill_date, 'YYYY-MM-DD')  AS bill_date,
       NVL(b.payment_mode, 'NOT PAID')    AS payment_mode,
       COUNT(*)                           AS bills,
       SUM(b.total_amt)                   AS billed,
       SUM(b.amount_paid)                 AS collected
  FROM bill b
 GROUP BY TO_CHAR(b.bill_date, 'YYYY-MM-DD'), NVL(b.payment_mode, 'NOT PAID')
 ORDER BY bill_date, payment_mode;

-- ---------------------------------------------------------------------
-- Q5. Doctors with more than 2 appointments in the last 30 days
-- Purpose : Management sees which doctors carry the most load
-- FR      : FR12
-- Concept : GROUP BY + HAVING
-- Output  : doctor | specialization | appointments
-- ---------------------------------------------------------------------
SELECT d.full_name       AS doctor,
       d.specialization,
       COUNT(*)          AS appointments
  FROM appointment a
  JOIN doctor d ON d.doctor_id = a.doctor_id
 WHERE a.appt_date >= TRUNC(SYSDATE) - 30
   AND a.status <> 'CANCELLED'
 GROUP BY d.full_name, d.specialization
HAVING COUNT(*) > 2
 ORDER BY appointments DESC;

-- ---------------------------------------------------------------------
-- Q6. Patients whose outstanding dues are above the average due
-- Purpose : Billing follows up the largest unpaid balances first
-- FR      : FR10
-- Concept : Non-correlated subquery in HAVING (average of per-patient dues)
-- Output  : patient_id | patient | phone | total_due
-- ---------------------------------------------------------------------
SELECT p.patient_id,
       p.first_name || ' ' || p.last_name   AS patient,
       p.phone,
       SUM(b.total_amt - b.amount_paid)     AS total_due
  FROM patient p
  JOIN appointment a ON a.patient_id     = p.patient_id
  JOIN bill        b ON b.appointment_id = a.appointment_id
 GROUP BY p.patient_id, p.first_name, p.last_name, p.phone
HAVING SUM(b.total_amt - b.amount_paid) >
       (SELECT AVG(patient_due)
          FROM (SELECT SUM(b2.total_amt - b2.amount_paid) AS patient_due
                  FROM bill b2
                  JOIN appointment a2 ON a2.appointment_id = b2.appointment_id
                 GROUP BY a2.patient_id))
 ORDER BY total_due DESC;

-- ---------------------------------------------------------------------
-- Q7. Tests in the catalogue that have never been ordered
-- Purpose : Lab manager reviews unused tests (reagents, pricing)
-- FR      : FR5
-- Concept : NOT EXISTS with a correlated subquery
-- Output  : test_code | test_name | category | price
-- ---------------------------------------------------------------------
SELECT tc.test_code, tc.test_name, tc.category, tc.price
  FROM test_catalog tc
 WHERE NOT EXISTS (SELECT 1
                     FROM sample s
                    WHERE s.test_code = tc.test_code);

-- ---------------------------------------------------------------------
-- Q8. Most-ordered test in each category
-- Purpose : Lab plans stock and staffing around its busiest tests
-- FR      : FR12
-- Concept : Window function RANK() OVER (PARTITION BY ... ORDER BY ...)
-- Output  : category | test_name | times_ordered | rank_in_category
-- ---------------------------------------------------------------------
SELECT category, test_name, times_ordered, rank_in_category
  FROM (SELECT tc.category,
               tc.test_name,
               COUNT(s.sample_id) AS times_ordered,
               RANK() OVER (PARTITION BY tc.category
                            ORDER BY COUNT(s.sample_id) DESC) AS rank_in_category
          FROM test_catalog tc
          LEFT JOIN sample s ON s.test_code = tc.test_code
         GROUP BY tc.category, tc.test_name)
 WHERE rank_in_category = 1
 ORDER BY times_ordered DESC, category;

-- ---------------------------------------------------------------------
-- Q9. Patients who have consulted more than one doctor (completed visits)
-- Purpose : Doctors see patients under multiple specialists
-- FR      : FR3
-- Concept : COUNT(DISTINCT ...) with HAVING, LISTAGG
-- Output  : patient | doctors_seen | doctor_names
-- ---------------------------------------------------------------------
SELECT p.first_name || ' ' || p.last_name             AS patient,
       COUNT(DISTINCT a.doctor_id)                    AS doctors_seen,
       LISTAGG(DISTINCT d.full_name, ', ')
           WITHIN GROUP (ORDER BY d.full_name)        AS doctor_names
  FROM patient p
  JOIN appointment a ON a.patient_id = p.patient_id
  JOIN doctor      d ON d.doctor_id  = a.doctor_id
 WHERE a.status = 'COMPLETED'
 GROUP BY p.patient_id, p.first_name, p.last_name
HAVING COUNT(DISTINCT a.doctor_id) > 1
 ORDER BY doctors_seen DESC, patient;

-- ---------------------------------------------------------------------
-- Q10. Completed appointments that have not been billed
-- Purpose : Billing finds visits that would otherwise be missed
--           (this is exactly the set end_of_day_billing will pick up)
-- FR      : FR9, FR11
-- Concept : LEFT OUTER JOIN ... WHERE right side IS NULL (anti-join)
-- Output  : appointment_id | appt_date | patient | doctor
-- ---------------------------------------------------------------------
SELECT a.appointment_id,
       TO_CHAR(a.appt_date, 'DD-MON-YYYY')  AS appt_date,
       p.first_name || ' ' || p.last_name   AS patient,
       d.full_name                          AS doctor
  FROM appointment a
  JOIN patient p   ON p.patient_id     = a.patient_id
  JOIN doctor  d   ON d.doctor_id      = a.doctor_id
  LEFT JOIN bill b ON b.appointment_id = a.appointment_id
 WHERE a.status = 'COMPLETED'
   AND b.bill_id IS NULL
 ORDER BY a.appt_date;

-- ---------------------------------------------------------------------
-- Q11. Average result value per test compared with its normal range
-- Purpose : Pathologist spots tests where the population runs high/low
-- FR      : FR7
-- Concept : AVG / MIN / MAX aggregates, CASE expression
-- Output  : test_name | results | avg_value | normal_min | normal_max | avg_position
-- ---------------------------------------------------------------------
SELECT tc.test_name,
       COUNT(*)                   AS results,
       ROUND(AVG(r.result_value), 2) AS avg_value,
       MIN(r.result_value)        AS min_value,
       MAX(r.result_value)        AS max_value,
       tc.normal_min,
       tc.normal_max,
       CASE
           WHEN AVG(r.result_value) < tc.normal_min THEN 'BELOW RANGE'
           WHEN AVG(r.result_value) > tc.normal_max THEN 'ABOVE RANGE'
           ELSE 'WITHIN RANGE'
       END                        AS avg_position
  FROM test_result r
  JOIN sample       s  ON s.sample_id  = r.sample_id
  JOIN test_catalog tc ON tc.test_code = s.test_code
 WHERE s.status <> 'REJECTED'
 GROUP BY tc.test_name, tc.normal_min, tc.normal_max
 ORDER BY tc.test_name;

-- ---------------------------------------------------------------------
-- Q12. Each doctor's share of total billed revenue
-- Purpose : Management compares revenue contribution per doctor
-- FR      : FR12
-- Concept : Scalar subquery in SELECT for the grand total, percentage
-- Output  : doctor | bills | revenue | pct_of_total
-- ---------------------------------------------------------------------
SELECT d.full_name                     AS doctor,
       COUNT(b.bill_id)                AS bills,
       SUM(b.total_amt)                AS revenue,
       ROUND(100 * SUM(b.total_amt) / (SELECT SUM(total_amt) FROM bill), 1) AS pct_of_total
  FROM bill b
  JOIN appointment a ON a.appointment_id = b.appointment_id
  JOIN doctor      d ON d.doctor_id      = a.doctor_id
 GROUP BY d.full_name
 ORDER BY revenue DESC;

-- ---------------------------------------------------------------------
-- Q13. Patients with both a HIGH and a LOW result
-- Purpose : Flags patients with mixed abnormalities for a full review
-- FR      : FR7
-- Concept : Set operator INTERSECT
-- Output  : patient_id | patient
-- ---------------------------------------------------------------------
SELECT p.patient_id, p.first_name || ' ' || p.last_name AS patient
  FROM patient p
  JOIN appointment a ON a.patient_id     = p.patient_id
  JOIN sample      s ON s.appointment_id = a.appointment_id
  JOIN test_result r ON r.sample_id      = s.sample_id
 WHERE r.result_flag = 'HIGH'
INTERSECT
SELECT p.patient_id, p.first_name || ' ' || p.last_name AS patient
  FROM patient p
  JOIN appointment a ON a.patient_id     = p.patient_id
  JOIN sample      s ON s.appointment_id = a.appointment_id
  JOIN test_result r ON r.sample_id      = s.sample_id
 WHERE r.result_flag = 'LOW'
 ORDER BY 1;

-- ---------------------------------------------------------------------
-- Q14. New patient registrations per month
-- Purpose : Management tracks growth of the clinic's patient base
-- FR      : FR1, FR12
-- Concept : GROUP BY on a derived value (TO_CHAR month), COUNT
-- Output  : month | new_patients
-- ---------------------------------------------------------------------
SELECT TO_CHAR(registered_on, 'YYYY-MM') AS month,
       COUNT(*)                          AS new_patients
  FROM patient
 GROUP BY TO_CHAR(registered_on, 'YYYY-MM')
 ORDER BY month;

-- ---------------------------------------------------------------------
-- Q15. View v_bill_summary : one readable line per bill
-- Purpose : Billing desk and reports read bills without writing joins
-- FR      : FR9, FR10
-- Concept : CREATE VIEW over a 4-table join; querying the view
-- Output  : bill_id | bill_date | patient | doctor | total | paid | balance | status | mode
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_bill_summary AS
SELECT b.bill_id,
       b.bill_date,
       a.appointment_id,
       p.patient_id,
       p.first_name || ' ' || p.last_name AS patient,
       d.full_name                        AS doctor,
       b.consultation_amt,
       b.test_amt,
       b.discount_pct,
       b.total_amt,
       b.amount_paid,
       b.total_amt - b.amount_paid        AS balance,
       b.payment_status,
       b.payment_mode
  FROM bill b
  JOIN appointment a ON a.appointment_id = b.appointment_id
  JOIN patient     p ON p.patient_id     = a.patient_id
  JOIN doctor      d ON d.doctor_id      = a.doctor_id;

SELECT bill_id,
       TO_CHAR(bill_date, 'DD-MON-YYYY') AS bill_date,
       patient,
       doctor,
       total_amt,
       amount_paid,
       balance,
       payment_status,
       payment_mode
  FROM v_bill_summary
 ORDER BY bill_id;
