"""demo/tests/t114_mutants.py — T-114's mutants: the times GIMS writes read as times, one rule for both engines.

BE1–BE9 break both engines ALIKE -- the rule's two statements (``picks/times.py`` and ``runtime/runtime.sql``'s
``xpr.time_at``) or the one expression both evaluate -- so the engines agree, the differential passes, and only the
hand truth can catch them. E1–E21 break one engine at one edge each. BD1–BD9 put one reader of a bare date back
at UTC midnight (a-chk's preview: on a question's clock every reader reads it as the clock's midnight); BD10 drops
the hour a clock skips that a bare date's midnight sits in; BD11 and BD12 put the sort and a board's latest /
earliest back at UTC midnight; BD13 and BD14 break the clock reading they share (a repeated midnight; D); BD15-BD19
the one instant. RO1-RO4 read a time field more than once a row again (a-chk's cost MEDIUM); FN1, RC1 and KL1-KL3
undo the cost window's three fixes (the fence, the second engine's memory, the Kleene groups' shorter form); WB1 and
WB2 move a window's bound to the wrong side of a time at its very instant; ED1-ED4 step past the calendar's ends
again (t98-23); YP1 writes a year below 1000 as strftime does (t98-24). A runtime mutant edits ``runtime/runtime.sql``,
which the parity tests install fresh (``this_runtime.install``) into the throwaway. Run on ``t78_mutants.py``'s
runner, from a scratch copy, with AUTOSQL_PARITY_DSN set to a throwaway Postgres (the dashboard cases build their
own scratch copy of the seed there).

    AUTOSQL_PARITY_DSN=… demo/.venv/bin/python demo/tests/t114_mutants.py [--dry-run] [--only BE1,E3]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t78_mutants as runner  # noqa: E402

_P = "../parity/tests/test_t114_times.py::"
_PY = _P + "test_the_rule_in_python"
_SQL = _P + "test_the_rule_in_sql"
_T = "../picks/times.py"
_R = "../runtime/runtime.sql"
_V = "../picks/view.py"
_B = "../picks/builder.py"
_E = "../picks/pyrunner/evaluate.py"
_SH = "../picks/pyrunner/shape.py"
_G = "../picks/group.py"
_PG = "../picks/pyrunner/group.py"

_ZONE_PY = '(?:Z|[+-](?:0[0-9]|1[0-4]):?[0-5][0-9])")'
_ZONE_SQL = "(Z|[+-](0[0-9]|1[0-4]):?[0-5][0-9])$'"
_CAST = "      THEN v::timestamptz\n"
_MICRO = '        micro = int(rest[1:k].ljust(6, "0"))\n'
_SHIFT = "        shift = sign * timedelta(hours=int(rest[1:3]), minutes=int(rest[-2:]))\n"
_KLEENE = '    if logic in ("one", "allnone") and any(_reads_any_instant(it, fields) for it in live):\n'
_SECOND = "_the_second_engine_alone_compares_instants_and_an_unreadable_time_matches_nothing"
_BARE = _P + "test_every_reader_reads_a_bare_date_as_its_clocks_midnight"
_STATEMENT = "_the_statement_compares_instants_and_an_unreadable_time_matches_nothing"
_EDGE = _P + "test_a_bare_date_on_a_day_its_clock_skips_or_repeats_midnight_reads_as_its_first_instant"
_ONCE = _P + "test_a_time_field_is_read_once_a_row"
_C = "../compiler/compile.py"


def _pair(text, want):
    """The rule's hand-truth case in both engines."""
    return [f"{_PY}[{text}-{want}]", f"{_SQL}[{text}-{want}]"]


