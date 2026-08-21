\set ON_ERROR_STOP 0
\echo '=== I1  is xpr.ecma_num actually immutable?  (it is DECLARED IMMUTABLE) ==='
SET extra_float_digits = 1;    -- the PG12+ default
SELECT current_setting('extra_float_digits') AS efd, xpr.ecma_num(0.1::float8 + 0.2::float8) AS ecma_num_out;
SET extra_float_digits = -3;
SELECT current_setting('extra_float_digits') AS efd, xpr.ecma_num(0.1::float8 + 0.2::float8) AS ecma_num_out;
RESET extra_float_digits;

\echo '=== I2  the same value reached through the REAL language:  string($.score) ==='
\echo '     compiled form of string($.score) is xpr.ecma_num(xpr.f8(...)) -- fixture case string($.n)'
DELETE FROM idxprobe WHERE key='SUB-EFD';
INSERT INTO idxprobe VALUES ('Submission','SUB-EFD','{"score":0.30000000000000004,"status":"open"}');

\echo '=== I3  build the index at the default GUC, then change the GUC ==='
DROP INDEX IF EXISTS idxprobe_ecma;
SET extra_float_digits = 1;
CREATE INDEX idxprobe_ecma ON idxprobe ((xpr.ecma_num(xpr.f8(data -> 'score'))));
ANALYZE idxprobe;
SET extra_float_digits = -3;
\echo '--- I3a  SAME query, planner free to use the index:'
EXPLAIN (COSTS OFF) SELECT count(*) FROM idxprobe WHERE xpr.ecma_num(xpr.f8(data -> 'score')) = '0.3';
SELECT count(*) AS answer_with_index FROM idxprobe WHERE xpr.ecma_num(xpr.f8(data -> 'score')) = '0.3';
\echo '--- I3b  SAME query, index access disabled -> the honest answer:'
SET enable_indexscan = off; SET enable_bitmapscan = off; SET enable_indexonlyscan = off;
EXPLAIN (COSTS OFF) SELECT count(*) FROM idxprobe WHERE xpr.ecma_num(xpr.f8(data -> 'score')) = '0.3';
SELECT count(*) AS answer_without_index FROM idxprobe WHERE xpr.ecma_num(xpr.f8(data -> 'score')) = '0.3';
RESET enable_indexscan; RESET enable_bitmapscan; RESET enable_indexonlyscan; RESET extra_float_digits;

\echo '=== I4  do the other IMMUTABLE-declared xpr date functions actually vary? ==='
SET TimeZone = 'UTC';
SELECT current_setting('TimeZone') AS tz, xpr.pdate_ms('"2026-07-02"'::jsonb) AS pdate_ms,
       xpr.fmt_date_ms(1751414400000, true) AS fmt_date;
SET TimeZone = 'Pacific/Kiritimati';
SELECT current_setting('TimeZone') AS tz, xpr.pdate_ms('"2026-07-02"'::jsonb) AS pdate_ms,
       xpr.fmt_date_ms(1751414400000, true) AS fmt_date;
SET lc_time = 'C';
SELECT current_setting('lc_time') AS lc, xpr.fmt_date_ms(1751414400000, false) AS fmt_dt;
RESET TimeZone; RESET lc_time;

\echo '=== I5  cleanup ==='
DELETE FROM idxprobe WHERE key='SUB-EFD';
DROP INDEX IF EXISTS idxprobe_ecma;
