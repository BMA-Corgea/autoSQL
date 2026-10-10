"""picks/paths.py — how a field is named: its path (T-88).

A field is named by its path through a record, in the expression language's own spelling without
the leading ``$``: a key that is a plain identifier is written dotted (``payload.load``), and any
other key — one with a space, a bracket, a dot — in brackets as a JSON string
(``["Sample Weight (g)"]``, ``a["b c"].d``).  So every key a record can hold has one name, and the
statement side and the second engine read the same keys from it.

* :func:`steps` — a path → its keys, or ``ValueError`` for anything malformed;
* :func:`of`    — keys → their path (the one spelling);
* :func:`dollar` — a path as the expression language reads it (``$.a.b``, ``$["x y"]``).
"""

from __future__ import annotations

import json
import re
from typing import List, Sequence

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BRACKET = re.compile(r'\[("(?:[^"\\]|\\.)*")\]')


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
            key = json.loads(m.group(1))
            if not isinstance(key, str) or not key:
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
    return out


def of(keys: Sequence[str]) -> str:
    """Keys → their one path: identifiers dotted, any other key bracketed."""
    out = ""
    for k in keys:
        if not isinstance(k, str) or not k:
            raise ValueError(f"a key is non-empty text, not {k!r}")
        if _IDENT.fullmatch(k):
            out += ("." if out else "") + k
        else:
            out += "[" + json.dumps(k, ensure_ascii=False) + "]"
    return out


def dollar(path: str) -> str:
    """A path as the expression language reads it: ``$.a.b`` or ``$["x y"].z``."""
    p = of(steps(path))
    return "$" + ("" if p.startswith("[") else ".") + p
