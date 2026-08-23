# T-2 · auto-review round 2 — regression review of the 16-fix diff

Scope: `git diff 8bb9018..HEAD`, 14 files, 2,951 insertions / 127 deletions. Round 1's findings were
already independently verified fixed, so round 2 looked at the thing nobody had examined: **what the
fixes broke or introduced**, with five workers editing one tree concurrently.

Method: all 14 files read, the full suite run (**624 passed, 10 skipped, 0 failed**), and **~45
crafted live requests** against the running stack. Never touched port 55433.

**Two findings. The rest of the fix work verified sound.**

---

## FINDING 1 — [MEDIUM] Six malformed picks still return a bare HTTP 500, and the new guard test cannot see them

`demo/legality.py::shape_violations` — added by the round-1 fix — validates only the **outer holder
type** of each slot: that `aggregate`/`window`/`sort` are objects, `computed` a list, each
`computed[i]` an object. **It never checks the inner value.** So these pass shape validation, pass
legality, and then crash unhandled:

- `aggregate.field` a list or dict → `builder.py:372`, `if field in self.cc_frag:` → `TypeError: unhashable type`
- `window.field` a list or dict → same site
- `computed[i].name` a list or dict → `app.py:733`, `aliases = {cc.get("name") …}` → `TypeError: unhashable type`

**Reproduced live**, six inputs, each a bare 500 with body `Internal Server Error`:

```
POST /api/pick {"pick":{"source":"noun:Heartbeat","aggregate":{"fn":"sum","field":{"a":1}}}}      -> 500
POST /api/pick {"pick":{"source":"noun:Heartbeat","aggregate":{"fn":"sum","field":["x"]}}}        -> 500
POST /api/pick {"pick":{"source":"noun:Heartbeat","window":{"field":{"a":1}}}}                    -> 500
POST /api/pick {"pick":{"source":"noun:Heartbeat","window":{"field":["x"]}}}                      -> 500
POST /api/pick {"pick":{"source":"noun:Heartbeat","computed":[{"name":["a"],"expr":"$.priority"}]}}  -> 500
POST /api/pick {"pick":{"source":"noun:Heartbeat","computed":[{"name":{"x":1},"expr":"$.priority"}]}} -> 500
```

`sort.field` of the wrong type is **safe** (422) — the sort path hits `_field_path`'s `isinstance`
check via list-membership before any dict-membership test. That asymmetry is exactly why
`aggregate`/`window` still crash and `sort` does not.

**Why this is a round-2 finding and not a repeat of round 1.** The new guard test
`test_vendor.py::test_a_malformed_pick_shape_is_a_named_refusal_not_a_500` parametrizes
`_MALFORMED_PICKS` — **the six holder-type shapes round 1 had already named**, all now correctly 422.
It tests none of the inner-value cases, so **it passes green while the six inputs above still 500.**
That is the same structural blindness round 1 flagged for the AC-32 guard — *"structurally incapable
of failing on the file that actually breaks the promise"* — **reproduced inside the test that was
written to close that very finding.**

`/api/operations` does not share the crash (it never builds SQL), so this is `/api/pick`-only and not
reachable from the screen.

---

## FINDING 2 — [LOW, latent] The serving-layer font strip is bypassable by non-canonical request paths

`app.py`'s `/vendor/styles/{name}.css` route runs `offline_css` and is registered before the
`/vendor` StaticFiles mount, so the **canonical** path is stripped correctly (verified: served bytes
carry no `fonts.googleapis.com`). But the explicit route matches one literal spelling. Every other
spelling that resolves to the same file falls through to the raw mount and is served **verbatim, with
the live `@import url('https://fonts.googleapis.com/…')` intact.** Confirmed live:

```
/vendor/./styles/watery.css          /vendor//styles/watery.css
/vendor/styles/../styles/watery.css  /vendor/styles/%2e%2e/styles/watery.css
/vendor/styles/watery.css/           (trailing slash)
```

**Honest scope: this is NOT a live AC-32 violation.** `index.html` links the canonical path, and
browsers normalise dot-segments and doubled slashes before sending, so the page as served never
requests a bypass path. The AC-32 walk test is genuine — it follows the real links the page emits and
asserts the served bytes are clean — but it only ever reaches the canonical path, so it cannot see
this. The fix's own stated guarantee (*"the bytes on the wire carry nothing that leaves this
machine"*) is nonetheless false for non-canonical paths. A future link with a trailing slash, a
fronting proxy, or GIMS integration referencing the sheet differently would leak.

---

## Checked and found genuinely SOUND

- **Empty-array ordering (round-1 HIGH):** correct end to end. The exact round-1 reproduction pick now
  returns **verdict=agree, 0 differing** in both directions, live. The new unit tests assert against
  the **live engine** over all pairs rather than the spec table, with a guard that the probe still
  exercises `'[]' < 'null'` — not tautological.
- **Named refusals:** `1e400` → layer-1 named refusal, construct `"inf"`. `$.g*$.g` on EdgeCase →
  layer-2 named refusal, construct `"float8 overflow"`, SQLSTATE 22003, **the Python pane still
  answers and the next pick is unharmed.** Both reachable and named.
- **The read-only guard:** genuinely refuses a write on the pick's **own** transaction
  (`transaction_read_only=on`, UPDATE → SQLSTATE 25006). A subtlety was found and is already handled:
  `SET SESSION CHARACTERISTICS` is reverted by any rollback, and the one mid-pick rollback path
  (float8 overflow) explicitly re-arms it. Sound, not a finding.
- **CSS integrity:** `demo/vendor/styles/watery.css` on disk is byte-identical to its manifest digest
  (`684dc2cc…`). The rewriter leaves `data:`, `about:` and relative URLs alone; only the one off-host
  reference is touched. No corruption path.
- **`run-demo` shell (~550 new lines):** exit handling is careful — `set +e`/status-capture around
  pytest and the summary, no pipefail-swallowed failure. **Every path expansion is quoted**, which
  matters in a repo whose whole history with this tooling is path-with-a-space bugs. The
  `pid_is_our_app` four-predicate identity check matches the actual running app's cmdline and
  correctly distinguishes it from the machine's four other unrelated uvicorns. The readiness poll now
  routes through `db.connect()`, and every boundary contract it depends on exists — the concurrent
  edits are consistent across that boundary.
- **Tests:** round-1's `or True` tautology is gone; the permanent `run=False` xfail is replaced with
  real executing tests.

EVIDENCE: round-2 regression review of branch feat/T-2-demo, diff 8bb9018..HEAD (14 files, 2,951 insertions) — full suite 624 passed / 10 skipped / 0 failed, ~45 crafted live requests; 2 findings (six inner-value malformed picks still returning bare 500s with a guard test structurally unable to see them; the font strip bypassable at non-canonical request spellings, latent rather than live); the ordering fix, both named refusals, the read-only guard including its rollback subtlety, CSS disk/digest integrity and the run-demo shell each verified sound
