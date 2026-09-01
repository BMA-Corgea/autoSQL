"""Generate runtime/runtime.sql from runtime.sql.in and the running Python's Unicode data.

The three tables this fills in are not constants — they are *derived from the
interpreter that will run the Python half of the comparison*. That is the whole
point. autoSQL's correctness claim is that the compiled SQL answers what
`core.dashboard.expr` answers; Python's `float()` accepts any Unicode decimal
digit by numeric value, and which code points those are is a property of the
Unicode version the interpreter carries.

Freeze the table as a literal and a Python upgrade splits the two engines
silently: Python starts coercing a digit the SQL mapping has never heard of, the
divergence class T-6 closed reopens, and not one line of code has changed.
`test_no_drift` is what stands between this project and that.

Usage:
    python3 runtime/generate.py            # write runtime/runtime.sql
    python3 runtime/generate.py --check    # exit 1 if the committed file is stale
    python3 runtime/generate.py --stdout   # print, write nothing
"""
from __future__ import annotations

import argparse
import io
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "runtime.sql.in"
TARGET = HERE / "runtime.sql"


def _esc(cp: int) -> str:
    """A Postgres E'' escape for one code point."""
    return "\\u%04X" % cp if cp <= 0xFFFF else "\\U%08X" % cp


def nonascii_decimal_digits() -> list[int]:
    """Every non-ASCII code point Python treats as a decimal digit.

    Category Nd is exactly the set `float()` accepts — verified rather than
    assumed by `test_mapping_matches_float`, which enumerates the whole code
    space and compares against `float()` itself.
    """
    return [cp for cp in range(0x110000)
            if not chr(cp).isascii() and unicodedata.category(chr(cp)) == "Nd"]


def python_whitespace() -> list[int]:
    """Every code point `str.strip()` removes — Python's isspace set, all of it.

    SQL's own btrim in the ASCII gate covers six of these. The other 23 are why
    a value wrapped in a non-breaking space used to read as NULL on one engine
    and 7.0 on the other.
    """
    return [cp for cp in range(0x110000) if chr(cp).isspace()]


def tables() -> dict[str, str]:
    nd = nonascii_decimal_digits()
    ws = python_whitespace()

    frm = "".join(_esc(cp) for cp in nd)
    to = "".join(str(unicodedata.decimal(chr(cp))) for cp in nd)
    if len(to) != len(nd):
        raise SystemExit(
            "translate() needs from/to of equal length: %d code points produced %d "
            "replacement characters. A digit outside 0-9 would do this." % (len(nd), len(to)))

    # Individually, never as ranges: btrim takes a literal character LIST, so a
    # range collapses to its two endpoints and leaves a stray '-' in the set.
    ws_literal = "".join(_esc(cp) for cp in ws)

    return {"ND_MAP_FROM": frm, "ND_MAP_TO": to, "PY_WS": ws_literal}


def render() -> str:
    text = io.open(TEMPLATE, encoding="utf-8").read()
    # Drop the template's own "edit me, not the output" header: it is addressed to
    # whoever edits the template, and repeating it in the generated file tells the
    # reader to edit the very file they are looking at.
    marker = "-- Placeholders: {{PY_WS}} {{ND_MAP_FROM}} {{ND_MAP_TO}}\n--\n"
    if marker in text:
        text = text.split(marker, 1)[1]
    for key, value in tables().items():
        token = "{{%s}}" % key
        if token not in text:
            raise SystemExit("template is missing placeholder %s" % token)
        text = text.replace(token, value)
    if "{{" in text:
        raise SystemExit("template still has an unfilled placeholder after rendering")
    banner = (
        "-- GENERATED FILE — DO NOT EDIT.\n"
        "-- Produced by runtime/generate.py from runtime/runtime.sql.in, using the\n"
        "-- Unicode data of the interpreter that ran it. Edit the template and\n"
        "-- regenerate:  python3 runtime/generate.py\n"
        "--\n"
        "-- Unicode %s · %d non-ASCII decimal digits · %d whitespace code points\n"
        "--\n" % (unicodedata.unidata_version,
                  len(nonascii_decimal_digits()), len(python_whitespace()))
    )
    return banner + text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed runtime.sql is not what this would write")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    args = ap.parse_args(argv)

    text = render()
    if args.stdout:
        sys.stdout.write(text)
        return 0
    if args.check:
        if not TARGET.exists():
            print("runtime/runtime.sql does not exist — run: python3 runtime/generate.py")
            return 1
        current = io.open(TARGET, encoding="utf-8").read()
        if current == text:
            print("runtime/runtime.sql is current (Unicode %s)" % unicodedata.unidata_version)
            return 0
        print("runtime/runtime.sql is STALE for this interpreter (Unicode %s).\n"
              "  Regenerate with: python3 runtime/generate.py\n"
              "  If the digit set itself moved, the two engines have drifted apart — read\n"
              "  runtime/README.md before committing the new bytes."
              % unicodedata.unidata_version)
        return 1

    io.open(TARGET, "w", encoding="utf-8").write(text)
    print("wrote %s (Unicode %s, %d digits, %d whitespace)"
          % (TARGET, unicodedata.unidata_version,
             len(nonascii_decimal_digits()), len(python_whitespace())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
