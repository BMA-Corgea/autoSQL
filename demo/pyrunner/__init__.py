"""demo/pyrunner — moved to ``picks/pyrunner/`` (T-86).

This package name, and each of its modules (``pyrunner.group``,
``demo.pyrunner.evaluate`` …), is the SAME module object as its
``picks.pyrunner`` counterpart, so a caller (or a test) that reads or patches
one reads or patches the other.  ``demo/picks_host.py`` registers the demo's
modules and records first.
"""

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import demo.picks_host  # noqa: E402,F401  (the host first)
import picks.pyrunner as _moved  # noqa: E402
from picks.pyrunner import decimals, evaluate, group, lookup, order, rows, shape  # noqa: E402,F401

for _sub in ("decimals", "evaluate", "group", "lookup", "order", "rows", "shape"):
    sys.modules[f"{__name__}.{_sub}"] = getattr(_moved, _sub)
sys.modules[__name__] = _moved
