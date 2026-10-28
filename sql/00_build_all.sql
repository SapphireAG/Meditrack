-- =====================================================================
-- MediTrack : 00_build_all.sql
-- Builds the whole database from scratch in SQL*Plus / SQLcl:
--     cd sql
--     sqlplus meditrack/<password>@localhost/FREEPDB1 @00_build_all.sql
-- (In SQL Developer: open this file and press F5 "Run Script".)
--
-- Order matters: triggers are created BEFORE the seed data so every
-- seed row passes through them (flags and payment statuses are set by
-- the triggers, not typed by hand).
-- =====================================================================
SET SERVEROUTPUT ON
SET DEFINE OFF

PROMPT ==== Dropping old objects ====
@@99_drop_all.sql
PROMPT ==== Creating tables, constraints, sequences ====
@@01_ddl.sql
PROMPT ==== Creating functions ====
@@04_functions.sql
PROMPT ==== Creating procedures ====
@@05_procedures.sql
PROMPT ==== Creating triggers ====
@@06_triggers.sql
PROMPT ==== Loading seed data ====
@@02_seed_data.sql
PROMPT ==== Creating view and running the 15 queries ====
@@03_queries.sql
PROMPT ==== Build complete. Run 07_dml_demo.sql to walk through T1-T7 ====
