"""demo/server — the FastAPI app (spec §9.1) and the demo's one connection.

Four modules, and the boundary each one owns:

* :mod:`demo.server.settings` — the compose-file constants and the two
  pinned session values, read from ``demo/compose.yaml`` so there is
  exactly one place they can drift from.
* :mod:`demo.server.db` — **the only connection factory in the tree**
  (plan §4.5, B13).  Nothing else in ``demo/`` imports the driver.
* :mod:`demo.server.errors` — the two refusal shapes §9.3 renders, as the
  JSON the screen is built from.  It defines no new exception: layer 1 is
  ``demo.gate.Refused`` and layer 2 is ``demo.probes.RuntimeRefusal``,
  each already raised by the file that owns the rule.
* :mod:`demo.server.app` — the routes: ``GET /``, ``GET /api/operations``
  (B22), ``GET /api/fields`` (§4.4 item 3) and ``POST /api/pick``.

:mod:`demo.server.operations` is W8's and is the single source of truth
for the nine controls; ``app`` serves it and invents nothing.
"""
