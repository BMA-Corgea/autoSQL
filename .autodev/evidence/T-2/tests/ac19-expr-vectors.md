# AC-19 — the static gate over GIMS's expression vectors

**A reported observation, not a pass mark.** Produced by `demo/tests/test_expr_vectors.py` on every `./run-demo test` that can see a `GIMS-Project` checkout; the run that cannot see one skips loudly instead and leaves this file as it stood. Nothing in the suite passes or fails on the split below — see the criterion, and the module docstring, for why it cannot.

## What was read, and with what

| | |
|---|---|
| fixture | `/home/corgea/Desktop/Coding Projects/GIMS-Project/tests/fixtures/expr_vectors.json` |
| fixture sha256 | `0091df64283d91cbcae75c814d56f9a5b759881044962b068544da8e10003552` |
| fixture bytes | 15,499 |
| fixture `version` | `1` |
| fixture `float_epsilon` | `1e-09` |
| cases | 130 (AC-19 names 130) |
| gate | `demo/gate.py` — the 32-construct allowlist over the 12 AST tags |
| parser | `demo/vendor/expr.py` — the demo's own vendored copy (R4), never the checkout's, so nothing is executed inside a read-only tree |

## The split

- AC-19 (reported observation, no threshold): 68 accepted / 62 refused of 130 fixture cases.
- AC-19's expected reading is 68 accepted / 62 refused — this run MATCHES it.
- AC-19 per-case report written to /home/corgea/Desktop/Coding Projects/autoSQL/demo/ac19-expr-vectors.md

Read it as §0 defines it: a **contract-surface** count — how much of *this test file* falls inside the safe subset — and never as how much of real use is covered. No corpus of real use exists in either checkout, and `FINDINGS.md` §5.7(i) rules that this figure may not be quoted at a gate.

## Refusals by construct

| construct | cases refused |
|---|---|
| `days_between` | 9 |
| `string` | 8 |
| `%` | 7 |
| `date_add` | 7 |
| `contains` | 5 |
| `round` | 5 |
| `sum` | 4 |
| `concat` | 3 |
| `number` | 3 |
| `avg` | 2 |
| `ceil` | 2 |
| `floor` | 2 |
| `lower` | 2 |
| `now` | 1 |
| `today` | 1 |
| `upper` | 1 |

68 cases were accepted and are not listed here; every one of them appears in the per-case table below, and 62 refusals name the construct that stopped them.

## Every case, one row each

`construct` and `rule` are the gate's own words for a refusal — the two things AC-19 requires instead of a bare "refused".

