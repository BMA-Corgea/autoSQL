-- ============================================================================
-- T-1 spike · THROWAWAY runtime support library for the expr -> Postgres compiler.
--
-- CONTRACT (mirrors core/dashboard/expr.py, GIMS-Project@995cc59 == gims-ledger@7b7a049):
--   * Every expr value is carried as `jsonb`.
--   * expr's Python `None` is represented as SQL NULL, never as jsonb 'null'.
--     (`_resolve_field` cannot distinguish absent-key from JSON-null -> expr.py:562-575,
--      so collapsing both to SQL NULL is faithful.)
--   * Nested JSON nulls (inside arrays/objects) stay as jsonb 'null'; that is also
--     faithful, because Python keeps them as None inside the list/dict.
--
-- This is a SPIKE artifact. It is not a library, nothing imports it, and it is
-- installed only into the scratch database `autosql_spike`, schema `xpr`.
--
-- KNOWN GUC DEPENDENCY: xpr.ecma_num() reads float8's text output, which is the
-- shortest-round-trip representation only when extra_float_digits >= 0 (the PG12+
-- default is 1). The functions are declared IMMUTABLE anyway (a production
-- deployment would have to pin the GUC); this is recorded as a caveat, not hidden.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS xpr;

-- ----------------------------------------------------------------------------
-- f8 : jsonb number -> float8, guarded so an out-of-float8-range JSON numeric
--      yields NULL instead of raising. DIVERGENCE (documented, not in fixture):
--      expr/Python would yield +-inf here; we yield NULL.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.f8(j jsonb) RETURNS float8
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN j IS NULL THEN NULL::float8
    WHEN jsonb_typeof(j) <> 'number' THEN NULL::float8
    WHEN abs((j #>> '{}')::numeric) > 179769313486231570000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000::numeric
      THEN NULL::float8
    ELSE (j #>> '{}')::float8
  END
$$;

-- ----------------------------------------------------------------------------
-- num : implements _to_num (expr.py:305-319)
--   bool -> 1.0/0.0 ; number -> itself ; string -> only if the WHOLE trimmed
--   string matches _NUM_RE (expr.py:302) ; everything else -> NULL.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.num(j jsonb) RETURNS float8
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE jsonb_typeof(j)
    WHEN 'boolean' THEN CASE WHEN j = 'true'::jsonb THEN 1.0::float8 ELSE 0.0::float8 END
    WHEN 'number'  THEN xpr.f8(j)
    WHEN 'string'  THEN (
      CASE WHEN btrim(j #>> '{}', E' \t\n\r\f\v') ~ '^[+-]?([0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)([eE][+-]?[0-9]+)?$'
                AND abs(btrim(j #>> '{}', E' \t\n\r\f\v')::numeric) <= 179769313486231570000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000::numeric
           THEN btrim(j #>> '{}', E' \t\n\r\f\v')::float8
           ELSE NULL::float8 END)
    ELSE NULL::float8
  END
$$;

-- ----------------------------------------------------------------------------
-- truthy : implements _truthy (expr.py:282-293). Never NULL.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.truthy(j jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN j IS NULL THEN false
    WHEN jsonb_typeof(j) = 'null'    THEN false
    WHEN jsonb_typeof(j) = 'boolean' THEN (j = 'true'::jsonb)
    WHEN jsonb_typeof(j) = 'number'  THEN ((j #>> '{}')::numeric <> 0)
    WHEN jsonb_typeof(j) = 'string'  THEN (length(j #>> '{}') > 0)
    WHEN jsonb_typeof(j) = 'array'   THEN (jsonb_array_length(j) > 0)
    WHEN jsonb_typeof(j) = 'object'  THEN (j <> '{}'::jsonb)
    ELSE true
  END
$$;

-- ----------------------------------------------------------------------------
-- ecma_num : implements _num_to_str (expr.py:322-348), ECMA-262 Number::toString.
--   Digit source is float8's own shortest-round-trip text (== Python repr()).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.ecma_num(x float8) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  t text; mpart text; epart int; ipart text; fpart text;
  alld text; pointpos int; lz int; s text; k int; n int; e int; mant text; out text;
BEGIN
  IF x IS NULL THEN RETURN NULL; END IF;
  IF x = 0 THEN RETURN '0'; END IF;                      -- expr.py:328-329 (covers -0.0)
  IF x <> x THEN RETURN 'NaN'; END IF;                   -- expr.py:330-331
  IF x = 'Infinity'::float8  THEN RETURN 'Infinity';  END IF;   -- expr.py:332-333
  IF x = '-Infinity'::float8 THEN RETURN '-Infinity'; END IF;

  t := abs(x)::text;                                     -- shortest round-trip digits
  IF position('e' in t) > 0 THEN
    mpart := split_part(t, 'e', 1);
    epart := split_part(t, 'e', 2)::int;
  ELSE
    mpart := t; epart := 0;
  END IF;
  IF position('.' in mpart) > 0 THEN
    ipart := split_part(mpart, '.', 1);
    fpart := split_part(mpart, '.', 2);
  ELSE
    ipart := mpart; fpart := '';
  END IF;

  alld := ipart || fpart;
  pointpos := length(ipart);
  lz := 0;
  WHILE lz < length(alld) AND substr(alld, lz + 1, 1) = '0' LOOP lz := lz + 1; END LOOP;
  s := substr(alld, lz + 1);
  n := pointpos - lz + epart;                            -- decimal-point position
  s := rtrim(s, '0');                                    -- Decimal(...).normalize()
  IF s = '' THEN RETURN '0'; END IF;
  k := length(s);

  IF k <= n AND n <= 21 THEN                             -- expr.py:338-339
    out := s || repeat('0', n - k);
  ELSIF n > 0 AND n <= 21 THEN                           -- expr.py:340-341
    out := substr(s, 1, n) || '.' || substr(s, n + 1);
  ELSIF n > -6 AND n <= 0 THEN                           -- expr.py:342-343
    out := '0.' || repeat('0', -n) || s;
  ELSE                                                   -- expr.py:344-347
    mant := substr(s, 1, 1) || CASE WHEN k > 1 THEN '.' || substr(s, 2) ELSE '' END;
    e := n - 1;
    out := mant || 'e' || CASE WHEN e >= 0 THEN '+' ELSE '-' END || abs(e)::text;
  END IF;
  RETURN CASE WHEN x < 0 THEN '-' || out ELSE out END;   -- expr.py:348
END
$$;

-- ----------------------------------------------------------------------------
-- str : implements _to_str (expr.py:351-360). list/dict -> NULL.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.str(j jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN j IS NULL THEN NULL::text
    WHEN jsonb_typeof(j) = 'null'    THEN NULL::text
    WHEN jsonb_typeof(j) = 'boolean' THEN CASE WHEN j = 'true'::jsonb THEN 'true' ELSE 'false' END
    WHEN jsonb_typeof(j) = 'number'  THEN xpr.ecma_num(xpr.f8(j))
    WHEN jsonb_typeof(j) = 'string'  THEN (j #>> '{}')
    ELSE NULL::text
  END
$$;

-- ----------------------------------------------------------------------------
-- idx : one ("index", N) field-path step (expr.py:570-574).
--   MUST be type-guarded: Postgres treats a jsonb SCALAR as a 1-element array for
--   integer subscripting ('5'::jsonb -> 0  ==  5), which _resolve_field does not.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.idx(j jsonb, i int) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN jsonb_typeof(j) = 'array' THEN j -> i END
$$;

-- ----------------------------------------------------------------------------
-- ord : implements _order_cmp (expr.py:381-396). Three-valued; type-homogeneous.
--   bool operands, and any mixed pair, are NULL (not an error, not a coercion).
--   String comparison pinned to COLLATE "C" == Python codepoint ordering.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.ord(op text, a jsonb, b jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN a IS NULL OR b IS NULL THEN NULL::boolean
    WHEN jsonb_typeof(a) = 'number' AND jsonb_typeof(b) = 'number' THEN
      CASE op
        WHEN '<'  THEN xpr.f8(a) <  xpr.f8(b)
        WHEN '<=' THEN xpr.f8(a) <= xpr.f8(b)
        WHEN '>'  THEN xpr.f8(a) >  xpr.f8(b)
        ELSE           xpr.f8(a) >= xpr.f8(b)
      END
    WHEN jsonb_typeof(a) = 'string' AND jsonb_typeof(b) = 'string' THEN
      CASE op
        WHEN '<'  THEN (a #>> '{}') COLLATE "C" <  (b #>> '{}')
        WHEN '<=' THEN (a #>> '{}') COLLATE "C" <= (b #>> '{}')
        WHEN '>'  THEN (a #>> '{}') COLLATE "C" >  (b #>> '{}')
        ELSE           (a #>> '{}') COLLATE "C" >= (b #>> '{}')
      END
    ELSE NULL::boolean
  END
$$;

-- ----------------------------------------------------------------------------
-- div : implements the "/" branch (expr.py:620-621) -- zero divisor -> NULL,
--   never Postgres's division_by_zero error.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.div(a float8, b float8) RETURNS float8
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN a IS NULL OR b IS NULL OR b = 0 THEN NULL::float8 ELSE a / b END
$$;

-- ----------------------------------------------------------------------------
-- _bits : IEEE-754 decomposition of |v| -> ARRAY[mantissa, exponent] with
--   |v| == mantissa * 2^exponent exactly. Used only by xpr.fmod.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr._bits(v float8) RETURNS bigint[]
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE b bytea; u bigint := 0; i int; expo int; mant bigint;
BEGIN
  b := float8send(abs(v));                    -- abs() clears the sign bit -> u fits int8
  FOR i IN 0..7 LOOP u := u * 256 + get_byte(b, i); END LOOP;
  expo := (u >> 52)::int;
  mant := u & 4503599627370495;               -- 2^52 - 1
  IF expo = 0 THEN
    RETURN ARRAY[mant, -1074];                -- subnormal
  ELSE
    RETURN ARRAY[mant + 4503599627370496, expo - 1075];
  END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- fmod : implements the "%" branch (expr.py:622-624), which is math.fmod, i.e.
--   C fmod: truncated remainder with the sign of the DIVIDEND.
--   Postgres has NO % operator and NO mod() for double precision at all
--   (verified: 'operator does not exist: double precision % double precision'),
--   so this is computed exactly: decompose both doubles to integer*2^e, scale to a
--   common exponent, take the EXACT numeric mod, then scale back. The result of
--   fmod is always exactly representable, so the final float8 product is exact.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.fmod(x float8, y float8) RETURNS float8
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  bx bigint[]; byv bigint[]; s int; xn numeric; yn numeric; r numeric; res float8;
BEGIN
  IF x IS NULL OR y IS NULL THEN RETURN NULL; END IF;
  IF y = 0 THEN RETURN NULL; END IF;                       -- expr.py:624
  IF x <> x OR y <> y THEN RETURN NULL; END IF;            -- NaN in
  IF x = 'Infinity'::float8 OR x = '-Infinity'::float8 THEN RETURN NULL; END IF;
  IF y = 'Infinity'::float8 OR y = '-Infinity'::float8 THEN RETURN x; END IF;
  IF x = 0 THEN RETURN x; END IF;
  IF abs(x) < abs(y) THEN RETURN x; END IF;

  bx := xpr._bits(x);
  byv := xpr._bits(y);
  s  := least(bx[2], byv[2])::int;
  xn := bx[1]::numeric * (2::numeric ^ (bx[2] - s));
  yn := byv[1]::numeric * (2::numeric ^ (byv[2] - s));
  r  := mod(xn, yn);                                          -- exact truncated remainder
  res := r::float8 * (2::float8 ^ s::float8);
  RETURN CASE WHEN x < 0 THEN -res ELSE res END;
END
$$;

-- ----------------------------------------------------------------------------
-- round : implements _fn_round (expr.py:517-527) -- half AWAY from zero.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.round(x float8, nd float8) RETURNS float8
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE ndig int; factor float8; scaled float8; t float8;
BEGIN
  IF x IS NULL THEN RETURN NULL; END IF;
  ndig := CASE WHEN nd IS NULL THEN 0 ELSE trunc(nd)::int END;   -- int() truncates
  factor := 10::float8 ^ ndig::float8;
  scaled := x * factor;
  IF scaled <> scaled THEN RETURN NULL; END IF;
  t := trunc(abs(scaled) + 0.5);
  RETURN (CASE WHEN scaled < 0 THEN -t ELSE t END) / factor;
END
$$;

-- ----------------------------------------------------------------------------
-- pdate_ms / pdate_only : implement _parse_date_ms (expr.py:409-431).
--   Strict ISO subset; calendar-validated the way Python's datetime() is;
--   UTC assumed when no offset; totally NULL on any failure.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.pdate_ms(j jsonb) RETURNS float8
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  s text; m text[]; y int; mo int; d int; hh int; mi int; ss int; us int;
  off text; dim int; sec numeric; ms numeric; sgn int; dig text;
BEGIN
  IF j IS NULL OR jsonb_typeof(j) <> 'string' THEN RETURN NULL; END IF;  -- expr.py:411-412
  s := btrim(j #>> '{}', E' \t\n\r\f\v');
  m := regexp_match(s,
        '^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?(Z|[+-]\d{2}:?\d{2})?)?$');
  IF m IS NULL THEN RETURN NULL; END IF;
  y := m[1]::int; mo := m[2]::int; d := m[3]::int;
  hh := coalesce(m[4], '0')::int; mi := coalesce(m[5], '0')::int; ss := coalesce(m[6], '0')::int;
  us := rpad(coalesce(m[7], '0'), 6, '0')::int;                          -- expr.py:422
  off := m[8];
  -- datetime(...) would raise ValueError -> _parse_date_ms returns None (expr.py:425-426)
  IF y < 1 OR y > 9999 THEN RETURN NULL; END IF;
  IF mo < 1 OR mo > 12 THEN RETURN NULL; END IF;
  dim := CASE mo
           WHEN 1 THEN 31
           WHEN 2 THEN CASE WHEN (y % 4 = 0 AND y % 100 <> 0) OR y % 400 = 0 THEN 29 ELSE 28 END
           WHEN 3 THEN 31 WHEN 4 THEN 30 WHEN 5 THEN 31 WHEN 6 THEN 30
           WHEN 7 THEN 31 WHEN 8 THEN 31 WHEN 9 THEN 30 WHEN 10 THEN 31
           WHEN 11 THEN 30 ELSE 31 END;
  IF d < 1 OR d > dim THEN RETURN NULL; END IF;
  IF hh > 23 OR mi > 59 OR ss > 59 THEN RETURN NULL; END IF;

  sec := extract(epoch from (make_timestamp(y, mo, d, hh, mi, ss::double precision) at time zone 'UTC'));
  ms  := sec * 1000 + us::numeric / 1000;
  IF off IS NOT NULL AND off <> 'Z' THEN                                  -- expr.py:427-430
    sgn := CASE WHEN substr(off, 1, 1) = '+' THEN 1 ELSE -1 END;
    dig := replace(substr(off, 2), ':', '');
    ms := ms - sgn * (substr(dig, 1, 2)::int * 60 + substr(dig, 3, 2)::int) * 60000;
  END IF;
  RETURN ms::float8;
END
$$;

CREATE OR REPLACE FUNCTION xpr.pdate_only(j jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN xpr.pdate_ms(j) IS NULL THEN NULL::boolean
              ELSE (regexp_match(btrim(j #>> '{}', E' \t\n\r\f\v'),
                     '^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?(Z|[+-]\d{2}:?\d{2})?)?$'
                   ))[4] IS NULL                                          -- has_time == hh is not None
  END
$$;

-- ----------------------------------------------------------------------------
-- fmt_date_ms : implements _format_date_ms (expr.py:434-445), including the
--   out-of-range -> NULL totality rule and 4-digit year zero-padding.
--   Python bounds: datetime.min .. datetime.max, i.e. year 1 .. 9999 UTC.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.fmt_date_ms(ms float8, date_only boolean) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE total_us numeric; sec numeric; rem numeric; ts timestamp;
BEGIN
  IF ms IS NULL OR date_only IS NULL THEN RETURN NULL; END IF;
  IF ms <> ms THEN RETURN NULL; END IF;
  IF ms = 'Infinity'::float8 OR ms = '-Infinity'::float8 THEN RETURN NULL; END IF;
  total_us := round(ms::numeric * 1000);
  IF total_us < -62135596800000000 OR total_us > 253402300799999999 THEN
    RETURN NULL;                                          -- expr.py:440-441
  END IF;
  sec := floor(total_us / 1000000);
  rem := total_us - sec * 1000000;
  ts  := timestamp 'epoch'
         + (sec::bigint::text || ' seconds')::interval
         + (rem::bigint::text || ' microseconds')::interval;
  RETURN CASE WHEN date_only THEN to_char(ts, 'YYYY-MM-DD')
              ELSE to_char(ts, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') END;
END
$$;

-- ----------------------------------------------------------------------------
-- now_ms : implements _now_ms (expr.py:448-456). Context clock override.
--   Wall-clock fallback uses now() (transaction timestamp): one instant per
--   query, which is the set-oriented analogue of expr's one instant per
--   evaluate() call. NOT exercised by the fixture (all clock cases inject "now").
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.now_ms(ctx jsonb) RETURNS float8
LANGUAGE sql STABLE AS $$
  SELECT COALESCE(
    CASE WHEN jsonb_typeof(ctx -> 'now') = 'string' THEN xpr.pdate_ms(ctx -> 'now') END,
    CASE WHEN jsonb_typeof(ctx -> 'now') = 'number' THEN xpr.f8(ctx -> 'now') END,
    extract(epoch from now())::float8 * 1000.0
  )
$$;

-- ----------------------------------------------------------------------------
-- contains : implements _fn_contains (expr.py:488-499).
--   NOTE the exception to null-propagation: a NULL haystack yields FALSE, not NULL.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.contains(hay jsonb, needle jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE hs text; ns text;
BEGIN
  IF hay IS NULL OR jsonb_typeof(hay) = 'null' THEN RETURN false; END IF;   -- expr.py:492-493
  IF jsonb_typeof(hay) = 'array' THEN                                       -- expr.py:494-495
    RETURN EXISTS (SELECT 1 FROM jsonb_array_elements(hay) e
                    WHERE nullif(e, 'null'::jsonb) IS NOT DISTINCT FROM needle);
  END IF;
  hs := xpr.str(hay); ns := xpr.str(needle);                                -- expr.py:496-499
  IF hs IS NULL OR ns IS NULL THEN RETURN false; END IF;
  RETURN position(ns in hs) > 0;
END
$$;

-- ----------------------------------------------------------------------------
-- length : implements the `length` builtin (expr.py:543).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.length(j jsonb) RETURNS float8
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE jsonb_typeof(j)
    WHEN 'string' THEN length(j #>> '{}')::float8
    WHEN 'array'  THEN jsonb_array_length(j)::float8
    WHEN 'object' THEN (SELECT count(*) FROM jsonb_object_keys(j))::float8
    ELSE NULL::float8
  END
$$;

-- ----------------------------------------------------------------------------
-- count_arr / count_one : implements `count` (expr.py:548) over _as_list
--   (expr.py:462-466). Returns 0.0 (never NULL) on an empty/all-null operand set
--   -- the OPPOSITE convention from sum/avg/min/max below.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.count_arr(arr jsonb) RETURNS float8
LANGUAGE sql IMMUTABLE AS $$
  SELECT (SELECT count(*) FROM jsonb_array_elements(arr) e
           WHERE jsonb_typeof(e) <> 'null')::float8
$$;

CREATE OR REPLACE FUNCTION xpr.count_one(j jsonb) RETURNS float8
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN j IS NOT NULL AND jsonb_typeof(j) = 'array' THEN xpr.count_arr(j)
              WHEN j IS NULL THEN 0::float8
              WHEN jsonb_typeof(j) = 'null' THEN 0::float8
              ELSE 1::float8 END
$$;

-- ----------------------------------------------------------------------------
-- reduce_arr / reduce_one : implements sum/avg/min/max via _fn_reduce
--   (expr.py:502-514) -- _to_num filter, and NULL (not 0) on an empty result set.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.reduce_arr(op text, arr jsonb) RETURNS float8
LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE op
           WHEN 'sum' THEN sum(v ORDER BY ord)
           WHEN 'avg' THEN sum(v ORDER BY ord) / nullif(count(*), 0)
           WHEN 'min' THEN min(v)
           WHEN 'max' THEN max(v)
         END
  FROM (SELECT xpr.num(e) AS v, ord
          FROM jsonb_array_elements(arr) WITH ORDINALITY t(e, ord)) q
  WHERE v IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION xpr.reduce_one(op text, j jsonb) RETURNS float8
LANGUAGE sql IMMUTABLE AS $$
  SELECT xpr.reduce_arr(op,
    CASE WHEN j IS NOT NULL AND jsonb_typeof(j) = 'array' THEN j
         ELSE jsonb_build_array(j) END)
$$;
