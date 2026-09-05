# autoSQL — setting up on a new machine

This repo is AutoDev-enrolled. The repo carries the **what** (your shop, your
gates, your tickets, your KB); the AutoDev **plugin** carries the **how** (what
each pipeline stage actually does). You need both.

Nothing here is optional except step 5.

---

## 1. Install the AutoDev plugin

The plugin repo is its own Claude Code marketplace, so this is two commands
inside `claude`:

```
/plugin marketplace add RShuken/autodev-plugin
/plugin install autodev@autodev-marketplace
```

### Pinning the version (recommended)

This repo's tickets pin themselves to pipeline versions — `T-1` pins
`spike@v2`, whose stages (`sp-frame@v1` … `sp-spawn@v2`) are defined
**plugin-side**, not here. Installing from the marketplace gets you *latest*,
which may have moved on. To match the machine this repo was built on:

```bash
git clone https://github.com/RShuken/autodev-plugin.git ~/autodev-plugin
cd ~/autodev-plugin && git checkout 11418ba   # v0.53.0
```

Then in `claude`, add that directory as the marketplace instead:

```
/plugin marketplace add ~/autodev-plugin
/plugin install autodev@autodev-marketplace
```

> Alternative — **vendored mode**: `./install.sh /path/to/autoSQL` copies the
> engine into `.autodev/engine/` so it lives in this repo's own git history and
> no plugin install is needed. Pick one mode per repo; running both doubles
> every hook and skill.

## 2. Clone this repo

```bash
git clone <this repo url> autoSQL
cd autoSQL
```

## 3. Check the wiring before trusting anything

```
/autodev:doctor
```

The check that matters most here is **`data.pins`** — it should read
*"all N ticket(s) resolve at their pinned versions."* If it doesn't, your
plugin version doesn't carry a pipeline this repo's tickets are pinned to;
go back to step 1 and pin the commit.

Two warnings are expected and harmless:
- `pipelines.wiring` — an unresolved `compliance-officer` role in the
  **regulated** pipeline, which this shop does not use.
- `monitoring.roots` — only if your sidecar root path contains a space; the
  doctor's arg parser doesn't strip quotes. Confirm the truth with
  `journalctl --user -u autodev-watch -n 20`, which prints the repos it
  actually sees.

## 4. Prove full access — don't assume it

`.claude/settings.json` (bypassPermissions) travels with the repo, but the
*proof* deliberately does not — `.autodev/access-verified.json` is gitignored
because it carries no machine identity, and a copied one would report proven
access this machine never earned.

```bash
bash <plugin-root>/ops/verify-access.sh .
```

- **PROVEN** → done.
- **NOT LOGGED IN** → run `claude` here once, finish `/login`, re-run.
- **PERMISSION wall** → run `claude` here once, accept the bypass-permissions
  warning, re-run.

## 5. Monitoring (optional)

```bash
node <plugin-root>/scripts/sidecar-service.mjs install --roots "<parent dir of this repo>"
node <plugin-root>/scripts/sidecar-service.mjs status
```

Quote the roots path if it contains a space, or the watcher silently reports
`0 repos`.

## 6. Pick up where the last machine left off

```
/autodev:init
```

It reads `.autodev/onboarding.json`, sees what's already done, and resumes the
conversation mid-stream rather than re-interviewing you.

---

## Working across two machines

`.autodev/events.jsonl` is an **append-only ledger**. Run tickets on both boxes
without pulling first and it will conflict — annoying rather than dangerous,
but the fix is discipline:

**`git pull` before you start work. `git push` when you stop.**

## What travels, and what doesn't

| Travels via git | Stays on the machine |
| --- | --- |
| `.autodev/shop.json` — shop, operator, preset | `claude` login |
| `.autodev/data/gates-policy.json` — your gates | `.autodev/access-verified.json` |
| `.autodev/envelope.json` — access + ledger fence | the monitoring sidecar service |
| `.autodev/events.jsonl`, `tickets/` — the ledger | the plugin itself |
| `.autodev/onboarding.json` — so init resumes | |
| `.autodev/imports/` — the imported personas | |
| `kb/` — CURRENT-WORK, CODE-MAP, wiki | |
| `.claude/settings.json` — bypassPermissions | |

## This shop

- **shop** `autosql` · **operator** `human:owner` · **preset** `solo-builder-review`
- Two human gates: **spec approval** and **QA acceptance**. Build, review,
  merge, verify and ship run unattended.
- Rationale on the record: a SQL generator fails *quietly* — subtly wrong
  numbers rather than an error — so there are eyes before ship.
- Change any of it with `/autodev:config`.
