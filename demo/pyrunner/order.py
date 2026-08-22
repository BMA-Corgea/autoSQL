"""§7.4's comparator, written out — T-2 spec §7.4 (ruling R12), plan §4.5.

Every Python sort in this demo goes through ``sort_key`` (plan §4.5: "every
Python sort").  Nothing here is idiom; every line implements a sentence of
spec §7.4, and the sentences it implements are cited inline.

The three decisions a build gets wrong, pinned here
---------------------------------------------------
1. **Two kinds of null** (§7.4(1b)).  An *absent* key is SQL ``NULL`` — the
   thing ``NULLS LAST`` governs — and is represented here by the sentinel
   ``MISSING``.  A key that is *present and holds JSON null* is
   ``'null'::jsonb``, a real value that sorts below every other jsonb value,
   and is represented by Python ``None``.  They are never merged: an
   ascending sort has three bands — JSON nulls, then everything else by the
   type table, then the absent-key rows — and a descending sort keeps the
   absent band last (``NULLS LAST`` is unconditional, §7.4(1)) while the
   present values invert.

2. **Text is byte order under the C collation** (§7.4(1b), §0).  The demo's
   database is created with ``--locale=C``, so every SQL text comparison is
   raw byte order.  Strings here are therefore compared as their UTF-8
   bytes.  (For the ASCII this demo's data and keys are made of, byte order
   and code-point order coincide — spec §0 "collation" — and UTF-8 byte
   order equals code-point order in general; encoding makes the rule
   explicit rather than inherited.)

3. **The tiebreak is `key ASC` whichever way the sort field runs**
   (§7.4(1a)), and the spec bans the idiom that breaks it: *"Never
   ``reverse=True`` over a tuple that contains ``key``."*  ``sort_key``
   therefore inverts direction *inside the value component only*: the
   returned tuple is ``(value-part, key-part)`` where only the value part
   ever flips.  A caller uses it as a plain ascending sort key and can not
   reproduce the reversed-tuple bug through this module.

The cross-type table (§7.4(1b)) both panes implement:

    Object > Array > Boolean > Number > String > Null
    two numbers   — numeric order
    two strings   — byte order under the C collation
    two booleans  — true > false
    two arrays    — longer is greater; equal lengths element by element
    two objects   — more pairs is greater; equal counts compare pair by
                    pair in Postgres's storage order (shorter keys before
                    longer, bytewise within one length): key-1, value-1,
                    key-2, value-2, …

On the object rule's fine print: the spec's sentence "compare key by key and
then value by value" is implemented as Postgres documents its own jsonb
btree order — *"Objects with equal numbers of pairs are compared in the
order: key-1, value-1, key-2 …"* — i.e. each pair's key then its value,
interleaved, not all keys first.  §7.4 says the table exists because
Postgres's ordering "is documented and finite, so it is written out here";
where the paraphrase is loose, the documented order it transcribes governs,
because the SQL pane's ``ORDER BY`` is real Postgres and the panes must not
be made to disagree by a paraphrase.  Recorded by W9 as a clarification, not
a departure.
"""

from decimal import Decimal

__all__ = ["MISSING", "compare_jsonb", "sort_key"]


class _Missing:
    """The absent-key sentinel: `data #> path` returned SQL NULL (§7.4(1b)).

    Distinct from None, which is JSON null.  A singleton; truth-value False
    so a careless `if value:` at least does not mistake it for data.
    """

    __slots__ = ()

    def __repr__(self):
        return "MISSING"

    def __bool__(self):
        return False


MISSING = _Missing()


# The cross-type rank, ascending: Object > Array > Boolean > Number > String
# > Null (§7.4(1b)), so Null is smallest.
_RANK_NULL = 0
_RANK_STRING = 1
_RANK_NUMBER = 2
_RANK_BOOLEAN = 3
_RANK_ARRAY = 4
_RANK_OBJECT = 5


def _type_rank(v):
    # bool MUST be tested before the number types: Python bool subclasses
    # int, and jsonb_typeof calls it 'boolean' (§7.2 item 5, plan B7).
    if v is None:
        return _RANK_NULL
    if isinstance(v, bool):
        return _RANK_BOOLEAN
    if isinstance(v, (int, float, Decimal)):
        return _RANK_NUMBER
    if isinstance(v, str):
        return _RANK_STRING
    if isinstance(v, (list, tuple)):
        return _RANK_ARRAY
    if isinstance(v, dict):
        return _RANK_OBJECT
    raise TypeError(f"not a jsonb value: {type(v).__name__} ({v!r})")


def _cmp(a, b):
    """Three-way compare of two already-comparable primitives."""
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _storage_order_pairs(obj):
    """An object's pairs in Postgres's storage order (§7.4(1b)):
    shorter keys before longer, bytewise within one length."""
    return sorted(obj.items(), key=lambda kv: (len(kv[0].encode("utf-8")), kv[0].encode("utf-8")))


