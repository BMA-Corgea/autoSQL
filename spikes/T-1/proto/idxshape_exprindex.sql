\set ON_ERROR_STOP 0
\timing off
\echo '### T1  catalog: which operators each jsonb GIN opclass family actually supports'
SELECT opc.opcname, amop.amopopr::regoperator AS operator
FROM pg_opclass opc
JOIN pg_am am ON am.oid = opc.opcmethod
JOIN pg_amop amop ON amop.amopfamily = opc.opcfamily
WHERE opc.opcname IN ('jsonb_path_ops','jsonb_ops') AND am.amname='gin'
ORDER BY opc.opcname, amop.amopstrategy;

\echo '### T2  catalog: volatility of the builtins the xpr functions call inside IMMUTABLE bodies'
SELECT p.oid::regprocedure AS fn,
       CASE p.provolatile WHEN 'i' THEN 'IMMUTABLE' WHEN 's' THEN 'STABLE' ELSE 'VOLATILE' END AS volatility
FROM pg_proc p
WHERE p.oid::regprocedure::text IN (
  'to_char(timestamp without time zone,text)',
  'to_char(timestamp with time zone,text)',
  'date_part(text,timestamp with time zone)',
  'date_part(text,timestamp without time zone)',
  'timezone(text,timestamp without time zone)',
  'make_timestamp(integer,integer,integer,integer,integer,double precision)',
  'float8out(double precision)',
  'now()')
ORDER BY 1;

\echo '### T3  hand-written vs compiled, on the SAME btree expression index'
DROP INDEX IF EXISTS idxprobe_score_f8;
CREATE INDEX idxprobe_score_f8 ON idxprobe (((data->>'score')::float8));
ANALYZE idxprobe;
\echo '--- T3a  HAND-WRITTEN predicate  (data->>''score'')::float8 > 90'
EXPLAIN (ANALYZE, BUFFERS) SELECT data FROM idxprobe
 WHERE collection='Submission' AND (data->>'score')::float8 > 90;
\echo '--- T3b  COMPILED predicate for the identical expression  $.score > 90'
EXPLAIN (ANALYZE, BUFFERS) SELECT data FROM idxprobe
 WHERE collection='Submission'
   AND xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb), to_jsonb((90.0)::float8))));
\echo '--- T3c  T3b again with enable_seqscan=off (absence of strategy vs cost choice)'
SET enable_seqscan = off;
EXPLAIN (COSTS OFF) SELECT data FROM idxprobe
 WHERE collection='Submission'
   AND xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb), to_jsonb((90.0)::float8))));
SET enable_seqscan = on;

\echo '### T4  expression index on the EXACT compiled operand (jsonb btree)'
CREATE INDEX idxprobe_score_operand ON idxprobe ((nullif((data -> 'score'::text), 'null'::jsonb)));
ANALYZE idxprobe;
\echo '--- T4a  compiled W2 predicate against it'
SET enable_seqscan = off;
EXPLAIN (COSTS OFF) SELECT data FROM idxprobe
 WHERE collection='Submission'
   AND xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb), to_jsonb((90.0)::float8))));
\echo '--- T4b  compiled SORT key S1 against it: ORDER BY nullif(data->''score'',''null'') DESC LIMIT 50'
EXPLAIN (ANALYZE, BUFFERS) SELECT data FROM idxprobe
 WHERE collection='Submission'
 ORDER BY nullif((data -> ('score')::text), 'null'::jsonb) DESC NULLS LAST LIMIT 50;
SET enable_seqscan = on;

\echo '### T5  full-predicate BOOLEAN expression index reproducing the compiled W2 verbatim'
CREATE INDEX idxprobe_w2_bool ON idxprobe ((xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb), to_jsonb((90.0)::float8))))));
ANALYZE idxprobe;
EXPLAIN (ANALYZE, BUFFERS) SELECT data FROM idxprobe
 WHERE collection='Submission'
   AND xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb), to_jsonb((90.0)::float8))));

\echo '### T6  PARTIAL index whose predicate is the compiled W2 verbatim'
CREATE INDEX idxprobe_w2_partial ON idxprobe (collection, key)
  WHERE xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb), to_jsonb((90.0)::float8))));
ANALYZE idxprobe;
EXPLAIN (ANALYZE, BUFFERS) SELECT data FROM idxprobe
 WHERE collection='Submission'
   AND xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb), to_jsonb((90.0)::float8))));
\echo '--- T6b  the SAME partial index against a DIFFERENT threshold (95, not 90)'
EXPLAIN (COSTS OFF) SELECT data FROM idxprobe
 WHERE collection='Submission'
   AND xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> ('score')::text), 'null'::jsonb), to_jsonb((95.0)::float8))));

\echo '### T7  IMMUTABLE claims: what can and cannot be indexed'
\echo '--- T7a  xpr.ecma_num  (declared IMMUTABLE, reads extra_float_digits) -- index creatable?'
CREATE INDEX idxprobe_ecma ON idxprobe ((xpr.ecma_num(xpr.f8(data -> 'score'))));
\echo '--- T7b  xpr.now_ms  (declared STABLE) -- index creatable?'
CREATE INDEX idxprobe_nowms ON idxprobe ((xpr.now_ms('{}'::jsonb)));
\echo '--- T7c  the compiled DERIVE column D1 (days_left) -- index creatable?'
CREATE INDEX idxprobe_d1 ON idxprobe ((to_jsonb((xpr.pdate_ms(nullif((data -> ('due_date')::text), 'null'::jsonb)) - xpr.pdate_ms(to_jsonb(xpr.fmt_date_ms(xpr.now_ms(('{"now": "2026-08-19T12:00:00Z"}'::jsonb)::jsonb), true)))) / 86400000.0::float8)));
\echo '--- T7d  the same D1 with the clock term hoisted to a constant -- index creatable?'
CREATE INDEX idxprobe_d1_const ON idxprobe ((xpr.pdate_ms(nullif((data -> ('due_date')::text), 'null'::jsonb))));
\d+ idxprobe
