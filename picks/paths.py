"""picks/paths.py — how a field is named: its path (T-88).

A field is named by its path through a record, in the expression language's own spelling without
the leading ``$``: a key that is a plain identifier is written dotted (``payload.load``), and any
other key — one with a space, a bracket, a dot — in brackets as a quoted string
(``["Sample Weight (g)"]``, ``a["b c"].d``).  So every key a record can hold has one name, and the
statement side and the second engine read the same keys from it.

The quoted string is the expression language's, not JSON's (the T-88 check's HIGH): the language
reads a backslash and the character after it as that character, except ``\n``, ``\t`` and ``\r``
— so ``\b``, ``\f`` or ``\u0008`` would name ``b``, ``f`` or ``u0008``, another key.  A name
therefore escapes only the backslash, the quote, newline, tab and carriage return, and holds every
other character as itself.  A key Postgres text cannot hold (NUL) has no name.

* :func:`steps` — a path → its keys; ``ValueError`` for anything malformed, or for any spelling
  but the one :func:`of` gives (a hand-sent JSON escape, a needless bracket);
* :func:`of`    — keys → their path (the one spelling);
* :func:`dollar` — a path as the expression language reads it (``$.a.b``, ``$["x y"]``);
* :func:`name`  — keys → their path, or ``None`` when the registered parser would not read that
  path back as exactly these keys: such a key is not offered.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BRACKET = re.compile(r'\[("(?:[^"\\]|\\.)*")\]', re.S)
#: the escapes the expression language reads (demo/vendor/expr.py ``_decode_string``)
_ESCAPE = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t", "\r": "\\r"}
_UNESCAPE = {"n": "\n", "t": "\t", "r": "\r"}


def _quote(key: str) -> str:
    return '"' + "".join(_ESCAPE.get(ch, ch) for ch in key) + '"'


def _unquote(quoted: str) -> str:
    body, out, i = quoted[1:-1], [], 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            out.append(_UNESCAPE.get(body[i + 1], body[i + 1]))
            i += 2
        else:
            out.append(body[i])
            i += 1
    return "".join(out)


def steps(path: str) -> List[str]:
    """``"payload.load"`` → ``["payload", "load"]``; ``'["Sample Weight (g)"]'`` →
    ``["Sample Weight (g)"]``.  A leading ``$`` or ``$.`` is accepted."""
    if not isinstance(path, str):
        raise ValueError(f"a field path is text, not {path!r}")
    text = path[1:] if path.startswith("$") else path
    if text.startswith("."):
        text = text[1:]
    out: List[str] = []
    i, first = 0, True
    while i < len(text):
        if text[i] == "[":
            m = _BRACKET.match(text, i)
            if not m:
                raise ValueError(f"{path!r} is not a field path")
            key = _unquote(m.group(1))
            if not key:
                raise ValueError(f"{path!r} names an empty key")
            out.append(key)
            i = m.end()
        else:
            if not first:
                if text[i] != ".":
                    raise ValueError(f"{path!r} is not a field path")
                i += 1
            m = _IDENT.match(text, i)
            if not m:
                raise ValueError(f"{path!r} is not a field path")
            out.append(m.group(0))
            i = m.end()
        first = False
    if not out:
        raise ValueError(f"{path!r} names no field")
    if of(out) != text:
        raise ValueError(f"{path!r} is not this field's name; it is written {of(out)!r}")
    return out


def of(keys: Sequence[str]) -> str:
    """Keys → their one path: identifiers dotted, any other key bracketed."""
    out = ""
    for k in keys:
        if not isinstance(k, str) or not k:
            raise ValueError(f"a key is non-empty text, not {k!r}")
        if "\x00" in k:
            raise ValueError("a key holding NUL cannot be named (Postgres text cannot hold it)")
        if _IDENT.fullmatch(k):
            out += ("." if out else "") + k
        else:
            out += "[" + _quote(k) + "]"
    return out


def dollar(path: str) -> str:
    """A path as the expression language reads it: ``$.a.b`` or ``$["x y"].z``."""
    p = of(steps(path))
    return "$" + ("" if p.startswith("[") else ".") + p


def name(keys: Sequence[str]) -> Optional[str]:
    """Keys → their path, only if both engines will read exactly these keys by it: the path parses
    back through :func:`steps` and through the registered parser (the one the statement compiles
    with and the second engine evaluates with) to these keys and nothing else.  ``None`` — the key
    is not offered — for an empty key, a NUL, or any name a parser would read another way."""
    try:
        path = of(keys)
        if steps(path) != list(keys):
            return None
        from . import env
        for role in ("parser", "evaluator"):
            ast = env.get(role).parse(dollar(path))
            if not (isinstance(ast, tuple) and ast[0] == "field"
                    and [tuple(s) for s in ast[1]] == [("key", k) for k in keys]):
                return None
    except Exception:  # noqa: BLE001 — a name any reader refuses is no name
        return None
    return path