def compare_jsonb(a, b):
    """Three-way compare of two *present* jsonb values under §7.4(1b)'s table.

    Returns -1, 0 or 1.  ``MISSING`` is not a jsonb value and is refused —
    the absent band is ``sort_key``'s business, because it is a property of
    the row (NULLS LAST), not of any value.
    """
    if a is MISSING or b is MISSING:
        raise TypeError("MISSING is not a jsonb value; absent keys are handled by sort_key()")
    ra = _type_rank(a)
    rb = _type_rank(b)
    if ra != rb:
        # different JSON types: Object > Array > Boolean > Number > String > Null
        return _cmp(ra, rb)
    if ra == _RANK_NULL:
        return 0
    if ra == _RANK_STRING:
        # byte order under the C collation (§7.4(1b), §0)
        return _cmp(a.encode("utf-8"), b.encode("utf-8"))
    if ra == _RANK_NUMBER:
        # numeric order.  int/Decimal/float cross-comparisons are exact in
        # Python 3; the Decimal parse (plan B7) means numbers arrive here as
        # int or Decimal, never lossy.
        return _cmp(a, b)
    if ra == _RANK_BOOLEAN:
        # true > false
        return _cmp(a, b)  # False < True is Python's bool order too
    if ra == _RANK_ARRAY:
        # the longer array is greater
        if len(a) != len(b):
            return _cmp(len(a), len(b))
        # equal lengths compare element by element under this same table
        for ea, eb in zip(a, b):
            c = compare_jsonb(ea, eb)
            if c:
                return c
        return 0
    # _RANK_OBJECT
    # the object with more pairs is greater
    if len(a) != len(b):
        return _cmp(len(a), len(b))
    # equal counts: pairs in storage order, compared key-1, value-1, key-2,
    # value-2, … (see the module docstring on this sentence).  Keys are
    # text, so they compare exactly as §7.4's table compares any text:
    # byte order under the C collation.
    for (ka, va), (kb, vb) in zip(_storage_order_pairs(a), _storage_order_pairs(b)):
        c = _cmp(ka.encode("utf-8"), kb.encode("utf-8"))
        if c:
            return c
        c = compare_jsonb(va, vb)
        if c:
            return c
    return 0


class _ValueKey:
    """One row's sort-field component, direction folded in.

    Ordering (ascending use of this object reproduces §7.4 exactly):

      * absent (MISSING) rows sort after every present value, in BOTH
        directions — NULLS LAST is unconditional (§7.4(1));
      * present values compare under §7.4(1b)'s table, inverted when the
        pick's direction is 'desc'.

    Only __lt__ and __eq__ are defined: Python's sorts use ``<`` alone, and
    tuple comparison additionally uses ``==``.  Nothing else is needed, and
    an unused operator is an untested one.
    """

    __slots__ = ("_value", "_sign")

    def __init__(self, value, sign):
        self._value = value
        self._sign = sign

    def __eq__(self, other):
        a_absent = self._value is MISSING
        b_absent = other._value is MISSING
        if a_absent or b_absent:
            return a_absent and b_absent
        return compare_jsonb(self._value, other._value) == 0

    def __lt__(self, other):
        a_absent = self._value is MISSING
        b_absent = other._value is MISSING
        if a_absent or b_absent:
            # NULLS LAST, unconditionally: a present value is less than (i.e.
            # sorts before) an absent one, and the sign never touches this.
            return b_absent and not a_absent
        return self._sign * compare_jsonb(self._value, other._value) < 0

    def __repr__(self):
        arrow = "asc" if self._sign == 1 else "desc"
        return f"_ValueKey({self._value!r}, {arrow})"


def sort_key(value, key, direction="asc"):
    """The total-order sort key for one row — §7.4, both halves, in one place.

    Arguments:
      value      the row's sort-field value: ``MISSING`` if the key is absent
                 from the record (this is also what a pick with no sort field
                 passes for every row, collapsing the order to `key ASC` —
                 §7.4(2)'s "with or without a sort field"), ``None`` if it is
                 present and holds JSON null, otherwise the parsed jsonb
                 value (numbers from the Decimal parse, plan B7).
      key        the record's ``key`` column — the tiebreak.  Unique within
                 a collection (§8.2), so the returned tuple is a total order.
      direction  'asc' or 'desc' — §4.4 row 7's closed set, nothing else.

    Returns a tuple ``(value-part, key-part)`` for use as an ASCENDING sort
    key (plain ``sorted(rows, key=...)``, no ``reverse=``):

      * the value part orders by §7.4(1b)'s table in the chosen direction,
        absent rows last regardless of direction;
      * the key part is the key's UTF-8 bytes — `key ASC` under the C
        collation, ALWAYS ascending whichever way the sort field runs
        (§7.4(1a)).  Direction never touches it, so the reversed-tuple bug
        (`reverse=True` flipping the tiebreak) cannot be expressed through
        this function.
    """
    if direction == "asc":
        sign = 1
    elif direction == "desc":
        sign = -1
    else:
        raise ValueError(f"direction must be 'asc' or 'desc', got {direction!r}")
    if not isinstance(key, str):
        raise TypeError(f"key must be str, got {type(key).__name__}")
    return (_ValueKey(value, sign), key.encode("utf-8"))
