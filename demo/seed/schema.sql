-- demo/seed/schema.sql — the demo's one table, exactly as T-2-plan.md §5.1
-- writes it (spec §8.2).
--
-- No other index, ever (plan §5.1, spec Q11/§4.8): AC-12 asserts that
-- `SELECT * FROM pg_indexes WHERE schemaname = 'demo'` returns exactly ONE
-- row — the primary key below, which is part of the table's definition
-- rather than query acceleration (R6). Nothing in this file, and nothing
-- anywhere else in the demo tree, may add a second one.

CREATE SCHEMA demo;
CREATE TABLE demo.records (
  collection text  NOT NULL,
  key        text  NOT NULL,
  data       jsonb NOT NULL,
  PRIMARY KEY (collection, key)
);
