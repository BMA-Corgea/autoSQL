"""demo/gate.py — moved to ``picks/gate.py`` (T-86).

This name is the SAME module object as ``picks.gate``: an import of
``gate`` or ``demo.gate`` gets it, so a caller (or a test) that reads or
patches one reads or patches the other.  ``demo/picks_host.py`` registers
the demo's modules and records first.
"""

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import demo.picks_host  # noqa: E402,F401  (the host first)
import picks.gate as _moved  # noqa: E402

sys.modules[__name__] = _moved
