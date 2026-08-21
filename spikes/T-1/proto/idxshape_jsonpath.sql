\set ON_ERROR_STOP 0
DROP INDEX IF EXISTS h2a; DROP INDEX IF EXISTS idxprobe_score_operand; DROP INDEX IF EXISTS idxprobe_d1_const;
DROP INDEX IF EXISTS idxprobe_actor_txt; DROP INDEX IF EXISTS idxprobe_due_txt; DROP INDEX IF EXISTS idxprobe_status_txt;
DROP INDEX IF EXISTS idxprobe_score_f8; DROP INDEX IF EXISTS idxprobe_ecma;
CREATE INDEX idxprobe_data_gin_path ON idxprobe USING GIN (data jsonb_path_ops);
ANALYZE idxprobe;
\echo '=== J0  CONTROL: the index doing the job it was built for (list_records_where) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT data FROM idxprobe
 WHERE collection='LedgerRecord' AND data @> '{"actor":"goms"}'::jsonb;
\echo '=== J1  key-existence, which jsonb_path_ops deliberately does not support ==='
SET enable_seqscan=off;
EXPLAIN (COSTS OFF) SELECT data FROM idxprobe WHERE collection='LedgerRecord' AND data ? 'revision';
SET enable_seqscan=on;
\echo '=== J2  jsonpath RANGE over an arbitrary key, via @?  (jsonb_path_ops DOES carry @?) ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT data FROM idxprobe
 WHERE collection='Submission' AND data @? '$.score ? (@ > 90)';
\echo '=== J3  jsonpath EQUALITY via @@ ==='
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT data FROM idxprobe
 WHERE collection='Submission' AND data @@ '$.status == "open"';
\echo '=== J4  swap to jsonb_ops and repeat J1/J2 ==='
DROP INDEX idxprobe_data_gin_path;
CREATE INDEX idxprobe_data_gin_default ON idxprobe USING GIN (data jsonb_ops);
ANALYZE idxprobe;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT data FROM idxprobe WHERE collection='LedgerRecord' AND data ? 'revision';
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT data FROM idxprobe WHERE collection='Submission' AND data @? '$.score ? (@ > 90)';
\echo '=== J5  do the jsonpath forms AGREE with the compiled expr predicate? ==='
SELECT (SELECT count(*) FROM idxprobe WHERE collection='Submission' AND data @? '$.score ? (@ > 90)') AS jsonpath_gt90,
       (SELECT count(*) FROM idxprobe WHERE collection='Submission'
          AND xpr.truthy(to_jsonb(xpr.ord('>'::text, nullif((data->'score'::text),'null'::jsonb), to_jsonb(90.0::float8))))) AS compiled_gt90,
       (SELECT count(*) FROM idxprobe WHERE collection='Submission' AND data @@ '$.status == "open"') AS jsonpath_status_open,
       (SELECT count(*) FROM idxprobe WHERE collection='Submission'
          AND xpr.truthy(to_jsonb(nullif((data->'status'::text),'null'::jsonb) IS NOT DISTINCT FROM to_jsonb('open'::text)))) AS compiled_status_open;
DROP INDEX idxprobe_data_gin_default;
