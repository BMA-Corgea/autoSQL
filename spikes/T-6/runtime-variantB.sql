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
-- f8 : jsonb number -> float8.
-- T-3 STEP ZERO (2026-08-22, EXPERIMENTS.md 1.2): the guard literal was 297 digits
-- (= 1.797693134862316e+296) where DBL_MAX needs 309; every finite double of
-- magnitude ~1.8e296+ was silently nulled.  Fixed to the full 309 digits.
-- THE GA-4 RULING (EXPERIMENTS.md 1.2, "reported runtime refusal"): above DBL_MAX
-- this no longer returns NULL -- a null is an ANSWER, and a wrong one.  It RAISES
-- a NAMED, catchable refusal, SQLSTATE 'XPR01', distinct from every native error
-- class, so the caller can report a fallback to the Python path.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION xpr.f8(j jsonb) RETURNS float8
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE n numeric;
BEGIN
  IF j IS NULL OR jsonb_typeof(j) <> 'number' THEN
    RETURN NULL;
  END IF;
  n := (j #>> '{}')::numeric;
  IF abs(n) > 179769313486231570000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000::numeric THEN
    RAISE EXCEPTION 'xpr.f8 refusal: JSON number magnitude exceeds float8 range (DBL_MAX)'
      USING ERRCODE = 'XPR01',
            DETAIL  = 'value (truncated): ' || left(n::text, 40),
            HINT    = 'named refusal -- fall back to the Python evaluator and report which path ran';
  END IF;
  RETURN (j #>> '{}')::float8;
END
$fn$;

-- ----------------------------------------------------------------------------
-- num : implements _to_num (expr.py:305-319)
--   bool -> 1.0/0.0 ; number -> itself ; string -> only if the WHOLE trimmed
--   string matches _NUM_RE (expr.py:302) ; everything else -> NULL.
-- ----------------------------------------------------------------------------
-- T-3 STEP ZERO + THE GA-4 RULING apply here too (the second of the two sites --
-- the string-coercion path, the one FINDINGS.md D.6 measured as actually reached
-- in real GIMS data).  Same 309-digit literal, same named XPR01 refusal.
-- A numeric string whose EXPONENT overflows numeric itself (e.g. '1e200000') is
-- refused the same way; a tiny one (e.g. '1e-20000') falls through to float8's own
-- native 22003, the pre-existing unguarded-underflow behaviour T-3 measures but,
-- per the framing's scope, does not redesign.
CREATE OR REPLACE FUNCTION xpr.num(j jsonb) RETURNS float8
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE t text; n numeric;
BEGIN
  IF j IS NULL THEN
    RETURN NULL;
  END IF;
  IF jsonb_typeof(j) = 'boolean' THEN
    RETURN CASE WHEN j = 'true'::jsonb THEN 1.0::float8 ELSE 0.0::float8 END;
  ELSIF jsonb_typeof(j) = 'number' THEN
    RETURN xpr.f8(j);
  ELSIF jsonb_typeof(j) = 'string' THEN
    t := btrim(j #>> '{}', E'\u0009\u000A\u000B\u000C\u000D\u001C\u001D\u001E\u001F\u0020\u0085\u00A0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u2028\u2029\u202F\u205F\u3000');
    -- T-6 variant B: MATCH Python instead of refusing.  Python's float() accepts any
    -- Unicode decimal digit by its numeric value, so map the 670 non-ASCII Nd code
    -- points onto '0'-'9' and carry on.  Python also strips its full 29-code-point
    -- isspace set, so the btrim above uses that set rather than six ASCII characters.
    t := translate(t, E'\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669\u06F0\u06F1\u06F2\u06F3\u06F4\u06F5\u06F6\u06F7\u06F8\u06F9\u07C0\u07C1\u07C2\u07C3\u07C4\u07C5\u07C6\u07C7\u07C8\u07C9\u0966\u0967\u0968\u0969\u096A\u096B\u096C\u096D\u096E\u096F\u09E6\u09E7\u09E8\u09E9\u09EA\u09EB\u09EC\u09ED\u09EE\u09EF\u0A66\u0A67\u0A68\u0A69\u0A6A\u0A6B\u0A6C\u0A6D\u0A6E\u0A6F\u0AE6\u0AE7\u0AE8\u0AE9\u0AEA\u0AEB\u0AEC\u0AED\u0AEE\u0AEF\u0B66\u0B67\u0B68\u0B69\u0B6A\u0B6B\u0B6C\u0B6D\u0B6E\u0B6F\u0BE6\u0BE7\u0BE8\u0BE9\u0BEA\u0BEB\u0BEC\u0BED\u0BEE\u0BEF\u0C66\u0C67\u0C68\u0C69\u0C6A\u0C6B\u0C6C\u0C6D\u0C6E\u0C6F\u0CE6\u0CE7\u0CE8\u0CE9\u0CEA\u0CEB\u0CEC\u0CED\u0CEE\u0CEF\u0D66\u0D67\u0D68\u0D69\u0D6A\u0D6B\u0D6C\u0D6D\u0D6E\u0D6F\u0DE6\u0DE7\u0DE8\u0DE9\u0DEA\u0DEB\u0DEC\u0DED\u0DEE\u0DEF\u0E50\u0E51\u0E52\u0E53\u0E54\u0E55\u0E56\u0E57\u0E58\u0E59\u0ED0\u0ED1\u0ED2\u0ED3\u0ED4\u0ED5\u0ED6\u0ED7\u0ED8\u0ED9\u0F20\u0F21\u0F22\u0F23\u0F24\u0F25\u0F26\u0F27\u0F28\u0F29\u1040\u1041\u1042\u1043\u1044\u1045\u1046\u1047\u1048\u1049\u1090\u1091\u1092\u1093\u1094\u1095\u1096\u1097\u1098\u1099\u17E0\u17E1\u17E2\u17E3\u17E4\u17E5\u17E6\u17E7\u17E8\u17E9\u1810\u1811\u1812\u1813\u1814\u1815\u1816\u1817\u1818\u1819\u1946\u1947\u1948\u1949\u194A\u194B\u194C\u194D\u194E\u194F\u19D0\u19D1\u19D2\u19D3\u19D4\u19D5\u19D6\u19D7\u19D8\u19D9\u1A80\u1A81\u1A82\u1A83\u1A84\u1A85\u1A86\u1A87\u1A88\u1A89\u1A90\u1A91\u1A92\u1A93\u1A94\u1A95\u1A96\u1A97\u1A98\u1A99\u1B50\u1B51\u1B52\u1B53\u1B54\u1B55\u1B56\u1B57\u1B58\u1B59\u1BB0\u1BB1\u1BB2\u1BB3\u1BB4\u1BB5\u1BB6\u1BB7\u1BB8\u1BB9\u1C40\u1C41\u1C42\u1C43\u1C44\u1C45\u1C46\u1C47\u1C48\u1C49\u1C50\u1C51\u1C52\u1C53\u1C54\u1C55\u1C56\u1C57\u1C58\u1C59\uA620\uA621\uA622\uA623\uA624\uA625\uA626\uA627\uA628\uA629\uA8D0\uA8D1\uA8D2\uA8D3\uA8D4\uA8D5\uA8D6\uA8D7\uA8D8\uA8D9\uA900\uA901\uA902\uA903\uA904\uA905\uA906\uA907\uA908\uA909\uA9D0\uA9D1\uA9D2\uA9D3\uA9D4\uA9D5\uA9D6\uA9D7\uA9D8\uA9D9\uA9F0\uA9F1\uA9F2\uA9F3\uA9F4\uA9F5\uA9F6\uA9F7\uA9F8\uA9F9\uAA50\uAA51\uAA52\uAA53\uAA54\uAA55\uAA56\uAA57\uAA58\uAA59\uABF0\uABF1\uABF2\uABF3\uABF4\uABF5\uABF6\uABF7\uABF8\uABF9\uFF10\uFF11\uFF12\uFF13\uFF14\uFF15\uFF16\uFF17\uFF18\uFF19\U000104A0\U000104A1\U000104A2\U000104A3\U000104A4\U000104A5\U000104A6\U000104A7\U000104A8\U000104A9\U00010D30\U00010D31\U00010D32\U00010D33\U00010D34\U00010D35\U00010D36\U00010D37\U00010D38\U00010D39\U00011066\U00011067\U00011068\U00011069\U0001106A\U0001106B\U0001106C\U0001106D\U0001106E\U0001106F\U000110F0\U000110F1\U000110F2\U000110F3\U000110F4\U000110F5\U000110F6\U000110F7\U000110F8\U000110F9\U00011136\U00011137\U00011138\U00011139\U0001113A\U0001113B\U0001113C\U0001113D\U0001113E\U0001113F\U000111D0\U000111D1\U000111D2\U000111D3\U000111D4\U000111D5\U000111D6\U000111D7\U000111D8\U000111D9\U000112F0\U000112F1\U000112F2\U000112F3\U000112F4\U000112F5\U000112F6\U000112F7\U000112F8\U000112F9\U00011450\U00011451\U00011452\U00011453\U00011454\U00011455\U00011456\U00011457\U00011458\U00011459\U000114D0\U000114D1\U000114D2\U000114D3\U000114D4\U000114D5\U000114D6\U000114D7\U000114D8\U000114D9\U00011650\U00011651\U00011652\U00011653\U00011654\U00011655\U00011656\U00011657\U00011658\U00011659\U000116C0\U000116C1\U000116C2\U000116C3\U000116C4\U000116C5\U000116C6\U000116C7\U000116C8\U000116C9\U00011730\U00011731\U00011732\U00011733\U00011734\U00011735\U00011736\U00011737\U00011738\U00011739\U000118E0\U000118E1\U000118E2\U000118E3\U000118E4\U000118E5\U000118E6\U000118E7\U000118E8\U000118E9\U00011950\U00011951\U00011952\U00011953\U00011954\U00011955\U00011956\U00011957\U00011958\U00011959\U00011C50\U00011C51\U00011C52\U00011C53\U00011C54\U00011C55\U00011C56\U00011C57\U00011C58\U00011C59\U00011D50\U00011D51\U00011D52\U00011D53\U00011D54\U00011D55\U00011D56\U00011D57\U00011D58\U00011D59\U00011DA0\U00011DA1\U00011DA2\U00011DA3\U00011DA4\U00011DA5\U00011DA6\U00011DA7\U00011DA8\U00011DA9\U00011F50\U00011F51\U00011F52\U00011F53\U00011F54\U00011F55\U00011F56\U00011F57\U00011F58\U00011F59\U00016A60\U00016A61\U00016A62\U00016A63\U00016A64\U00016A65\U00016A66\U00016A67\U00016A68\U00016A69\U00016AC0\U00016AC1\U00016AC2\U00016AC3\U00016AC4\U00016AC5\U00016AC6\U00016AC7\U00016AC8\U00016AC9\U00016B50\U00016B51\U00016B52\U00016B53\U00016B54\U00016B55\U00016B56\U00016B57\U00016B58\U00016B59\U0001D7CE\U0001D7CF\U0001D7D0\U0001D7D1\U0001D7D2\U0001D7D3\U0001D7D4\U0001D7D5\U0001D7D6\U0001D7D7\U0001D7D8\U0001D7D9\U0001D7DA\U0001D7DB\U0001D7DC\U0001D7DD\U0001D7DE\U0001D7DF\U0001D7E0\U0001D7E1\U0001D7E2\U0001D7E3\U0001D7E4\U0001D7E5\U0001D7E6\U0001D7E7\U0001D7E8\U0001D7E9\U0001D7EA\U0001D7EB\U0001D7EC\U0001D7ED\U0001D7EE\U0001D7EF\U0001D7F0\U0001D7F1\U0001D7F2\U0001D7F3\U0001D7F4\U0001D7F5\U0001D7F6\U0001D7F7\U0001D7F8\U0001D7F9\U0001D7FA\U0001D7FB\U0001D7FC\U0001D7FD\U0001D7FE\U0001D7FF\U0001E140\U0001E141\U0001E142\U0001E143\U0001E144\U0001E145\U0001E146\U0001E147\U0001E148\U0001E149\U0001E2F0\U0001E2F1\U0001E2F2\U0001E2F3\U0001E2F4\U0001E2F5\U0001E2F6\U0001E2F7\U0001E2F8\U0001E2F9\U0001E4F0\U0001E4F1\U0001E4F2\U0001E4F3\U0001E4F4\U0001E4F5\U0001E4F6\U0001E4F7\U0001E4F8\U0001E4F9\U0001E950\U0001E951\U0001E952\U0001E953\U0001E954\U0001E955\U0001E956\U0001E957\U0001E958\U0001E959\U0001FBF0\U0001FBF1\U0001FBF2\U0001FBF3\U0001FBF4\U0001FBF5\U0001FBF6\U0001FBF7\U0001FBF8\U0001FBF9', '0123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789');
    IF t !~ '^[+-]?([0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)([eE][+-]?[0-9]+)?$' THEN
      RETURN NULL;
    END IF;
    BEGIN
      n := t::numeric;
    EXCEPTION WHEN numeric_value_out_of_range THEN
      IF t ~ '[eE]-' THEN
        RETURN t::float8;   -- tiny beyond numeric: float8's own native raise surfaces
      END IF;
      RAISE EXCEPTION 'xpr.num refusal: numeric string magnitude exceeds float8 range (DBL_MAX)'
        USING ERRCODE = 'XPR01',
              DETAIL  = 'value (truncated): ' || left(t, 40),
              HINT    = 'named refusal -- fall back to the Python evaluator and report which path ran';
    END;
    IF abs(n) > 179769313486231570000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000::numeric THEN
      RAISE EXCEPTION 'xpr.num refusal: numeric string magnitude exceeds float8 range (DBL_MAX)'
        USING ERRCODE = 'XPR01',
              DETAIL  = 'value (truncated): ' || left(t, 40),
              HINT    = 'named refusal -- fall back to the Python evaluator and report which path ran';
    END IF;
    RETURN t::float8;
  ELSE
    RETURN NULL;
  END IF;
END
$fn$;

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