T114_MUTANTS = [
    # ── both engines broken alike: only the hand truth catches these ──
    dict(id="BE1", defect="BOTH engines flip the offset's sign (they agree)",
         edits=[(_T, _SHIFT, _SHIFT.replace("shift = sign", "shift = -sign")),
                (_R, _CAST, "      THEN (v::timestamp AT TIME ZONE 'UTC') + ((v::timestamp AT TIME ZONE 'UTC') - v::timestamptz)\n")],
         selector=_pair("2026-07-09T05:03:48-0600", "2026-07-09T11:03:48.000000Z"),
         expect="AssertionError: ('2026-07-09T05:03:48-0600',"),
    dict(id="BE2", defect="BOTH engines drop the fraction",
         edits=[(_T, _MICRO, "        micro = 0\n"),
                (_R, _CAST, "      THEN date_trunc('second', v::timestamptz)\n")],
         selector=_pair("2026-07-09T05:03:48.123456+00:00", "2026-07-09T05:03:48.123456Z"),
         expect="AssertionError: ('2026-07-09T05:03:48.123456+00:00',"),
    dict(id="BE3", defect="BOTH engines read a naive time as UTC",
         edits=[(_T, _ZONE_PY, _ZONE_PY.replace(')")', ')?")')),
                (_T, '    if rest[0] == ".":', '    if rest[:1] == ".":'),
                (_T, '    if rest == "Z":', '    if rest in ("Z", ""):'),
                (_R, _ZONE_SQL, _ZONE_SQL.replace("])$'", "])?$'"))],
         selector=_pair("2026-07-09T05:03:48", "None"), expect="AssertionError: ('2026-07-09T05:03:48',"),
    dict(id="BE4", defect="BOTH engines leave an offset without its colon (-0600) unread",
         edits=[(_T, _ZONE_PY, _ZONE_PY.replace(":?[0-5]", ":[0-5]")),
                (_R, _ZONE_SQL, _ZONE_SQL.replace(":?[0-5]", ":[0-5]"))],
         selector=_pair("2026-07-09T05:03:48-0600", "2026-07-09T11:03:48.000000Z"),
         expect="AssertionError: ('2026-07-09T05:03:48-0600',"),
    dict(id="BE5", defect="the kind's majority test dropped: one time-looking value makes free text a time (both setups)",
         edits=[(_V, "        if readable and 2 * looks > n:\n", "        if readable:\n")],
         selector=_P + "test_the_field_kind_both_directions[free text with one readable time among three words]",
         expect="AssertionError: ('free text"),
    dict(id="BE6", defect="BOTH engines read 7+ fraction digits, truncated (they agree, and the rule refuses it)",
         edits=[(_T, r'(?:\.[0-9]{1,6})?"', r'(?:\.[0-9]{1,9})?"'),
                (_T, _MICRO, '        micro = int(rest[1:k][:6].ljust(6, "0"))\n'),
                (_R, r"(\.[0-9]{1,6})?(Z|", r"(\.[0-9]{1,9})?(Z|"),
                (_R, _CAST, "      THEN regexp_replace(v, '(\\.[0-9]{6})[0-9]+', '\\1')::timestamptz\n")],
         selector=_pair("2026-07-09T05:03:48.1234567Z", "None"), expect="AssertionError: ('2026-07-09T05:03:48.1234567Z',"),
    dict(id="BE7", defect="negation: an unreadable time is 'not after X' again (the one expression both engines read)",
         edits=[(_V, _KLEENE, "    if False:\n")],
         selector=[_P + f"test{_SECOND}[all or none (after X, S is y): no unreadable row]",
                   _P + f"test{_STATEMENT}[all or none (after X, S is y): no unreadable row]"],
         expect="AssertionError: ('all or none"),
    dict(id="BE8", defect="BOTH engines sort a time field by its text again",
         edits=[(_B, "            if reads_as_instant(field, self.times):\n", "            if False:\n"),
                (_SH, '            if ev.reads_as_instant(field, pick.get("times")):\n', "            if False:\n")],
         selector=[_P + "test_the_second_engine_alone_sorts_a_time_field_by_its_instant_and_caps_it[desc-want0-None]",
                   _P + "test_the_statement_sorts_a_time_field_by_its_instant_and_caps_it[desc-want0-None]"],
         expect="AssertionError: assert ["),
    dict(id="BE9", defect="BOTH engines ignore the offset (they agree)",
         edits=[(_T, _SHIFT, "        shift = timedelta(0)\n"),
                (_R, _CAST, "      THEN v::timestamp AT TIME ZONE 'UTC'\n")],
         selector=_pair("2026-07-09T05:03:48-0600", "2026-07-09T11:03:48.000000Z"),
         expect="AssertionError: ('2026-07-09T05:03:48-0600',"),
    # ── one edge, one engine each ──
    dict(id="E1", defect="the statement's offset cap widened to 15",
         edits=[(_R, _ZONE_SQL, _ZONE_SQL.replace("1[0-4]", "1[0-5]"))],
         selector=f"{_SQL}[2026-07-09T05:03:48+15:00-None]", expect="AssertionError: ('2026-07-09T05:03:48+15:00',"),
    dict(id="E2", defect="the statement's year range dropped (an instant in year 0 read)",
         edits=[(_R, "         AND (v COLLATE \"C\" >= '0001-01-02' AND v COLLATE \"C\" < '9999-12-31'\n"
                     "              OR (v::timestamptz >= '0001-01-01 00:00:00+00' AND v::timestamptz < '10000-01-01 00:00:00+00'))\n",
                 "")],
         selector=f"{_SQL}[0001-01-01T00:30:00+01:00-None]", expect="AssertionError: ('0001-01-01T00:30:00+01:00',"),
    dict(id="E3", defect="the second engine leaves a space-separated time unread",
         edits=[(_T, "-[0-9]{2}[T ](?:[01]", "-[0-9]{2}T(?:[01]")],
         selector=f"{_PY}[2026-07-09 05:03:48+00:00-2026-07-09T05:03:48.000000Z]",
         expect="AssertionError: ('2026-07-09 05:03:48+00:00',"),
    dict(id="E4", defect="the statement reads a lowercase t and z",
         edits=[(_R, "[0-9]{2}[T ]([01]", "[0-9]{2}[Tt ]([01]"), (_R, r"(\.[0-9]{1,6})?(Z|", r"(\.[0-9]{1,6})?([Zz]|")],
         selector=f"{_SQL}[2026-07-09t05:03:48z-None]", expect="AssertionError: ('2026-07-09t05:03:48z',"),
    dict(id="E5", defect="a time field's span back to the first and last of 2,001 texts",
         edits=[(_V, '        if kind == "time" and t_lo is not None:\n', '        if kind == "time" and strings:\n'),
                (_V, '            field["range"] = {"min": _span_text(t_lo), "max": _span_text(t_hi)}\n',
                 '            field["range"] = {"min": strings[0], "max": strings[-1]}\n')],
         selector=_P + "test_the_dashboards_setup_calls_a_mixed_field_a_time_and_free_text_text",
         expect="AssertionError: None"),          # T-126: a field past VALUE_LIMIT has no values list, so no span
    dict(id="E6", defect="the named-field bucket reads ::timestamp again (the offset dropped)",
         edits=[(_B, "date_trunc({g}, {at}, 'UTC') AT TIME ZONE 'UTC'", "date_trunc({g}, {value}::timestamp)")],
         selector=_P + "test_the_statement_buckets_every_readable_time_by_its_instant[None]", expect="AssertionError: {"),
    dict(id="E7", defect="the view names no time field: a condition compares text again",
         edits=[(_V, '        if f and _reads_instant(f, c) and f["path"] not in out:\n', "        if False:\n")],
         selector=_P + f"test{_STATEMENT}[on Jul 9 (UTC)]", expect="AssertionError: ('on Jul 9 (UTC)'"),
    dict(id="E8", defect="the second engine skips the instant reading",
         edits=[(_E, "    record = instant_record(row.record_f, instants, zone) if instants else row.record_f\n",
                 "    record = row.record_f\n")],
         selector=_P + f"test{_SECOND}[on Jul 9 (UTC)]", expect="AssertionError: ('on Jul 9 (UTC)'"),
    dict(id="E9", defect="the second engine reads an unreadable value as null (it turns blank)",
         edits=[(_T, "    if at is None:\n        return False\n", "    if at is None:\n        return None\n")],
         selector=_P + f"test{_SECOND}[all or none (after X, S is y): no unreadable row]",
         expect="AssertionError: ('all or none"),
    dict(id="E10", defect="the statement reads an unreadable value as null (it turns blank)",
         edits=[(_R, "  RETURN 'false'::jsonb;\n", "  RETURN NULL;\n")],
         selector=_P + f"test{_STATEMENT}[all or none (after X, S is y): no unreadable row]",
         expect="AssertionError: ('all or none"),
    dict(id="E11", defect="the year shortcut reads the stored text: a time near year 1 read on a clock is bucketed",
         edits=[(_B, "    return (f\"(({at} >= '0001-01-02 00:00:00+00'::timestamptz AND {at} < '9999-12-31 00:00:00+00'::timestamptz)\"",
                 "    return (f\"(({value} COLLATE \\\"C\\\" >= '0001-01-02' AND {value} COLLATE \\\"C\\\" < '9999-12-31')\"")],
         selector=_P + "test_the_statement_leaves_a_clock_reading_before_year_1_out", expect="AssertionError: {"),
    dict(id="E12", defect="the kind's edge flipped: exactly half is a time",
         edits=[(_V, "        if readable and 2 * looks > n:\n", "        if readable and 2 * looks >= n:\n")],
         selector=_P + "test_the_field_kind_both_directions[one readable, one junk: exactly half is text]",
         expect="AssertionError: ('one readable, one junk"),
    dict(id="E13", defect="the Python reader (GIMS's SQLite mode) counts the forms its own way",
         edits=[(_V, '            filled, looks, readable, not_date = times.kind_counts(strings)\n',
                 '            filled, looks, readable, not_date = times.kind_counts(v for v in strings if "+" not in v)\n')],
         selector=_P + "test_the_python_reader_answers_the_setup_as_postgres_does", expect="AssertionError: assert {"),
    dict(id="E14", defect="a picked end drops its fraction (GIMS's day end, its last microsecond)",
         edits=[(_V, "    if m.group(5):", "    if False:")],
         selector=_P + f"test{_STATEMENT}[a day's last microsecond, inclusive (GIMS's day end)]",
         expect="AssertionError: (\"a day's last microsecond"),
    dict(id="E15", defect="the statement sorts an unreadable time as a boolean (not pinned last)",
         edits=[(_B, "                value = f\"nullif({reading}, 'false'::jsonb)\"\n",
                 "                value = f\"{reading}\"\n")],
         selector=_P + "test_the_statement_sorts_a_time_field_by_its_instant_and_caps_it[desc-want0-None]",
         expect="AssertionError: assert ["),
    dict(id="E16", defect="the statement's board reads a time field's latest by text again",
         edits=[(_G, '        if t["field"] in (spec.get("count_times") or ()):\n', "        if False:\n")],
         selector=_P + "test_the_statement_reads_a_boards_latest_and_earliest_by_instant[max]",
         expect="AssertionError: {"),
    dict(id="E17", defect="the second engine's board reads a time field's latest by text again",
         edits=[(_PG, "        if time and time_instant:\n", "        if False:\n")],
         selector=_P + "test_the_second_engine_alone_reads_a_boards_latest_and_earliest_by_instant[max]",
         expect="AssertionError: {"),
    dict(id="E18", defect="the series time back to the one fixed form (T-109's guard no longer follows the rule)",
         edits=[(_B, "    return f\"(jsonb_typeof(data -> '{time}') = 'string' AND length({v}) > 10 AND xpr.time_at({v}) IS NOT NULL)\"\n",
                 "    return (f\"(jsonb_typeof(data -> '{time}') = 'string' AND {v} ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T"
                 "([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$' AND xpr.time_at({v}) IS NOT NULL)\")\n")],
         selector="../parity/tests/test_t109_refuses_by_name.py::"
                  "test_a_series_time_with_a_fraction_or_an_offset_is_counted_by_both_engines[fraction-None]",
         expect="series time is not one this reads"),
    dict(id="E19", defect="the dashboard's pick names no time field (to_pick)",
         edits=[(_V, '    if read:\n        pick["times"] = read\n', "")],
         selector=_P + "test_the_dashboards_conditions_compare_instants[on Jul 9 (UTC)]",
         expect="AssertionError: ('on Jul 9 (UTC)'"),
    dict(id="E20", defect="D compared as text again: its bounds as UTC text, tested against the stored text",
         edits=[(_B, '    p.params["bkt_bounds"] = bounds\n',
                 '    p.params["bkt_bounds"] = [__import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime(b))'
                 ' for b in bounds]\n'),
                (_B, "width_bucket(extract(epoch FROM {v})::float8, %(bkt_bounds)s::float8[])",
                 'width_bucket((data #>> %(bkt_path)s) COLLATE \\"C\\", %(bkt_bounds)s::text[])')],
         selector=_P + "test_the_statement_tests_D_against_a_times_instant_never_its_text"
                       "[inside D by its instant, before it as text]",
         expect="AssertionError: ('inside D by its instant, before it as text'"),
    dict(id="E21", defect="the probes ask about a time field raw again, though its truth reads it as an instant",
         edits=[("../picks/probes.py", "    return {repr(parse(paths.dollar(t))) for t in times}\n", "    return set()\n")],
         selector=_P + "test_a_probe_never_asks_about_a_time_field_its_truth_reads_as_an_instant",
         expect="AssertionError: RuntimeRefusal('out-of-range magnitude"),
    # ── a-chk's preview: on a question's clock every reader reads a bare date as that clock's midnight ──
    dict(id="BD1", defect="the span: the axis no longer reaches the bare dates at the clock's midnight",
         edits=[("../demo/server/dashboard.py", '''    dates = r.get("dates")
    if dates:
        lo = None if lo is None else min(lo, day_start(dates["min"]))
        hi = None if hi is None else max(hi, day_start(dates["max"]))
''', "")],
         selector=_BARE + "[America/Denver]", expect="('span', 'day'"),
    dict(id="BD3", defect="the statement alone reads a bare date at UTC midnight again (its conditions, time of day)",
         edits=[(_R, "    IF t IS NOT NULL AND length(j #>> '{}') = 10 THEN\n"
                     "      RETURN j;                          -- a bare date reads as itself: its midnight is the question's clock's\n"
                     "    ELSIF t IS NOT NULL THEN\n", "    IF t IS NOT NULL THEN\n")],
         selector=_BARE + "[America/Denver]", expect="('on Jul 9'"),
    dict(id="BD4", defect="the second engine alone reads a bare date at UTC midnight again",
         edits=[(_T, "    return value if len(value) == 10 else utc_text(at)\n", "    return utc_text(at)\n")],
         selector=_BARE + "[America/Denver]", expect="('on Jul 9'"),
    dict(id="BD5", defect="a bare date reads as no time again, in both engines' readings (the date branch dropped)",
         edits=[(_B, "                    f\" THEN to_jsonb({start} || '{times_mod.DATE_MARK}') ELSE {r} END AS t{i}\")\n",
                 "                    f\" THEN 'false'::jsonb ELSE {r} END AS t{i}\")\n"),
                (_T, "        return utc_text(midnight(r, zone))[:-1] + DATE_MARK\n", "        return False\n")],
         selector=_BARE + "[None]", expect="('on Jul 9'"),
    dict(id="BD6", defect="the axis no longer reaches the answer's own buckets: a bucket past the setup's span sits "
                          "after a gap (a 500 before every bucket with rows was laid)",
         edits=[("../demo/server/dashboard.py", "            lo, hi = min(lo, first), max(hi, last)\n", "")],
         selector=_P + "test_a_bucket_newer_than_the_setups_span_widens_the_axis_never_a_500",
         expect="AssertionError: {'label'"),
    dict(id="BD8", defect="before T: T written as a time at its instant: a bare date whose day begins at T is before it",
         edits=[(_V, "    return f\"{ref} < {string_literal(_marked(_instant(cond.get('value'), zone)))}\"",
                 "    return f\"{ref} < {string_literal(_wide(_instant(cond.get('value'), zone)))}\"")],
         selector=_EDGE + "[America/Havana]", expect="('before Mar 8, 1:00 AM'"),
    dict(id="BD9", defect="between A and B: A written as a time at its instant: a bare date whose day begins at A is out",
         edits=[(_V, "        return (f\"{ref} >= {string_literal(_marked(_instant(lo, zone)))} and {ref} <= {b}\",",
                 "        return (f\"{ref} >= {string_literal(_wide(_instant(lo, zone)))} and {ref} <= {b}\",")],
         selector=_EDGE + "[America/Havana]", expect="('between Mar 8, 1:00 AM and 11:00 PM'"),
    dict(id="BD10", defect="the axis lays only the hours the clock shows: a bucket an engine labels off them is dropped",
         edits=[("../demo/server/dashboard.py", "    return sorted(set(_slots(unit, lo, hi, zone)) | set(starts))\n",
                 "    return _slots(unit, lo, hi, zone)\n")],
         selector=_P + "test_the_axis_lays_every_bucket_an_engine_returns_even_an_hour_the_clock_never_shows",
         expect="AssertionError: assert ["),
    dict(id="BD11", defect="the pick names no clock: its readers put a bare date at UTC midnight again (both engines)",
         edits=[(_V, "        pick[\"times_zone\"] = view_zone(view)     # T-114: they are read on the question's clock (a "
                     "bare date at its midnight)\n", "        pass\n")],
         selector=_BARE + "[America/Denver]", expect="(\"the table's sort\", 'asc'"),
    dict(id="BD12", defect="a board names no clock: its latest / earliest reads a bare date at UTC midnight again",
         edits=[(_V, "        spec[\"times_zone\"] = view_zone(view)     # T-114: they are read on the question's clock\n",
                 "        pass\n")],
         selector=_BARE + "[America/Denver]", expect="(\"the board's latest\""),
    dict(id="BD13", defect="the statement reads a midnight the clock repeats as the later of the two (AT TIME ZONE's own)",
         edits=[(_B, "    return (f\"GREATEST(CASE WHEN {early} < {late} AND ({early} AT TIME ZONE {zone}) = {wall} THEN {early}\"\n"
                     "            f\" ELSE {late} END, '0001-01-01 00:00:00+00'::timestamptz)\")\n",
                 "    return f\"GREATEST({late}, '0001-01-01 00:00:00+00'::timestamptz)\"\n")],
         selector=_EDGE + "[America/Havana]", expect="('sort', 'asc'"),
    dict(id="BD14", defect="a bare date's midnight is read on the clock without D: inside it the sort reads on, unrefused",
         edits=[(_B, "    if not gaps:\n        return lambda d: date_midnight(d, z)\n",
                 "    if True:\n        return lambda d: date_midnight(d, z)\n")],
         selector=_P + "test_the_sort_reads_only_a_bare_date_on_the_clock_and_refuses_one_inside_d_by_name",
         expect="DID NOT RAISE"),
    dict(id="BD15", defect="the statement puts a bare date per hour at its wall midnight again (Havana's Mar 8: 12 AM)",
         edits=[(_B, "    day_start = read(date_midnight(value, \"%(bkt_zone)s::text\")) if hourly else f\"{value}::timestamp\"\n",
                 "    day_start = f\"{value}::timestamp\"\n")],
         selector=_EDGE + "[America/Havana]", expect="('buckets', 'hour'"),
    dict(id="BD16", defect="a day's bounds read its midnight as the later of two (fold=1), not its first instant",
         edits=[(_V, "    return times.utc_text(times.midnight(day.isoformat(), zone))[:-1] + times.DATE_MARK\n",
                 "    return times.utc_text(times.midnight(day.isoformat(), zone) if zone is None else _dt.datetime("
                 "day.year, day.month, day.day, fold=1, tzinfo=zones.ZoneInfo(zone)).astimezone(_dt.timezone.utc))"
                 "[:-1] + times.DATE_MARK\n")],
         selector=_EDGE + "[America/Havana]", expect="('on Nov 1'"),
    dict(id="BD17", defect="the count behind a capped table drops the question's clock: a bare date counts at UTC midnight",
         edits=[("../demo/server/dashboard.py", "                      bucket=\"off\", computed=[], sort=None, cap=None)\n",
                 "                      bucket=\"off\", computed=[], sort=None, cap=None)\n"
                 "    count_pick.pop(\"times_zone\", None)\n")],
         selector=_P + "test_a_capped_table_on_a_clock_counts_a_bare_date_on_that_clock",
         expect="AssertionError: ('the first 25 of"),
    dict(id="BD18", defect="the statement reads a bare date level with a time at its very midnight (its mark a Z)",
         edits=[(_B, "                    f\" THEN to_jsonb({start} || '{times_mod.DATE_MARK}') ELSE {r} END AS t{i}\")\n",
                 "                    f\" THEN to_jsonb({start} || 'Z') ELSE {r} END AS t{i}\")\n")],
         selector=_P + "test_a_bare_date_sorts_ahead_of_a_time_at_its_very_midnight[America/Denver]",
         expect="('America/Denver', 'asc'"),
    dict(id="BD19", defect="per hour a bare date is read on the clock without D: inside it the bucket reads on, unrefused",
         edits=[(_B, "    day_start = read(date_midnight(value, \"%(bkt_zone)s::text\")) if hourly else f\"{value}::timestamp\"\n",
                 "    day_start = (f\"({date_midnight(value, '%(bkt_zone)s::text')} AT TIME ZONE %(bkt_zone)s::text)\" if hourly\n"
                 "                 else f\"{value}::timestamp\")\n")],
         selector=_BARE + "[America/Denver]", expect="('zone check', 'hour'"),
    # a-chk's cost MEDIUM: a time field read once a row
    dict(id="RO1", defect="the compiler ignores the statement's once-a-row readings: a condition reads its field again",
         edits=[(_C, "        if self.instant_refs and tuple(tuple(step) for step in path) in self.instant_refs:\n",
                 "        if False:\n")],
         selector=_ONCE + "[on a day (Denver)]", expect="AssertionError: ('on a day (Denver)'"),
    dict(id="RO2", defect="the sort reads its time field again instead of the statement's reading",
         edits=[(_B, "                ref = self.time_ref(field, q)\n", "                ref = None\n")],
         selector=_ONCE + "[a capped sort (Denver)]", expect="AssertionError: ('a capped sort (Denver)'"),
    dict(id="RO3", defect="a board's count-ifs read their time field again instead of the board's reading",
         edits=[(_G, "            compile_kw=builder.reads_kw(compile_c, count_times, counted_refs))\n",
                 "            compile_kw=builder.instants_kw(compile_c, count_times))\n")],
         selector=_ONCE + "[a board: a time count-if with its %, and latest (Denver)]",
         expect="AssertionError: ('a board"),
    dict(id="RO4", defect="the sort takes the language's reading, which has no JSON null: a blank leaves its place",
         edits=[(_B, "                reading = (f\"(CASE WHEN {value} = 'null'::jsonb THEN 'null'::jsonb ELSE {ref} END)\" if ref\n",
                 "                reading = (ref if ref\n")],
         selector=_P + "test_the_statement_sorts_a_time_field_by_its_instant_and_caps_it[asc-want1-None]",
         expect="AssertionError: assert ["),
    # the cost window's three fixes (a-chk's cost on 506e4b2)
    dict(id="FN1", defect="the reading's LATERAL fenced on its inner level only: Postgres copies it into each comparison",
         edits=[(_B, "            f\" FROM (SELECT {', '.join(reads)} OFFSET 0) AS s OFFSET 0) AS {name}\", tuple(refs))\n",
                 "            f\" FROM (SELECT {', '.join(reads)} OFFSET 0) AS s) AS {name}\", tuple(refs))\n")],
         selector=_P + "test_a_reading_is_worked_out_once_a_row_and_its_comparisons_stay_inlined[on a day (Denver)]",
         expect="AssertionError: ('on a day (Denver)'"),
    dict(id="RC1", defect="the second engine reads every row's time afresh again (nothing remembered)",
         edits=[(_T, "@lru_cache(maxsize=_REMEMBERED)\ndef _instant(", "def _instant("),
                (_T, "@lru_cache(maxsize=_REMEMBERED)\ndef _reading(", "def _reading(")],
         selector=_P + "test_the_second_engine_reads_each_stored_time_once", expect="135, 27)"),
    dict(id="KL1", defect="a Kleene group of two is written as counts again, which == reads three times over",
         edits=[(_V, "    return tuple(min(p, c, key=len) for p, c in zip(plain, counts))\n", "    return counts\n")],
         selector=_P + "test_a_kleene_group_over_a_time_is_written_with_and_and_or[one-2]", expect="AssertionError: ((if("),
    dict(id="KL2", defect="exactly one, and / or form: one holds, the others' fails dropped (BOTH engines: at least one)",
         edits=[(_V, "        plain = (both([both([holds[i]] + fails[:i] + fails[i + 1:], \"and\") for i in range(n)], \"or\"),\n",
                 "        plain = (both([holds[i] for i in range(n)], \"or\"),\n")],
         selector=[_P + f"test{_SECOND}[exactly one (before X, S is y): no unreadable row]",
                   _P + f"test{_STATEMENT}[exactly one (before X, S is y): no unreadable row]"],
         expect="AssertionError: ('exactly one"),
    dict(id="KL3", defect="all or none, and / or form: none holding counts as all failing (BOTH engines: an unreadable one in)",
         edits=[(_V, "        plain = (f\"({both(holds, 'and')}) or ({both(fails, 'and')})\",\n",
                 "        plain = (f\"({both(holds, 'and')}) or (not ({both(holds, 'or')}))\",\n")],
         selector=[_P + f"test{_SECOND}[all or none (after X, S is y): no unreadable row]",
                   _P + f"test{_STATEMENT}[all or none (after X, S is y): no unreadable row]"],
         expect="AssertionError: ('all or none"),
    # a window's bounds, each on its side of a time at its very instant
    dict(id="WB1", defect="on D: the day's bounds written as times (Z): D's own bare date out, the next day's in",
         edits=[(_V, "    return times.utc_text(times.midnight(day.isoformat(), zone))[:-1] + times.DATE_MARK\n",
                 "    return times.utc_text(times.midnight(day.isoformat(), zone))\n")],
         selector=_BARE + "[None]", expect="('on Jul 9'"),
    dict(id="WB2", defect="after T: past T as a bare date would read: a time at T's very instant is after T",
         edits=[(_V, "        return f\"{ref} > {lit}\", f\"{said} {said_t}\"\n",
                 "        return f\"{ref} > {string_literal(_marked(_instant(cond.get('value'), zone)))}\", f\"{said} {said_t}\"\n")],
         selector=_P + f"test{_SECOND}[after 05:03:48 UTC]", expect="AssertionError: ('after 05:03:48 UTC'"),
    # t98-23: the calendar's ends
    dict(id="ED1", defect="a cell for a time its clock can't show reads it on that clock anyway: an OverflowError, a 500",
         edits=[(_V, "            local = at.astimezone(zones.ZoneInfo(zone))\n        except OverflowError:\n",
                 "            local = at.astimezone(zones.ZoneInfo(zone))\n        except ZeroDivisionError:\n")],
         selector=_P + "test_a_cell_for_a_time_its_clock_cant_show_says_what_is_stored_in_utc[Asia/Kolkata]",
         expect="AssertionError: (500,"),
    dict(id="ED2", defect="the calendar's last day has no end on any clock: on Kiritimati a time on Jan 1, 10000 is on Dec 31",
         edits=[(_V, "    if zone is None:\n        return None\n    last = _dt.datetime.combine(day, _dt.time.max)\n",
                 "    if True:\n        return None\n    last = _dt.datetime.combine(day, _dt.time.max)\n")],
         selector=_P + "test_the_calendars_last_day_ends_at_its_last_instant_on_the_clock[case1]",
         expect="AssertionError: (('en', 'Pacific/Kiritimati')"),
    dict(id="ED3", defect="a wall time whose instant leaves the calendar raises OverflowError (the axis's hour test: a 500)",
         edits=[("../picks/zones.py", "    except OverflowError:\n        raise ZoneError(\n",
                 "    except ZeroDivisionError:\n        raise ZoneError(\n")],
         selector=_P + "test_a_chart_at_the_calendars_ends_stops_at_its_last_instant[case4]",
         expect="AssertionError: (('eo', 'Asia/Kolkata', 'hour'), 500"),
    dict(id="ED4", defect="the axis steps past the calendar's last slot: an OverflowError, a 500",
         edits=[("../demo/server/dashboard.py", "        except (OverflowError, ValueError):\n            break",
                 "        except ZeroDivisionError:\n            break")],
         selector=_P + "test_a_chart_at_the_calendars_ends_stops_at_its_last_instant[case0]",
         expect="AssertionError: (('en', None, 'day'), 500"),
    # t98-24: one width
    dict(id="YP1", defect="a picked wall time's instant written with strftime again: year 1 as \"1\", compared wrong",
         edits=[("../picks/zones.py", "    return _times.fixed_text(moment.astimezone(_UTC))\n",
                 "    return moment.astimezone(_UTC).strftime(\"%Y-%m-%dT%H:%M:%SZ\")\n")],
         selector=_P + "test_a_time_in_years_1_to_999_is_compared_at_one_width_on_every_clock"
                       "[America/Denver after 0001-06-15T12:00]",
         expect="AssertionError: (('America/Denver', 'after'"),
]


def main(argv=None) -> int:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    if not os.environ.get("AUTOSQL_PARITY_DSN") and "--dry-run" not in (argv or sys.argv[1:]):
        print("t114 mutants: refusing to run — set AUTOSQL_PARITY_DSN to a throwaway Postgres")
        return 2
    runner.T78_MUTANTS[:] = T114_MUTANTS
    return runner.main(argv)


if __name__ == "__main__":
    sys.exit(main())
