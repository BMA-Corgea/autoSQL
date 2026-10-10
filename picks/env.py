"""picks/env.py — what the host supplies, once per process (T-86).

The pick engine does not carry the expression language or the compiler: the
host does, so the engine runs exactly the language its records were written
for.  Before any module of ``picks`` that needs them is imported, the host
calls :func:`use`:

* ``compiler`` — the compiler module (``compile_ast``, ``Compiled``,
  ``Uncompilable``): ``compiler/compile.py`` in this repo;
* ``parser`` — the expression module the statement side parses with (the
  gate reads its trees);
* ``evaluator`` — the expression module the second engine evaluates with
  (its own import, so the two engines never share an object).

The statement, its display and its probes are all written by that ONE
compiler (T-87), so a probe asks about an operand exactly as the statement
computes it.

and, optionally, :func:`set_default_records` — the :class:`Records` a call
uses when it is not handed one (a single-owner host such as the demo).
A host serving many owners passes ``records=`` on every call instead.
"""

from __future__ import annotations

from typing import Any, Optional

from .records import Records

_ENV: dict = {}
_DEFAULT: dict = {"records": None}

_NEEDED = ("compiler", "parser", "evaluator")


def use(*, compiler: Any, parser: Any, evaluator: Any) -> None:
    """Register the host's modules.  Calling it again with the same objects
    is a no-op; with different ones it is refused (modules already imported
    have bound the first)."""
    given = {"compiler": compiler, "parser": parser, "evaluator": evaluator}
    if _ENV and any(_ENV[k] is not given[k] for k in _NEEDED):
        raise RuntimeError("picks.env.use() was already called with other modules")
    _ENV.update(given)


def get(name: str) -> Any:
    if name not in _ENV:
        raise RuntimeError(
            f"picks needs the host's {name}: call picks.env.use(...) before importing the engine")
    return _ENV[name]


def set_default_records(records: Records) -> None:
    """The description a call reads when it is handed none — for a
    single-owner host.  A description with an owner (a partition) is
    refused: the default is process-wide, so a multi-owner host setting it
    per request would race one owner's request onto another's records; such
    a host passes ``records=`` on every call (T-87)."""
    if not isinstance(records, Records):
        raise TypeError("set_default_records takes a picks.records.Records")
    if records.partition is not None:
        raise ValueError("a default description cannot carry an owner: pass records= on every call instead")
    _DEFAULT["records"] = records


def records(given: Optional[Records] = None) -> Records:
    """The description a call reads: the one it was handed, else the
    process default, else a refusal (never a silent guess)."""
    if given is not None:
        return given
    if _DEFAULT["records"] is None:
        raise RuntimeError("no records description: pass records= or call picks.env.set_default_records()")
    return _DEFAULT["records"]
