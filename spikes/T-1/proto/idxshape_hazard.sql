\set ON_ERROR_STOP 0
\echo '### H1  volatility of the builtins compile.py itself emits'
SELECT p.oid::regprocedure AS fn,
       CASE p.provolatile WHEN 'i' THEN 'IMMUTABLE' WHEN 's' THEN 'STABLE' ELSE 'VOLATILE' END AS volatility
FROM pg_proc p
WHERE p.oid::regprocedure::text IN ('to_jsonb(anyelement)','jsonb_typeof(jsonb)',
      'jsonb_build_array(VARIADIC "any")','lower(text)','upper(text)','nullif(anyelement,anyelement)')
ORDER BY 1;

\echo '### H2  isolate WHICH function blocks the index: xpr-only vs to_jsonb-wrapped'
\echo '-- H2a xpr.ord alone (all-IMMUTABLE), no to_jsonb wrapper:'
CREATE INDEX h2a ON idxprobe ((xpr.ord(('>')::text, nullif((data -> 'score'::text), 'null'::jsonb), '90'::jsonb)));
\echo '-- H2b the same wrapped in to_jsonb(), exactly as compile.py emits it:'
CREATE INDEX h2b ON idxprobe ((to_jsonb(xpr.ord(('>')::text, nullif((data -> 'score'::text), 'null'::jsonb), '90'::jsonb))));
\echo '-- H2c xpr.truthy over H2a (still no to_jsonb):'
CREATE INDEX h2c ON idxprobe ((xpr.truthy(to_jsonb(xpr.ord(('>')::text, nullif((data -> 'score'::text), 'null'::jsonb), '90'::jsonb)))));
\echo '-- H2d does the planner USE h2a for a predicate written without to_jsonb?'
ANALYZE idxprobe;
SET enable_seqscan = off;
EXPLAIN (COSTS OFF) SELECT data FROM idxprobe WHERE collection='Submission'
  AND xpr.ord(('>')::text, nullif((data -> 'score'::text), 'null'::jsonb), '90'::jsonb);
SET enable_seqscan = on;

\echo '### H3  SORT: does the compiled sort key use an index if the ordering matches?'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT data FROM idxprobe WHERE collection='Submission'
  ORDER BY nullif((data -> 'score'::text), 'null'::jsonb) DESC LIMIT 50;
\echo '-- H3b ASC (index default order):'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT data FROM idxprobe WHERE collection='Submission'
  ORDER BY nullif((data -> 'score'::text), 'null'::jsonb) ASC LIMIT 50;

\echo '### H4  SEMANTIC HAZARD: the indexable rewrite is NOT the compiled predicate'
SELECT (SELECT count(*) FROM idxprobe WHERE collection='Submission'
          AND (data->>'score')::float8 > 90)                                   AS handwritten_indexable,
       (SELECT count(*) FROM idxprobe WHERE collection='Submission'
          AND xpr.truthy(to_jsonb(xpr.ord('>'::text, nullif((data->'score'::text),'null'::jsonb), to_jsonb(90.0::float8))))) AS compiled_expr_gt,
       (SELECT count(*) FROM idxprobe WHERE collection='Submission'
          AND jsonb_typeof(data->'score') = 'string')                          AS score_is_a_string;

\echo '### H5  TOTALITY HAZARD: what the indexable rewrite does with a non-numeric string'
INSERT INTO idxprobe VALUES ('Submission','SUB-NAN','{"score":"n/a","status":"open"}');
\echo '-- H5a compiled predicate (expr is total -> must not raise):'
SELECT count(*) FROM idxprobe WHERE collection='Submission'
  AND xpr.truthy(to_jsonb(xpr.ord('>'::text, nullif((data->'score'::text),'null'::jsonb), to_jsonb(90.0::float8))));
\echo '-- H5b hand-written indexable rewrite on the same row:'
SELECT count(*) FROM idxprobe WHERE collection='Submission' AND (data->>'score')::float8 > 90;
\echo '-- H5c can the btree expression index even be MAINTAINED with that row present?'
DROP INDEX IF EXISTS idxprobe_score_f8;
CREATE INDEX idxprobe_score_f8 ON idxprobe (((data->>'score')::float8));
DELETE FROM idxprobe WHERE key='SUB-NAN';
