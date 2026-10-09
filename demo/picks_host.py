"""demo/picks_host.py — the demo as a host of the pick engine (T-86).

The engine lives in ``picks/`` and is told two things by its host, once per
process: the modules it runs (the compiler, the expression parser and
evaluator, the probes' compiler) and the records it reads.  This module says
both for the demo, and is imported by every demo name that used to hold the
engine (``demo/legality.py``, ``demo/builder.py``, ``demo/pyrunner/`` …), so
whichever is imported first, the engine is ready.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from picks import env  # noqa: E402
from picks.records import Records  # noqa: E402


def _load_from_path(name: str, path: Path):
    """Import a single file under a stable module name, cached."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover — install defect
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: The modules, as the demo has always loaded them: the SHIPPING compiler,
#: the vendored parser the gate reads (AC-34), the second engine's own import
#: of the same vendored evaluator (spec §9.5), and the pinned T-1 compiler the
#: probes compile with (Q19: read only; AC-33 checksums it).
from demo.vendor import expr as _evaluator  # noqa: E402

env.use(
    compiler=_load_from_path("autosql_compile", _REPO_ROOT / "compiler" / "compile.py"),
    parser=_load_from_path("autosql_demo_expr", _REPO_ROOT / "demo" / "vendor" / "expr.py"),
    evaluator=_evaluator,
    probe_compiler=_load_from_path("t1_proto_compile", _REPO_ROOT / "spikes" / "T-1" / "proto" / "compile.py"),
)

#: The five collections (Senders since T-74, Sites since T-76), and each one's
#: top-level field vocabulary as a display string — what X1's reason states.
#: The seed is deterministic (plan §5), so these are constants of the build:
#:   noun:Heartbeat  plan §5.2's four fields
#:   noun:Sample     plan §5.3 / spec §4.10's list, as the approved mock
#:                   renders it
#:   noun:EdgeCase   the union of top-level keys over B24's ten pinned
#:                   rows, sorted as §4.4's key read sorts them.  The
#:                   mock drew five of these; B4 says the reason states
#:                   the collection's ACTUAL field list, so all sixteen
#:                   are stated (recorded in W8's report).
SOURCES: dict[str, str] = {
    "noun:Heartbeat": "sender_id, ts, status, payload",
    "noun:Sample": "id, status, due_date, priority, field_0 … field_14",
    "noun:EdgeCase": (
        "a, arr, d, g, huge, l, label, n, obj, present, "
        "s, t, tags, txt, where, z"
    ),
    # T-74: the senders' profiles, the parent the dashboard joins Heartbeats
    # to.  The two-pane screen still offers only the three above
    # (server/operations.py :: _SOURCE_OPTIONS, pinned by a test).
    "noun:Sender": "id, installed, kind, name, site",
    # T-76: the sites the senders name, and one none names — the level
    # above Senders a dashboard scoreboard can count across.  Not offered
    # on the two-pane screen either.
    "noun:Site": "capacity, name, opened",
}

#: The demo's records: one table, no owners, Heartbeats the time series
#: (``ts`` per ``sender_id``: operations 7-9, plan B4).
RECORDS = Records(
    table="demo.records",
    sources=SOURCES,
    series={"source": "noun:Heartbeat", "time": "ts", "member": "sender_id"},
    sources_note="the two-pane screen offers the first three",
)
env.set_default_records(RECORDS)
