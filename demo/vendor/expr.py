"""A small, sandboxed expression language for dashboard derived-fields and conditions.

This is **NOT** ``eval``. A tenant writes short expressions like

    days_between(today(), $.due_date)          # a derived "days_left" column
    $.result == "FAIL"                          # a condition predicate
    coalesce($.corrected, $.value)              # fall back across arbitrary fields

and the system evaluates them against one record (an arbitrary-key dict) with a
whitelisted function set and total (never-throwing) semantics. Because the same language
runs client-side (``frontend/lib/expr.js``, Phase 3) for live previews, the behaviour here
is the contract: every case in ``tests/fixtures/expr_vectors.json`` must produce the
identical value in both runtimes. The grammar + semantics are documented in
``design/dashboard_expr_grammar.md``.

Design rules that keep the two runtimes identical and the sandbox safe:
- **Total, not throwing.** Every operation returns ``null`` rather than raising on bad
  input (missing field, non-numeric operand, unparseable date, divide-by-zero). Only a
  *syntax* error (at ``parse`` time) raises :class:`ExprError`.
- **The evaluator never PRODUCES a non-finite number.** A number past the double range does not
  coerce (``"1e400"``, a 400-digit integer, a stored ``inf``: ``_to_num`` → not-a-number), and a
  result that would be infinite or NaN (``1e200 * 1e200``, ``round(x, 400)``) is ``null``. A field is
  still READ as stored, as autoSQL's SQL reads it (T-36 review F1), so ``$.a`` passes a stored ``inf``
  through; the resolve route sends any such stored value as ``null`` rather than a 500.
- **Bounded depth.** An AST deeper than :data:`MAX_AST_DEPTH` is a syntax error, so neither the
  parser nor the evaluator can run out of Python stack on a long chain (``1+1+…+1``).
- **UTC-only dates.** All date maths is done on UTC epoch-milliseconds via a strict ISO
  parser, so there is no timezone drift between Python and JS. The one exception is
  ``time_of_day(t, zone)``, which reads a wall clock in a zone NAMED in the call (never the
  machine's or the session's), from the closed list :data:`TIME_ZONES` both runtimes hold.
- **Per-record scalar semantics.** An expression maps one record → one scalar. Aggregation
  *across records* is a renderer concern (Phase 3), not part of this language; the
  ``count/sum/avg/min/max`` functions here operate on a single list *value* (e.g. a field
  that is itself a list).
- **No bare identifiers.** Field access is only via ``$`` (``$.a.b`` / ``$["a b"]`` /
  ``$[0]``); every other identifier must be a whitelisted function or a keyword
  (``and``/``or``/``not``/``true``/``false``/``null``). This removes any accidental
  variable/attribute reach.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

MAX_SOURCE_LEN = 2000       # reject pathologically long expressions before tokenising
MAX_DEPTH = 64              # parser recursion guard (deeply-nested parens)
MAX_AST_DEPTH = 256         # evaluator recursion guard: a 257-term `+` chain is a syntax error
MS_PER_DAY = 86_400_000.0
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

Value = Any                 # null | bool | float | str | list | dict
AST = Tuple                 # tagged tuple, e.g. ("bin", "+", left, right)


class ExprError(Exception):
    """A syntax error in an expression (raised only by :func:`parse`)."""


# ----------------------------------------------------------------------------------------
# Tokeniser
# ----------------------------------------------------------------------------------------
_TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<num>\d+\.\d+(?:[eE][+-]?\d+)?|\d+(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)
    | (?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
    | (?P<op><=|>=|==|!=|<|>|\+|-|\*|/|%|\(|\)|\[|\]|,|\.|\$)
    | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE,
)
_KEYWORDS = {"and", "or", "not", "true", "false", "null"}


def _tokenize(src: str) -> List[Tuple[str, str]]:
    tokens: List[Tuple[str, str]] = []
    pos, n = 0, len(src)
    while pos < n:
        m = _TOKEN_RE.match(src, pos)
        if not m:
            raise ExprError(f"Unexpected character {src[pos]!r} at position {pos}")
        pos = m.end()
        kind = m.lastgroup
        text = m.group()
        if kind == "ws":
            continue
        if kind == "ident" and text in _KEYWORDS:
            tokens.append(("kw", text))
        else:
            tokens.append((kind, text))
    tokens.append(("eof", ""))
    return tokens


def _decode_string(raw: str) -> str:
    """Decode a quoted string literal (supports \\n \\t \\\\ \\" \\' \\/ and the quote)."""
    body = raw[1:-1]
    out: List[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


# ----------------------------------------------------------------------------------------
# Parser (recursive descent; precedence low→high: or, and, not, cmp, +-, */%, unary, primary)
# ----------------------------------------------------------------------------------------
class _Parser:
    def __init__(self, tokens: List[Tuple[str, str]]):
        self.toks = tokens
        self.i = 0
        self.depth = 0

    def _peek(self) -> Tuple[str, str]:
        return self.toks[self.i]

    def _next(self) -> Tuple[str, str]:
        t = self.toks[self.i]
        self.i += 1
        return t

    def _expect(self, kind: str, text: Optional[str] = None) -> Tuple[str, str]:
        k, v = self._peek()
        if k != kind or (text is not None and v != text):
            want = text if text is not None else kind
            raise ExprError(f"Expected {want!r} but found {v!r}")
        return self._next()

    def parse(self) -> AST:
        node = self._or()
        if self._peek()[0] != "eof":
            raise ExprError(f"Unexpected trailing token {self._peek()[1]!r}")
        return node

    def _or(self) -> AST:
        node = self._and()
        while self._peek() == ("kw", "or"):
            self._next()
            node = ("or", node, self._and())
        return node

    def _and(self) -> AST:
        node = self._not()
        while self._peek() == ("kw", "and"):
            self._next()
            node = ("and", node, self._not())
        return node

    def _not(self) -> AST:
        # A loop, not recursion: `not not … x` 500 deep must reach the AST-depth check as a
        # syntax error rather than exhaust the parser's stack. Same AST as the recursive form.
        count = 0
        while self._peek() == ("kw", "not"):
            self._next()
            count += 1
        node = self._cmp()
        for _ in range(count):
            node = ("not", node)
        return node

    def _cmp(self) -> AST:
        node = self._add()
        k, v = self._peek()
        if k == "op" and v in ("==", "!=", "<", "<=", ">", ">="):
            self._next()
            return ("cmp", v, node, self._add())
        return node

    def _add(self) -> AST:
        node = self._mul()
        while self._peek()[0] == "op" and self._peek()[1] in ("+", "-"):
            op = self._next()[1]
            node = ("bin", op, node, self._mul())
        return node

    def _mul(self) -> AST:
        node = self._unary()
        while self._peek()[0] == "op" and self._peek()[1] in ("*", "/", "%"):
            op = self._next()[1]
            node = ("bin", op, node, self._unary())
        return node

    def _unary(self) -> AST:
        # A loop, not recursion (see _not): "-" * 1999 + "1" raised RecursionError here, a 500
        # from expression text alone. Unary plus is still dropped; each minus is one ("neg", …).
        negations = 0
        while self._peek()[0] == "op" and self._peek()[1] in ("-", "+"):
            if self._next()[1] == "-":
                negations += 1
        node = self._primary()
        for _ in range(negations):
            node = ("neg", node)
        return node

    def _primary(self) -> AST:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ExprError("Expression nesting too deep")
        try:
            k, v = self._peek()
            if k == "num":
                self._next()
                return ("num", float(v))
            if k == "str":
                self._next()
                return ("str", _decode_string(v))
            if k == "kw" and v in ("true", "false"):
                self._next()
                return ("bool", v == "true")
            if k == "kw" and v == "null":
                self._next()
                return ("null",)
            if k == "op" and v == "$":
                return self._field()
            if k == "op" and v == "(":
                self._next()
                node = self._or()
                self._expect("op", ")")
                return node
            if k == "ident":
                return self._call()
            raise ExprError(f"Unexpected token {v!r}")
        finally:
            self.depth -= 1

    def _field(self) -> AST:
        self._expect("op", "$")
        path: List[Tuple[str, Any]] = []
        while True:
            k, v = self._peek()
            if k == "op" and v == ".":
                self._next()
                nk, nv = self._peek()
                if nk != "ident":
                    raise ExprError("Expected a field name after '.'")
                self._next()
                path.append(("key", nv))
            elif k == "op" and v == "[":
                self._next()
                neg = False
                if self._peek() == ("op", "-"):
                    self._next()
                    neg = True
                ik, iv = self._peek()
                if ik == "str" and not neg:
                    self._next()
                    path.append(("key", _decode_string(iv)))
                elif ik == "num" and "." not in iv and "e" not in iv.lower():
                    self._next()
                    idx = int(iv)
                    path.append(("index", -idx if neg else idx))
                else:
                    raise ExprError("Expected a quoted key or integer index inside '[]'")
                self._expect("op", "]")
            else:
                break
        return ("field", path)

    def _call(self) -> AST:
        name = self._next()[1]
        self._expect("op", "(")
        args: List[AST] = []
        if self._peek() != ("op", ")"):
            args.append(self._or())
            while self._peek() == ("op", ","):
                self._next()
                args.append(self._or())
        self._expect("op", ")")
        if name not in _FUNCTIONS:
            raise ExprError(f"Unknown function {name!r}")
        return ("call", name, args)


def parse(src: str) -> AST:
    """Parse an expression string into an AST. Raises :class:`ExprError` on a syntax error."""
    if src is None or not isinstance(src, str):
        raise ExprError("Expression must be a string")
    if len(src) > MAX_SOURCE_LEN:
        raise ExprError("Expression too long")
    if src.strip() == "":
        raise ExprError("Empty expression")
    ast = _Parser(_tokenize(src)).parse()
    if _ast_depth(ast) > MAX_AST_DEPTH:
        raise ExprError("Expression nesting too deep")
    return ast


def _ast_depth(ast: AST) -> int:
    """Depth of the longest path through ``ast``, counted without recursion. The evaluator
    recurses once per level, so this bound is what keeps :func:`evaluate` inside the stack."""
    deepest, stack = 0, [(ast, 1)]
    while stack:
        node, depth = stack.pop()
        deepest = max(deepest, depth)
        tag = node[0]
        if tag in ("neg", "not"):
            children: Tuple = (node[1],)
        elif tag in ("and", "or"):
            children = (node[1], node[2])
        elif tag in ("cmp", "bin"):
            children = (node[2], node[3])
        elif tag == "call":
            children = tuple(node[2])
        else:
            children = ()
        stack.extend((child, depth + 1) for child in children)
    return deepest


# ----------------------------------------------------------------------------------------
# Value helpers (identical semantics must be mirrored in the JS evaluator)
# ----------------------------------------------------------------------------------------
def _is_num(v: Value) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _as_float(v: Value) -> float:
    """``float(v)`` for a number, except that an integer too large for a double becomes ±inf —
    what ``JSON.parse`` makes of it in the browser — instead of raising ``OverflowError``."""
    try:
        return float(v)
    except OverflowError:
        return math.inf if v > 0 else -math.inf


def _finite(x: Optional[float]) -> Optional[float]:
    """A numeric result, or ``None`` if it is infinite or NaN (see "Numbers are finite")."""
    return x if x is None or math.isfinite(x) else None




def _truthy(v: Value) -> bool:
    if v is None or v is False:
        return False
    if v is True:
        return True
    if _is_num(v):
        return v != 0 and v == v  # last clause rejects NaN
    if isinstance(v, str):
        return len(v) > 0
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    return True


def truthy(value: Value) -> bool:
    """Public truthiness (the same rule ``not``/``and``/``or``/``if`` use). Handy for a
    caller that wants to treat an evaluated condition as a keep/drop predicate."""
    return _truthy(value)


_NUM_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")


def _to_num(v: Value) -> Optional[float]:
    """Coerce to a finite float, or None if not numeric (never raises, never returns NaN or
    ±inf: ``"1e400"`` and a 400-digit integer are not numbers this language can hold)."""
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if _is_num(v):
        return _finite(_as_float(v))
    if isinstance(v, str):
        s = v.strip()
        if _NUM_RE.match(s):
            try:
                return _finite(float(s))
            except ValueError:
                return None
    return None


def _num_to_str(x: float) -> str:
    """Format a float exactly as ECMAScript ``String(Number)`` / ``Number.prototype.toString``
    does, so ``string()``/``concat()`` produce byte-identical text in Python and the JS mirror
    (the JS side can just use ``String(n)``). Uses the shortest round-tripping digits (Python
    ``repr`` == JS shortest) and applies ECMA-262 §Number::toString formatting (exponent only
    for very small/large magnitudes; ``1e+21`` not ``1000…``; ``0.00001`` not ``1e-05``)."""
    if x == 0:
        return "0"
    if x != x:
        return "NaN"  # unreachable: NaN is coerced to null upstream
    if x in (float("inf"), float("-inf")):
        return "Infinity" if x > 0 else "-Infinity"
    sign, digits, exp = Decimal(repr(abs(x))).normalize().as_tuple()
    s = "".join(map(str, digits))          # significant digits, no leading/trailing zeros
    k = len(s)
    n = k + exp                            # decimal-point position: value == s × 10^(n-k)
    if k <= n <= 21:
        out = s + "0" * (n - k)
    elif 0 < n <= 21:
        out = s[:n] + "." + s[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + s
    else:
        mant = s[0] + ("." + s[1:] if k > 1 else "")
        e = n - 1
        out = f"{mant}e{'+' if e >= 0 else '-'}{abs(e)}"
    return ("-" + out) if x < 0 else out


def _to_str(v: Value) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if _is_num(v):
        return _num_to_str(_as_float(v))
    if isinstance(v, str):
        return v
    return None


def _eq(a: Value, b: Value) -> bool:
    # An explicit stack, not recursion: two lists nested 498 deep raised RecursionError. The
    # pairs are independent, so the order they are visited in cannot change the answer.
    # A pair of containers already being compared is not compared again: that is what makes a
    # self-referencing value (a derive of bare `$` stored into its own row) terminate instead
    # of looping forever (T-36 review F2). JSON itself has no cycles, so no tree answer changes.
    pending = [(a, b)]
    seen: set = set()
    while pending:
        x, y = pending.pop()
        if x is y:
            continue
        if isinstance(x, (list, dict)) and isinstance(y, (list, dict)):
            pair = (id(x), id(y))
            if pair in seen:
                continue
            seen.add(pair)
        if x is None and y is None:
            continue
        if x is None or y is None:
            return False
        if isinstance(x, bool) or isinstance(y, bool):
            if isinstance(x, bool) and isinstance(y, bool) and x == y:
                continue
            return False
        if _is_num(x) and _is_num(y):
            if _as_float(x) == _as_float(y):
                continue
            return False
        if isinstance(x, str) and isinstance(y, str):
            if x == y:
                continue
            return False
        if isinstance(x, list) and isinstance(y, list):
            if len(x) != len(y):
                return False
            pending.extend(zip(x, y))
            continue
        if isinstance(x, dict) and isinstance(y, dict):
            if x.keys() != y.keys():
                return False
            pending.extend((x[k], y[k]) for k in x)
            continue
        return False
    return True


def _order_cmp(op: str, a: Value, b: Value) -> Optional[bool]:
    if a is None or b is None:
        return None
    if _is_num(a) and _is_num(b):
        a, b = _as_float(a), _as_float(b)
    elif isinstance(a, str) and isinstance(b, str):
        pass
    else:
        return None
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    return a >= b


# ----------------------------------------------------------------------------------------
# Date helpers — strict ISO parsing, UTC-only, so Python and JS agree to the millisecond.
# ----------------------------------------------------------------------------------------
_DATE_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?"
    r"(Z|[+-]\d{2}:?\d{2})?)?$"
)


def _parse_date_ms(v: Value) -> Optional[Tuple[float, bool]]:
    """Parse a date/datetime string → (utc_epoch_ms, date_only). None if unparseable."""
    if not isinstance(v, str):
        return None
    m = _DATE_RE.match(v.strip())
    if not m:
        return None
    y, mo, d, hh, mm, ss, frac, off = m.groups()
    has_time = hh is not None
    try:
        dt = datetime(
            int(y), int(mo), int(d),
            int(hh) if hh else 0, int(mm) if mm else 0, int(ss) if ss else 0,
            int((frac or "0").ljust(6, "0")[:6]),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
    since_epoch = dt - _EPOCH
    if off and off != "Z":
        sign = 1 if off[0] == "+" else -1
        digits = off[1:].replace(":", "")
        # The offset moves the INSTANT, not the calendar datetime: subtracting it from the
        # datetime raised OverflowError for "0001-01-01T00:00:00+14:00", a real instant the JS
        # mirror and Postgres both compute. Exact microseconds either way, so every in-range
        # result is the same double it always was (dt.timestamp() IS (dt - _EPOCH).total_seconds()).
        since_epoch -= timedelta(minutes=sign * (int(digits[:2]) * 60 + int(digits[2:4])))
    return since_epoch.total_seconds() * 1000.0, (not has_time)


def _format_date_ms(ms: float, date_only: bool) -> Optional[str]:
    # Total: an out-of-range result (data-driven date_add past year 1..9999) → None, not a
    # raised ValueError/OverflowError. Year is zero-padded manually (glibc strftime('%Y')
    # does NOT pad, which would emit a malformed '1-01-01').
    try:
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
    if date_only:
        return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
    return (f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
            f"T{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}Z")


def _now_ms(ctx: Dict[str, Any]) -> float:
    injected = ctx.get("now") if ctx else None
    if isinstance(injected, str):
        parsed = _parse_date_ms(injected)
        if parsed is not None:
            return parsed[0]
    if _is_num(injected):
        return _as_float(injected)
    return datetime.now(timezone.utc).timestamp() * 1000.0


# ----------------------------------------------------------------------------------------
# Whitelisted functions. Each: (args: list, ctx: dict) -> Value. Args are pre-evaluated.
# ----------------------------------------------------------------------------------------
def _as_list(args: List[Value]) -> List[Value]:
    """count/sum/avg/min/max accept either one list arg or several scalar args."""
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        return list(args[0])
    return args


def _fn_days_between(args, ctx):
    if len(args) != 2:
        return None
    a, b = _parse_date_ms(args[0]), _parse_date_ms(args[1])
    if a is None or b is None:
        return None
    return (b[0] - a[0]) / MS_PER_DAY


def _fn_date_add(args, ctx):
    if len(args) != 2:
        return None
    base = _parse_date_ms(args[0])
    n = _to_num(args[1])
    if base is None or n is None:
        return None
    return _format_date_ms(base[0] + n * MS_PER_DAY, date_only=base[1])


#: The zone names ``time_of_day`` accepts: exactly these, case and all. The same list is held
#: by the JS mirror and pinned by ``tests/fixtures/expr_vectors.json`` (``time_zones``), so the
#: two runtimes accept the same names. It is ``UTC`` and every IANA ``Area/Place`` name
#: (``Etc/GMT+12`` is UTC-12: the sign of an ``Etc/GMT`` name runs backwards); never a POSIX rule
#: (``EST5EDT``, ``+05:30``) nor a host file (``localtime``, ``posixrules``), which each runtime
#: reads its own way. What each zone's clock SAYS comes from each runtime's own time-zone data.
TIME_ZONES = frozenset({
    "Africa/Abidjan", "Africa/Accra", "Africa/Addis_Ababa", "Africa/Algiers", "Africa/Asmara",
    "Africa/Bamako", "Africa/Bangui", "Africa/Banjul", "Africa/Bissau", "Africa/Blantyre",
    "Africa/Brazzaville", "Africa/Bujumbura", "Africa/Cairo", "Africa/Casablanca", "Africa/Ceuta",
    "Africa/Conakry", "Africa/Dakar", "Africa/Dar_es_Salaam", "Africa/Djibouti", "Africa/Douala",
    "Africa/El_Aaiun", "Africa/Freetown", "Africa/Gaborone", "Africa/Harare", "Africa/Johannesburg",
    "Africa/Juba", "Africa/Kampala", "Africa/Khartoum", "Africa/Kigali", "Africa/Kinshasa",
    "Africa/Lagos", "Africa/Libreville", "Africa/Lome", "Africa/Luanda", "Africa/Lubumbashi",
    "Africa/Lusaka", "Africa/Malabo", "Africa/Maputo", "Africa/Maseru", "Africa/Mbabane",
    "Africa/Mogadishu", "Africa/Monrovia", "Africa/Nairobi", "Africa/Ndjamena", "Africa/Niamey",
    "Africa/Nouakchott", "Africa/Ouagadougou", "Africa/Porto-Novo", "Africa/Sao_Tome", "Africa/Timbuktu",
    "Africa/Tripoli", "Africa/Tunis", "Africa/Windhoek", "America/Adak", "America/Anchorage",
    "America/Anguilla", "America/Antigua", "America/Araguaina", "America/Argentina/Buenos_Aires", "America/Argentina/Catamarca",
    "America/Argentina/Cordoba", "America/Argentina/Jujuy", "America/Argentina/La_Rioja", "America/Argentina/Mendoza", "America/Argentina/Rio_Gallegos",
    "America/Argentina/Salta", "America/Argentina/San_Juan", "America/Argentina/San_Luis", "America/Argentina/Tucuman", "America/Argentina/Ushuaia",
    "America/Aruba", "America/Asuncion", "America/Atikokan", "America/Atka", "America/Bahia",
    "America/Bahia_Banderas", "America/Barbados", "America/Belem", "America/Belize", "America/Blanc-Sablon",
    "America/Boa_Vista", "America/Bogota", "America/Boise", "America/Cambridge_Bay", "America/Campo_Grande",
    "America/Cancun", "America/Caracas", "America/Cayenne", "America/Cayman", "America/Chicago",
    "America/Chihuahua", "America/Ciudad_Juarez", "America/Coral_Harbour", "America/Costa_Rica", "America/Coyhaique",
    "America/Creston", "America/Cuiaba", "America/Curacao", "America/Danmarkshavn", "America/Dawson",
    "America/Dawson_Creek", "America/Denver", "America/Detroit", "America/Dominica", "America/Edmonton",
    "America/Eirunepe", "America/El_Salvador", "America/Ensenada", "America/Fort_Nelson", "America/Fortaleza",
    "America/Glace_Bay", "America/Goose_Bay", "America/Grand_Turk", "America/Grenada", "America/Guadeloupe",
    "America/Guatemala", "America/Guayaquil", "America/Guyana", "America/Halifax", "America/Havana",
    "America/Hermosillo", "America/Indiana/Indianapolis", "America/Indiana/Knox", "America/Indiana/Marengo", "America/Indiana/Petersburg",
    "America/Indiana/Tell_City", "America/Indiana/Vevay", "America/Indiana/Vincennes", "America/Indiana/Winamac", "America/Inuvik",
    "America/Iqaluit", "America/Jamaica", "America/Juneau", "America/Kentucky/Louisville", "America/Kentucky/Monticello",
    "America/Kralendijk", "America/La_Paz", "America/Lima", "America/Los_Angeles", "America/Lower_Princes",
    "America/Maceio", "America/Managua", "America/Manaus", "America/Marigot", "America/Martinique",
    "America/Matamoros", "America/Mazatlan", "America/Menominee", "America/Merida", "America/Metlakatla",
    "America/Mexico_City", "America/Miquelon", "America/Moncton", "America/Monterrey", "America/Montevideo",
    "America/Montreal", "America/Montserrat", "America/Nassau", "America/New_York", "America/Nipigon",
    "America/Nome", "America/Noronha", "America/North_Dakota/Beulah", "America/North_Dakota/Center", "America/North_Dakota/New_Salem",
    "America/Nuuk", "America/Ojinaga", "America/Panama", "America/Pangnirtung", "America/Paramaribo",
    "America/Phoenix", "America/Port-au-Prince", "America/Port_of_Spain", "America/Porto_Acre", "America/Porto_Velho",
    "America/Puerto_Rico", "America/Punta_Arenas", "America/Rainy_River", "America/Rankin_Inlet", "America/Recife",
    "America/Regina", "America/Resolute", "America/Rio_Branco", "America/Santa_Isabel", "America/Santarem",
    "America/Santiago", "America/Santo_Domingo", "America/Sao_Paulo", "America/Scoresbysund", "America/Shiprock",
    "America/Sitka", "America/St_Barthelemy", "America/St_Johns", "America/St_Kitts", "America/St_Lucia",
    "America/St_Thomas", "America/St_Vincent", "America/Swift_Current", "America/Tegucigalpa", "America/Thule",
    "America/Thunder_Bay", "America/Tijuana", "America/Toronto", "America/Tortola", "America/Vancouver",
    "America/Virgin", "America/Whitehorse", "America/Winnipeg", "America/Yakutat", "America/Yellowknife",
    "Antarctica/Casey", "Antarctica/Davis", "Antarctica/DumontDUrville", "Antarctica/Macquarie", "Antarctica/Mawson",
    "Antarctica/McMurdo", "Antarctica/Palmer", "Antarctica/Rothera", "Antarctica/Syowa", "Antarctica/Troll",
    "Antarctica/Vostok", "Arctic/Longyearbyen", "Asia/Aden", "Asia/Almaty", "Asia/Amman",
    "Asia/Anadyr", "Asia/Aqtau", "Asia/Aqtobe", "Asia/Ashgabat", "Asia/Atyrau",
    "Asia/Baghdad", "Asia/Bahrain", "Asia/Baku", "Asia/Bangkok", "Asia/Barnaul",
    "Asia/Beirut", "Asia/Bishkek", "Asia/Brunei", "Asia/Chita", "Asia/Choibalsan",
    "Asia/Chongqing", "Asia/Colombo", "Asia/Damascus", "Asia/Dhaka", "Asia/Dili",
    "Asia/Dubai", "Asia/Dushanbe", "Asia/Famagusta", "Asia/Gaza", "Asia/Harbin",
    "Asia/Hebron", "Asia/Ho_Chi_Minh", "Asia/Hong_Kong", "Asia/Hovd", "Asia/Irkutsk",
    "Asia/Istanbul", "Asia/Jakarta", "Asia/Jayapura", "Asia/Jerusalem", "Asia/Kabul",
    "Asia/Kamchatka", "Asia/Karachi", "Asia/Kashgar", "Asia/Kathmandu", "Asia/Khandyga",
    "Asia/Kolkata", "Asia/Krasnoyarsk", "Asia/Kuala_Lumpur", "Asia/Kuching", "Asia/Kuwait",
    "Asia/Macau", "Asia/Magadan", "Asia/Makassar", "Asia/Manila", "Asia/Muscat",
    "Asia/Nicosia", "Asia/Novokuznetsk", "Asia/Novosibirsk", "Asia/Omsk", "Asia/Oral",
    "Asia/Phnom_Penh", "Asia/Pontianak", "Asia/Pyongyang", "Asia/Qatar", "Asia/Qostanay",
    "Asia/Qyzylorda", "Asia/Riyadh", "Asia/Sakhalin", "Asia/Samarkand", "Asia/Seoul",
    "Asia/Shanghai", "Asia/Singapore", "Asia/Srednekolymsk", "Asia/Taipei", "Asia/Tashkent",
    "Asia/Tbilisi", "Asia/Tehran", "Asia/Tel_Aviv", "Asia/Thimphu", "Asia/Tokyo",
    "Asia/Tomsk", "Asia/Ulaanbaatar", "Asia/Urumqi", "Asia/Ust-Nera", "Asia/Vientiane",
    "Asia/Vladivostok", "Asia/Yakutsk", "Asia/Yangon", "Asia/Yekaterinburg", "Asia/Yerevan",
    "Atlantic/Azores", "Atlantic/Bermuda", "Atlantic/Canary", "Atlantic/Cape_Verde", "Atlantic/Faroe",
    "Atlantic/Jan_Mayen", "Atlantic/Madeira", "Atlantic/Reykjavik", "Atlantic/South_Georgia", "Atlantic/St_Helena",
    "Atlantic/Stanley", "Australia/Adelaide", "Australia/Brisbane", "Australia/Broken_Hill", "Australia/Canberra",
    "Australia/Currie", "Australia/Darwin", "Australia/Eucla", "Australia/Hobart", "Australia/Lindeman",
    "Australia/Lord_Howe", "Australia/Melbourne", "Australia/Perth", "Australia/Sydney", "Australia/Yancowinna",
    "Etc/GMT", "Etc/GMT+0", "Etc/GMT+1", "Etc/GMT+10", "Etc/GMT+11",
    "Etc/GMT+12", "Etc/GMT+2", "Etc/GMT+3", "Etc/GMT+4", "Etc/GMT+5",
    "Etc/GMT+6", "Etc/GMT+7", "Etc/GMT+8", "Etc/GMT+9", "Etc/GMT-0",
    "Etc/GMT-1", "Etc/GMT-10", "Etc/GMT-11", "Etc/GMT-12", "Etc/GMT-13",
    "Etc/GMT-14", "Etc/GMT-2", "Etc/GMT-3", "Etc/GMT-4", "Etc/GMT-5",
    "Etc/GMT-6", "Etc/GMT-7", "Etc/GMT-8", "Etc/GMT-9", "Etc/GMT0",
    "Etc/Greenwich", "Etc/UCT", "Etc/UTC", "Etc/Universal", "Etc/Zulu",
    "Europe/Amsterdam", "Europe/Andorra", "Europe/Astrakhan", "Europe/Athens", "Europe/Belfast",
    "Europe/Belgrade", "Europe/Berlin", "Europe/Bratislava", "Europe/Brussels", "Europe/Bucharest",
    "Europe/Budapest", "Europe/Busingen", "Europe/Chisinau", "Europe/Copenhagen", "Europe/Dublin",
    "Europe/Gibraltar", "Europe/Guernsey", "Europe/Helsinki", "Europe/Isle_of_Man", "Europe/Istanbul",
    "Europe/Jersey", "Europe/Kaliningrad", "Europe/Kirov", "Europe/Kyiv", "Europe/Lisbon",
    "Europe/Ljubljana", "Europe/London", "Europe/Luxembourg", "Europe/Madrid", "Europe/Malta",
    "Europe/Mariehamn", "Europe/Minsk", "Europe/Monaco", "Europe/Moscow", "Europe/Nicosia",
    "Europe/Oslo", "Europe/Paris", "Europe/Podgorica", "Europe/Prague", "Europe/Riga",
    "Europe/Rome", "Europe/Samara", "Europe/San_Marino", "Europe/Sarajevo", "Europe/Saratov",
    "Europe/Simferopol", "Europe/Skopje", "Europe/Sofia", "Europe/Stockholm", "Europe/Tallinn",
    "Europe/Tirane", "Europe/Tiraspol", "Europe/Ulyanovsk", "Europe/Vaduz", "Europe/Vatican",
    "Europe/Vienna", "Europe/Vilnius", "Europe/Volgograd", "Europe/Warsaw", "Europe/Zagreb",
    "Europe/Zurich", "Indian/Antananarivo", "Indian/Chagos", "Indian/Christmas", "Indian/Cocos",
    "Indian/Comoro", "Indian/Kerguelen", "Indian/Mahe", "Indian/Maldives", "Indian/Mauritius",
    "Indian/Mayotte", "Indian/Reunion", "Pacific/Apia", "Pacific/Auckland", "Pacific/Bougainville",
    "Pacific/Chatham", "Pacific/Chuuk", "Pacific/Easter", "Pacific/Efate", "Pacific/Fakaofo",
    "Pacific/Fiji", "Pacific/Funafuti", "Pacific/Galapagos", "Pacific/Gambier", "Pacific/Guadalcanal",
    "Pacific/Guam", "Pacific/Honolulu", "Pacific/Johnston", "Pacific/Kanton", "Pacific/Kiritimati",
    "Pacific/Kosrae", "Pacific/Kwajalein", "Pacific/Majuro", "Pacific/Marquesas", "Pacific/Midway",
    "Pacific/Nauru", "Pacific/Niue", "Pacific/Norfolk", "Pacific/Noumea", "Pacific/Pago_Pago",
    "Pacific/Palau", "Pacific/Pitcairn", "Pacific/Pohnpei", "Pacific/Port_Moresby", "Pacific/Rarotonga",
    "Pacific/Saipan", "Pacific/Samoa", "Pacific/Tahiti", "Pacific/Tarawa", "Pacific/Tongatapu",
    "Pacific/Wake", "Pacific/Wallis", "Pacific/Yap", "UTC",
})


def _fn_time_of_day(args, ctx):
    """``time_of_day(t, zone)``: the time a wall clock in ``zone`` shows at the instant ``t``, as
    whole seconds since that clock's midnight (0..86399; a fraction of a second is dropped).

    Null when ``t`` is not a date-time this language reads, when it is a bare date (a date has
    no time of day), when ``zone`` is not in :data:`TIME_ZONES`, and when the instant or the
    clock's date falls outside years 1..9999. On a day the clocks go back, both readings of 1:30 are 5400.
    """
    if len(args) != 2:
        return None
    zone = args[1]
    if not isinstance(zone, str) or zone not in TIME_ZONES:
        return None
    parsed = _parse_date_ms(args[0])
    if parsed is None or parsed[1]:
        return None
    try:
        clock = datetime.fromtimestamp(math.floor(parsed[0] / 1000.0), ZoneInfo(zone))
    except (ValueError, OverflowError, OSError, ZoneInfoNotFoundError):
        return None
    return float(clock.hour * 3600 + clock.minute * 60 + clock.second)


def _fn_contains(args, ctx):
    if len(args) != 2:
        return None
    hay, needle = args[0], args[1]
    if hay is None:
        return False
    if isinstance(hay, (list, tuple)):
        return any(_eq(needle, x) for x in hay)
    hs, ns = _to_str(hay), _to_str(needle)
    if hs is None or ns is None:
        return False
    return ns in hs


def _fn_reduce(op, args):
    nums = [n for n in (_to_num(x) for x in _as_list(args)) if n is not None]
    if not nums:
        return None
    if op == "sum":
        return _finite(sum(nums))
    if op == "avg":
        return _finite(sum(nums) / len(nums))
    if op == "min":
        return min(nums)
    if op == "max":
        return max(nums)
    return None


def _fn_round(args, ctx):
    x = _to_num(args[0]) if args else None
    if x is None:
        return None
    ndig = int(_to_num(args[1])) if len(args) > 1 and _to_num(args[1]) is not None else 0
    # Past 308 the factor is no double, whatever x is; and 10 ** ndig is an EXACT int, so
    # round(1, 1e9) would build a ~415 MB integer before failing. Null, without computing it.
    if ndig > 308:
        return None
    # Canonical rule: round half AWAY from zero (the JS mirror implements the same, rather
    # than JS's Math.round which rounds half toward +Infinity) so both runtimes agree.
    factor = 10 ** ndig
    scaled = x * factor
    if not math.isfinite(scaled):          # round(1.7e296, 20): x * factor overflowed
        return None
    r = float((-1 if scaled < 0 else 1)) * int(abs(scaled) + 0.5)
    if factor == 0:                        # round(x, -324): 10 ** -324 underflows to 0.0
        return None
    return _finite(r / factor)


_FUNCTIONS = {
    "today": lambda args, ctx: _format_date_ms(_now_ms(ctx), date_only=True),
    "now": lambda args, ctx: _format_date_ms(_now_ms(ctx), date_only=False),
    "days_between": _fn_days_between,
    "date_add": _fn_date_add,
    "time_of_day": _fn_time_of_day,
    "coalesce": lambda args, ctx: next((a for a in args if a is not None), None),
    "if": None,  # special form (lazy) — handled in _eval, listed here so parse accepts it
    "lower": lambda args, ctx: (_to_str(args[0]).lower() if args and _to_str(args[0]) is not None else None),
    "upper": lambda args, ctx: (_to_str(args[0]).upper() if args and _to_str(args[0]) is not None else None),
    "contains": _fn_contains,
    "number": lambda args, ctx: (_to_num(args[0]) if args else None),
    "string": lambda args, ctx: (_to_str(args[0]) if args else None),
    "concat": lambda args, ctx: "".join(_to_str(a) or "" for a in args),
    "length": lambda args, ctx: (len(args[0]) if args and isinstance(args[0], (str, list, tuple, dict)) else None),
    "abs": lambda args, ctx: (abs(_to_num(args[0])) if args and _to_num(args[0]) is not None else None),
    "floor": lambda args, ctx: (float(math.floor(_to_num(args[0]))) if args and _to_num(args[0]) is not None else None),
    "ceil": lambda args, ctx: (float(math.ceil(_to_num(args[0]))) if args and _to_num(args[0]) is not None else None),
    "round": _fn_round,
    "count": lambda args, ctx: float(sum(1 for x in _as_list(args) if x is not None)),
    "sum": lambda args, ctx: _fn_reduce("sum", args),
    "avg": lambda args, ctx: _fn_reduce("avg", args),
    "min": lambda args, ctx: _fn_reduce("min", args),
    "max": lambda args, ctx: _fn_reduce("max", args),
}

#: Sorted names of every whitelisted function (for the dashboard builder catalog).
FUNCTION_NAMES = sorted(_FUNCTIONS)


# ----------------------------------------------------------------------------------------
# Evaluator
# ----------------------------------------------------------------------------------------
def _resolve_field(record: Any, path: List[Tuple[str, Any]]) -> Value:
    cur: Any = record
    for kind, key in path:
        if kind == "key":
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return None
        else:  # index
            if isinstance(cur, (list, tuple)) and -len(cur) <= key < len(cur):
                cur = cur[key]
            else:
                return None
    return cur


def _eval(node: AST, record: Any, ctx: Dict[str, Any]) -> Value:
    tag = node[0]
    if tag == "num":
        return _finite(node[1])            # the literal 1e400 parses to inf: not a number here
    if tag == "str":
        return node[1]
    if tag == "bool":
        return node[1]
    if tag == "null":
        return None
    if tag == "field":
        return _resolve_field(record, node[1])
    if tag == "neg":
        n = _to_num(_eval(node[1], record, ctx))
        return None if n is None else -n
    if tag == "not":
        return not _truthy(_eval(node[1], record, ctx))
    if tag == "and":
        return _truthy(_eval(node[1], record, ctx)) and _truthy(_eval(node[2], record, ctx))
    if tag == "or":
        return _truthy(_eval(node[1], record, ctx)) or _truthy(_eval(node[2], record, ctx))
    if tag == "cmp":
        op = node[1]
        left = _eval(node[2], record, ctx)
        right = _eval(node[3], record, ctx)
        if op == "==":
            return _eq(left, right)
        if op == "!=":
            return not _eq(left, right)
        return _order_cmp(op, left, right)
    if tag == "bin":
        op = node[1]
        ln = _to_num(_eval(node[2], record, ctx))
        rn = _to_num(_eval(node[3], record, ctx))
        if ln is None or rn is None:
            return None
        if op == "+":
            return _finite(ln + rn)
        if op == "-":
            return _finite(ln - rn)
        if op == "*":
            return _finite(ln * rn)
        if op == "/":
            return None if rn == 0 else _finite(ln / rn)
        if op == "%":
            # math.fmod == C fmod == JS `%` (truncated remainder, sign of the dividend).
            return None if rn == 0 else math.fmod(ln, rn)
    if tag == "call":
        name = node[1]
        if name == "if":
            argsn = node[2]
            if len(argsn) != 3:
                return None
            cond = _truthy(_eval(argsn[0], record, ctx))
            return _eval(argsn[1] if cond else argsn[2], record, ctx)
        fn = _FUNCTIONS[name]
        args = [_eval(a, record, ctx) for a in node[2]]
        return fn(args, ctx)
    raise ExprError(f"Unknown AST node {tag!r}")  # pragma: no cover - parser guarantees tags


def evaluate(ast: AST, record: Any, context: Optional[Dict[str, Any]] = None) -> Value:
    """Evaluate a parsed AST against one record. Never raises for data reasons (→ null)."""
    return _eval(ast, record if record is not None else {}, context or {})


def evaluate_str(src: str, record: Any, context: Optional[Dict[str, Any]] = None) -> Value:
    """Convenience: parse + evaluate. Parsing may raise :class:`ExprError`."""
    return evaluate(parse(src), record, context)