| # | case | expression | verdict | construct | rule |
|---:|---|---|---|---|---|
| 1 | `arithmetic/add` | `1 + 2` | accepted | — | — |
| 2 | `arithmetic/precedence_mul_before_add` | `10 - 4 * 2` | accepted | — | — |
| 3 | `arithmetic/parens_override` | `(10 - 4) * 2` | accepted | — | — |
| 4 | `arithmetic/true_division` | `7 / 2` | accepted | — | — |
| 5 | `arithmetic/modulo_pos` | `7 % 3` | refused | `%` | `%` is outside the safe subset -- the only arithmetic this demo compiles is + - * / |
| 6 | `arithmetic/modulo_neg_dividend_truncates` | `-5 % 3` | refused | `%` | `%` is outside the safe subset -- the only arithmetic this demo compiles is + - * / |
| 7 | `arithmetic/modulo_neg_divisor_truncates` | `5 % -3` | refused | `%` | `%` is outside the safe subset -- the only arithmetic this demo compiles is + - * / |
| 8 | `arithmetic/unary_minus` | `-3 + 1` | accepted | — | — |
| 9 | `arithmetic/mul_unary` | `2 * -3` | accepted | — | — |
| 10 | `arithmetic/divide_by_zero_is_null` | `5 / 0` | accepted | — | — |
| 11 | `arithmetic/modulo_by_zero_is_null` | `5 % 0` | refused | `%` | `%` is outside the safe subset -- the only arithmetic this demo compiles is + - * / |
| 12 | `fields/simple` | `$.a` | accepted | — | — |
| 13 | `fields/nested` | `$.a.b` | accepted | — | — |
| 14 | `fields/missing_top` | `$.missing` | accepted | — | — |
| 15 | `fields/descend_into_nondict_is_null` | `$.a.b` | accepted | — | — |
| 16 | `fields/bracket_quoted_key_with_space` | `$["weird key"]` | accepted | — | — |
| 17 | `fields/bracket_index` | `$.list[1]` | accepted | — | — |
| 18 | `fields/bracket_negative_index` | `$.list[-1]` | accepted | — | — |
| 19 | `fields/bracket_index_out_of_range_is_null` | `$.arr[5]` | accepted | — | — |
| 20 | `fields/deep_nested_key` | `$.results.ph` | accepted | — | — |
| 21 | `null_propagation/add_missing_field` | `$.a + $.b` | accepted | — | — |
| 22 | `null_propagation/add_present_fields` | `$.a + $.b` | accepted | — | — |
| 23 | `null_propagation/mul_nonnumeric_string` | `$.a * 2` | accepted | — | — |
| 24 | `null_propagation/add_numeric_string_coerces` | `$.a + 1` | accepted | — | — |
| 25 | `comparison/lt_true` | `$.n < 7` | accepted | — | — |
| 26 | `comparison/lt_false` | `$.n < 7` | accepted | — | — |
| 27 | `comparison/lt_missing_is_null` | `$.n < 7` | accepted | — | — |
| 28 | `comparison/eq_string_true` | `$.s == "FAIL"` | accepted | — | — |
| 29 | `comparison/eq_string_false` | `$.s == "FAIL"` | accepted | — | — |
| 30 | `comparison/neq_string_true` | `$.s != "FAIL"` | accepted | — | — |
| 31 | `comparison/eq_num_true` | `1 == 1` | accepted | — | — |
| 32 | `comparison/eq_num_false` | `1 == 2` | accepted | — | — |
| 33 | `comparison/null_eq_null` | `null == null` | accepted | — | — |
| 34 | `comparison/missing_eq_null_true` | `$.x == null` | accepted | — | — |
| 35 | `comparison/zero_eq_null_false` | `$.x == null` | accepted | — | — |
| 36 | `comparison/bool_eq_bool` | `true == true` | accepted | — | — |
| 37 | `comparison/bool_ne_num` | `true == 1` | accepted | — | — |
| 38 | `comparison/string_ne_num` | `"2" == 2` | accepted | — | — |
| 39 | `comparison/string_lex_lt` | `"apple" < "banana"` | accepted | — | — |
| 40 | `comparison/gte_equal` | `$.n >= 10` | accepted | — | — |
| 41 | `comparison/order_mixed_types_is_null` | `$.n < "x"` | accepted | — | — |
| 42 | `boolean/and_ff` | `true and false` | accepted | — | — |
| 43 | `boolean/or_tf` | `true or false` | accepted | — | — |
| 44 | `boolean/not_true` | `not true` | accepted | — | — |
| 45 | `boolean/not_missing_is_true` | `not $.x` | accepted | — | — |
| 46 | `boolean/and_with_falsy_zero` | `$.a and $.b` | accepted | — | — |
| 47 | `boolean/or_with_truthy` | `$.a or $.b` | accepted | — | — |
| 48 | `boolean/not_of_comparison` | `not (1 < 2)` | accepted | — | — |
| 49 | `boolean/range_check` | `$.n > 0 and $.n < 10` | accepted | — | — |
| 50 | `boolean/empty_string_falsy` | `not ""` | accepted | — | — |
| 51 | `boolean/nonempty_string_truthy` | `not "x"` | accepted | — | — |
| 52 | `boolean/zero_falsy` | `not 0` | accepted | — | — |
| 53 | `boolean/empty_list_falsy` | `not $.list` | accepted | — | — |
| 54 | `boolean/nonempty_list_truthy` | `not $.list` | accepted | — | — |
| 55 | `dates/today_from_now` | `today()` | refused | `today` | `today` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 56 | `dates/now_from_now` | `now()` | refused | `now` | `now` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 57 | `dates/days_between_today_future` | `days_between(today(), $.due)` | refused | `days_between` | `days_between` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 58 | `dates/days_between_reverse_negative` | `days_between("2026-07-02", "2026-07-01")` | refused | `days_between` | `days_between` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 59 | `dates/days_between_two_days` | `days_between("2026-07-01", "2026-07-03")` | refused | `days_between` | `days_between` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 60 | `dates/days_between_fractional` | `days_between("2026-07-01T12:00:00Z", "2026-07-02T00:00:00Z")` | refused | `days_between` | `days_between` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 61 | `dates/days_between_offset_aware` | `days_between("2026-07-01T00:00:00+02:00", "2026-07-01T00:00:00Z")` | refused | `days_between` | `days_between` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 62 | `dates/days_between_bad_input_null` | `days_between("bad", "2026-07-01")` | refused | `days_between` | `days_between` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 63 | `dates/date_add_days` | `date_add("2026-07-02", 7)` | refused | `date_add` | `date_add` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 64 | `dates/date_add_negative` | `date_add("2026-07-02", -2)` | refused | `date_add` | `date_add` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 65 | `dates/date_add_datetime_preserves_time` | `date_add("2026-07-02T10:00:00Z", 1)` | refused | `date_add` | `date_add` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 66 | `dates/date_add_year_rollover` | `date_add("2026-12-31", 1)` | refused | `date_add` | `date_add` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 67 | `dates/date_add_bad_input_null` | `date_add("nope", 1)` | refused | `date_add` | `date_add` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 68 | `coalesce/second_non_null` | `coalesce($.a, $.b, 0)` | accepted | — | — |
| 69 | `coalesce/all_missing_default` | `coalesce($.a, $.b, 0)` | accepted | — | — |
| 70 | `coalesce/all_null_returns_null` | `coalesce($.a, $.b)` | accepted | — | — |
| 71 | `coalesce/skip_literal_null` | `coalesce(null, 3)` | accepted | — | — |
| 72 | `strings/lower` | `lower($.s)` | refused | `lower` | `lower` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 73 | `strings/upper` | `upper($.s)` | refused | `upper` | `upper` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 74 | `strings/lower_missing_null` | `lower($.s)` | refused | `lower` | `lower` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 75 | `strings/contains_substring_true` | `contains($.s, "ell")` | refused | `contains` | `contains` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 76 | `strings/contains_substring_false` | `contains($.s, "xyz")` | refused | `contains` | `contains` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 77 | `strings/contains_list_member_true` | `contains($.tags, "a")` | refused | `contains` | `contains` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 78 | `strings/contains_list_member_false` | `contains($.tags, "z")` | refused | `contains` | `contains` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 79 | `strings/contains_missing_haystack_false` | `contains($.s, "a")` | refused | `contains` | `contains` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 80 | `strings/concat_literals` | `concat("a", "b", "c")` | refused | `concat` | `concat` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 81 | `strings/concat_fields` | `concat($.first, " ", $.last)` | refused | `concat` | `concat` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 82 | `strings/concat_with_string_of_number` | `concat("n=", string($.n))` | refused | `concat` | `concat` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 83 | `coercion/number_of_string` | `number("3.5")` | refused | `number` | `number` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 84 | `coercion/number_of_nonnumeric_null` | `number("abc")` | refused | `number` | `number` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 85 | `coercion/number_of_bool` | `number(true)` | refused | `number` | `number` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 86 | `coercion/string_of_int` | `string(5)` | refused | `string` | `string` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 87 | `coercion/string_of_float` | `string(3.5)` | refused | `string` | `string` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 88 | `coercion/string_of_bool` | `string(true)` | refused | `string` | `string` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 89 | `coercion/string_of_null` | `string(null)` | refused | `string` | `string` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 90 | `coercion/length_string` | `length($.s)` | accepted | — | — |
| 91 | `coercion/length_list` | `length($.list)` | accepted | — | — |
| 92 | `coercion/length_number_null` | `length($.n)` | accepted | — | — |
| 93 | `numeric_funcs/abs_literal` | `abs(-4)` | accepted | — | — |
| 94 | `numeric_funcs/abs_field` | `abs($.n)` | accepted | — | — |
| 95 | `numeric_funcs/floor_pos` | `floor(3.7)` | refused | `floor` | `floor` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 96 | `numeric_funcs/ceil_pos` | `ceil(3.2)` | refused | `ceil` | `ceil` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 97 | `numeric_funcs/floor_neg` | `floor(-3.2)` | refused | `floor` | `floor` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 98 | `numeric_funcs/ceil_neg` | `ceil(-3.2)` | refused | `ceil` | `ceil` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 99 | `numeric_funcs/round_half_up` | `round(2.5)` | refused | `round` | `round` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 100 | `numeric_funcs/round_half_away_from_zero_neg` | `round(-2.5)` | refused | `round` | `round` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 101 | `numeric_funcs/round_down` | `round(2.4)` | refused | `round` | `round` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 102 | `numeric_funcs/round_ndigits` | `round(3.14159, 2)` | refused | `round` | `round` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 103 | `numeric_funcs/round_ndigits_one` | `round(12.345, 1)` | refused | `round` | `round` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 104 | `aggregates/count_list` | `count($.list)` | accepted | — | — |
| 105 | `aggregates/count_skips_null` | `count($.list)` | accepted | — | — |
| 106 | `aggregates/sum_list` | `sum($.list)` | refused | `sum` | `sum` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 107 | `aggregates/sum_skips_nonnumeric` | `sum($.list)` | refused | `sum` | `sum` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 108 | `aggregates/avg_list` | `avg($.list)` | refused | `avg` | `avg` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 109 | `aggregates/min_list` | `min($.list)` | accepted | — | — |
| 110 | `aggregates/max_list` | `max($.list)` | accepted | — | — |
| 111 | `aggregates/max_varargs` | `max(1, 5, 3)` | accepted | — | — |
| 112 | `aggregates/sum_varargs` | `sum(1, 2, 3)` | refused | `sum` | `sum` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 113 | `aggregates/avg_empty_null` | `avg($.list)` | refused | `avg` | `avg` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 114 | `aggregates/sum_missing_null` | `sum($.empty)` | refused | `sum` | `sum` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 115 | `conditional/if_true_branch` | `if($.n > 0, "pos", "neg")` | accepted | — | — |
| 116 | `conditional/if_false_branch` | `if($.n > 0, "pos", "neg")` | accepted | — | — |
| 117 | `conditional/if_missing_is_false` | `if($.x, 1, 2)` | accepted | — | — |
| 118 | `composite/near_due_predicate` | `days_between(today(), $.due_date) < 7` | refused | `days_between` | `days_between` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 119 | `composite/result_in_set` | `$.result == "FAIL" or $.result == "ERROR"` | accepted | — | — |
| 120 | `composite/overdue_label` | `if(days_between(today(), $.due) < 0, "overdue", "ok")` | refused | `days_between` | `days_between` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 121 | `composite/days_left_derived` | `days_between(today(), $.due)` | refused | `days_between` | `days_between` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 122 | `modulo_fmod/mod_float_fmod` | `10.5 % 3` | refused | `%` | `%` is outside the safe subset -- the only arithmetic this demo compiles is + - * / |
| 123 | `modulo_fmod/mod_float_ieee` | `0.5 % 0.1` | refused | `%` | `%` is outside the safe subset -- the only arithmetic this demo compiles is + - * / |
| 124 | `modulo_fmod/mod_large_over_small_positive` | `$.a % $.b` | refused | `%` | `%` is outside the safe subset -- the only arithmetic this demo compiles is + - * / |
| 125 | `string_ecma/string_small_decimal_not_exp` | `string($.n)` | refused | `string` | `string` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 126 | `string_ecma/string_tiny_exp` | `string($.n)` | refused | `string` | `string` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 127 | `string_ecma/string_large_int_float` | `string($.n)` | refused | `string` | `string` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 128 | `string_ecma/string_neg_small` | `string($.n)` | refused | `string` | `string` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 129 | `date_total/date_add_out_of_range_null` | `date_add("9999-12-31", 100000)` | refused | `date_add` | `date_add` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
| 130 | `date_total/date_add_year_padded` | `date_add("0002-01-01", -1)` | refused | `date_add` | `date_add` is outside the safe subset -- the only functions this demo compiles are abs, coalesce, count, if, length, max, min |
