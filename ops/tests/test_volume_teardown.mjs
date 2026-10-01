/**
 * T-25 — a teardown must remove exactly what its own run created: no less, and no more.
 *
 * No less (T-25). Both Postgres images this repo uses declare `VOLUME /var/lib/postgresql/data`.
 * A container run with nothing mounted there gets an ANONYMOUS volume, and `docker rm -f <c>`
 * removes the container and leaves that volume dangling, invisible to `docker ps -a`. Measured on
 * 2026-10-01: one run of ops/runtime-check.sh, as it stood, took the machine's dangling count
 * from 74 to 75 (about 48 MB). REGENERATE-CORPUS §9 paid for the same thing first, at ~1 GiB.
 *
 * No more (T-45). `--volumes` on `compose … down` also deletes the NAMED volumes the compose file
 * declares, including one the run did not create: that is how `./run-demo test` deletes a
 * deliberately kept demo volume. So `-v`/`--volumes` is this guard's DEFAULT rule, not a law. A
 * deliberate keep of a volume the run did not create needs a reasoned exemption, which T-45
 * adds; until then such a keep fails here, on purpose.
 *
 * WHAT IT RECOGNISES, in every tracked shell script outside spikes/ (`*.sh`, or a bash/sh/dash/
 * zsh shebang; spikes/ is frozen evidence):
 *   docker rm · docker container rm|remove · docker compose … down|rm · docker-compose … down|rm
 *                              -> must pass -v or --volumes
 *   docker system prune        -> must pass --volumes
 *   docker container prune     -> always flagged: it has no way to remove volumes
 * with docker written as `docker`, `$DOCKER` or `${DOCKER}` (either case, quoted or not), after docker's or
 * compose's global flags (--context, -H, --host, --config, -c, --log-level; -f, -p, …), and
 * wherever the word stands: after sudo or xargs, inside $( … ), in a string handed to ssh. A
 * command's flags end at ; & | a backtick, a newline, or a `)` it did not open. Comments follow
 * bash's rule (an unquoted `#` that starts a word); only a backslash IMMEDIATELY before a newline
 * joins two lines; heredoc bodies are read as text, one line at a time.
 *
 * WHAT IT DOES NOT SEE: docker behind a wrapper function or an alias (`dk() { docker "$@"; }`),
 * in an array or a variable with any other name, or in an `eval`; list-form calls from Python
 * (`subprocess.run(["docker", "rm", …])`); files that are not shell scripts; and a container
 * started with no teardown at all — a missing line cannot be scanned. It does not judge the
 * "no more" half (T-45's). It over-reads on purpose: a teardown quoted in an echo, a heredoc or a
 * grep pattern is read like a command, because prose that tells a person to run `docker rm -f x`
 * teaches the same leak. Reword it, or give it the flag.
 *
 * Each test below was WATCHED FAILING before it was trusted (T-25 review round 2): against the
 * unfixed tree, planted leaks, a guard that sees no volume flag, a guard that flags everything,
 * a discovery that finds nothing, and a teardown moved where the scan cannot see it — because a
 * scan of nothing passes too.
 *
 * run: node --test ops/tests/test_volume_teardown.mjs      (or: ops/run-tests.sh)
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = (f) => fs.readFileSync(path.join(REPO, f), "utf8");

/** Tracked shell scripts outside spikes/: `*.sh`, or any tracked file with a shell shebang. */
export function trackedShellScripts(repo = REPO) {
  const files = execFileSync("git", ["ls-files", "-z"], { cwd: repo, encoding: "utf8" })
    .split("\0").filter(Boolean);
  return files.filter((f) => {
    if (f.startsWith("spikes/")) return false;
    if (f.endsWith(".sh")) return true;
    let head = "";
    try {
      const fd = fs.openSync(path.join(repo, f), "r");
      const buf = Buffer.alloc(80);
      const n = fs.readSync(fd, buf, 0, 80, 0);
      fs.closeSync(fd);
      head = buf.subarray(0, n).toString("utf8");
    } catch { return false; }
    return /^#!.*\b(?:bash|sh|dash|zsh)\b/.test(head);
  });
}

/**
 * The script as bash would split it: { lines: [{ text, at }], open }. One entry per logical
 * line, with comments dropped and `\`-newline joins made; a heredoc body comes back as one entry
 * per line, read as text. `at[k]` is the source line of `text[k]`. Quotes are tracked only to
 * tell a `#` or a `\` inside a string from one in the script. `open` names a quote or heredoc
 * still open at the end: a scanner that has lost its place misreads everything after it.
 */
export function logicalLines(text) {
  const lines = [], pending = [];
  let cur = "", at = [], q = null, qFrom = 0, n = 1;
  const put = (s) => { for (const ch of s) { cur += ch; at.push(n); } };
  const flush = () => { if (cur.trim()) lines.push({ text: cur, at }); cur = ""; at = []; };
  for (let i = 0; i < text.length; i++) {
    const c = text[i], next = text[i + 1];
    if (q === "'") { put(c); if (c === "\n") n++; if (c === "'") q = null; continue; }
    if (c === "\\") {
      if (next === "\n") { i++; n++; continue; }   // a continuation: `\` RIGHT before the newline
      put(c + (next ?? "")); i++; continue;         // an escape: `\#`, `\"`, `\ ` are not special
    }
    if (q === '"') { put(c); if (c === "\n") n++; if (c === '"') q = null; continue; }
    if (c === "'" || c === '"') { q = c; qFrom = n; put(c); continue; }
    if (c === "#" && (cur === "" || /[\s;&|()<>]$/.test(cur))) {  // a comment, to the end of its line
      while (i + 1 < text.length && text[i + 1] !== "\n") i++;
      continue;
    }
    if (c === "<" && next === "<" && text[i + 2] !== "<") {          // a heredoc opener (<<< is not)
      const m = /^<<(-?)[ \t]*(?:'([^'\n]*)'|"([^"\n]*)"|\\?([^\s;&|()<>]+))/.exec(text.slice(i, i + 200));
      if (m) {
        pending.push({ delim: m[2] ?? m[3] ?? m[4].replace(/['"\\]/g, ""), tabs: m[1] === "-", from: n });
        put(m[0]); i += m[0].length - 1; continue;
      }
    }
    if (c === "\n") {
      flush(); n++;
      while (pending.length) {                       // the bodies, in order: text, line by line
        const h = pending.shift();
        for (;;) {
          if (i + 1 >= text.length) return { lines, open: `heredoc <<${h.delim} from line ${h.from}` };
          const nl = text.indexOf("\n", i + 1), end = nl === -1 ? text.length : nl;
          const body = text.slice(i + 1, end);
          i = end; n++;
          if ((h.tabs ? body.replace(/^\t+/, "") : body) === h.delim) break;
          lines.push({ text: body, at: Array(body.length).fill(n - 1) });
        }
      }
      continue;
    }
    put(c);
  }
  flush();
  const open = q ? `a ${q === "'" ? "single" : "double"} quote from line ${qFrom}`
    : pending.length ? `heredoc <<${pending[0].delim} from line ${pending[0].from}` : null;
  return { lines, open };
}

// docker as a command word: `docker`, `docker-compose`, `$DOCKER` / `${DOCKER}` (either case),
// quoted or not. `/usr/bin/docker` counts; `$docker_x`, `my-docker` and `docker.sock` do not.
const DOCKER_WORD = /(?<![\w${-])docker(?:-compose)?(?=\s)|"?\$\{?(?:DOCKER|docker)\}?"?(?=\s)/g;
// Global flags that take a value, so the value is not read as the subcommand.
const DOCKER_VALUE_FLAGS = new Set(["-c", "--config", "--context", "-H", "--host", "-l",
  "--log-level", "--tlscacert", "--tlscert", "--tlskey"]);
const COMPOSE_VALUE_FLAGS = new Set(["-f", "--file", "-p", "--project-name", "--project-directory",
  "--env-file", "--profile", "--ansi", "--progress", "--parallel"]);

const HAS_V = (a) => a === "--volumes" || a === "--volumes=true" || /^-[a-zA-Z]*v[a-zA-Z]*$/.test(a);
/** What each recognised teardown must pass to take its anonymous volumes with it. */
const TAKES_VOLUMES = {
  "docker rm": (rest) => rest.some(HAS_V),
  "compose down": (rest) => rest.some(HAS_V),
  "compose rm": (rest) => rest.some(HAS_V),
  "system prune": (rest) => rest.includes("--volumes") || rest.includes("--volumes=true"),
  "container prune": () => false,
};

/** The rest of one simple command: up to ; & | a backtick or a newline, or a `)` it did not
 *  open. `top` leaves out what sits inside the command's own $( … ), so a nested command's
 *  flags (`$(grep -v …)`) are never borrowed. */
function commandRest(t, from) {
  let raw = "", top = "", depth = 0;
  for (let i = from; i < t.length; i++) {
    const c = t[i];
    if (depth === 0 && /[;&|`\n]/.test(c)) break;
    if (c === ")") { if (depth === 0) break; depth--; raw += c; if (depth === 0) top += " "; continue; }
    if (c === "(") depth++;
    raw += c;
    if (depth === 0) top += c;
  }
  return { raw, top };
}

/** Words as the shell would pass them, quotes removed (`"$C"` -> `$C`). */
function shellWords(s) {
  const words = [];
  let w = null, q = null;
  for (const c of s) {
    if (q) { if (c === q) q = null; else w += c; continue; }
    if (c === "'" || c === '"') { q = c; w ??= ""; continue; }
    if (/\s/.test(c)) { if (w !== null) words.push(w); w = null; continue; }
    w = (w ?? "") + c;
  }
  if (w !== null) words.push(w);
  return words;
}

const skipFlags = (w, i, valued) => {
  while (i < w.length && w[i].startsWith("-")) i += valued.has(w[i]) ? 2 : 1;
  return i;
};
function composeTeardown(w) {
  const i = skipFlags(w, 0, COMPOSE_VALUE_FLAGS);
  return w[i] === "down" || w[i] === "rm" ? { kind: `compose ${w[i]}`, rest: w.slice(i + 1) } : null;
}
function dockerTeardown(w) {
  const i = skipFlags(w, 0, DOCKER_VALUE_FLAGS);
  const [a, b] = [w[i], w[i + 1]];
  if (a === "rm") return { kind: "docker rm", rest: w.slice(i + 1) };
  if (a === "container" && (b === "rm" || b === "remove")) return { kind: "docker rm", rest: w.slice(i + 2) };
  if (a === "container" && b === "prune") return { kind: "container prune", rest: w.slice(i + 2) };
  if (a === "system" && b === "prune") return { kind: "system prune", rest: w.slice(i + 2) };
  if (a === "compose") return composeTeardown(w.slice(i + 1));
  return null;
}

/** Every teardown the guard recognises in a script's text, compliant or not:
 *  [{ line, command, kind, removesVolumes }]. */
export function teardowns(text) {
  const out = [];
  for (const { text: t, at } of logicalLines(text).lines) {
    for (const m of t.matchAll(DOCKER_WORD)) {
      const { raw, top } = commandRest(t, m.index + m[0].length);
      const words = shellWords(top);
      const found = m[0] === "docker-compose" ? composeTeardown(words) : dockerTeardown(words);
      if (!found) continue;
      out.push({ line: at[m.index], command: (m[0] + raw).replace(/\s+/g, " ").trim(),
        kind: found.kind, removesVolumes: TAKES_VOLUMES[found.kind](found.rest) });
    }
  }
  return out;
}

/** The recognised teardowns that leave a volume behind. */
export function leakyTeardowns(text) {
  return teardowns(text).filter((t) => !t.removesVolumes);
}

test("every tracked shell script outside spikes/ removes volumes with its containers (T-25)", () => {
  const offenders = [];
  for (const f of trackedShellScripts()) {
    for (const hit of leakyTeardowns(read(f))) offenders.push(`${f}:${hit.line}  ${hit.command}`);
  }
  assert.deepEqual(offenders, [],
    "a teardown leaves an anonymous volume behind; add -v (docker rm, compose down|rm) or " +
    "--volumes (system prune). A deliberate keep needs T-45's reasoned exemption:\n  " +
    offenders.join("\n  "));
});

test("the scan reads the real scripts AND recognises the teardowns in them (a scan of nothing passes too)", () => {
  const scripts = trackedShellScripts();
  // A `*.sh` with a teardown, an extensionless script found by its shebang, and the front door.
  for (const must of ["ops/runtime-check.sh", "run-demo", "start.sh"]) {
    assert.ok(scripts.includes(must), `${must} is not in the scanned set: ${scripts.join(", ")}`);
  }
  assert.ok(!scripts.some((f) => f.startsWith("spikes/")), "spikes/ is frozen evidence and is not scanned");
  for (const f of scripts) {
    const { open } = logicalLines(read(f));
    assert.equal(open, null, `the scanner lost its place in ${f}: ${open} is never closed`);
  }
  // Read is not enough: the teardowns this repo actually runs must come back from the scan.
  // If one moves behind a wrapper the guard cannot see, this fails instead of going quiet.
  for (const [f, re] of [
    ["ops/runtime-check.sh", /^docker rm\b.*"\$CONTAINER"/],
    ["run-demo", /^docker compose -f "\$COMPOSE_FILE" down\b/],
  ]) {
    const seen = teardowns(read(f));
    assert.ok(seen.some((t) => re.test(t.command)),
      `${f}: its teardown ${re} was not recognised; the scan saw ${JSON.stringify(seen.map((t) => t.command))}`);
  }
});

test("the guard would actually catch one: planted leaky teardowns are flagged", () => {
  const planted = [
    'docker rm -f "$CONTAINER" >/dev/null 2>&1',
    "docker container rm autosql-x",
    "  docker rm -f a && echo done",
    'docker compose -f "$COMPOSE_FILE" down',
    "docker-compose down --remove-orphans",
    "docker rm -f \\\n  autosql-x",
    "docker rm -f -v a; docker rm -f b",
    // review round 1 found these unseen
    '"$DOCKER" rm -f x', "$DOCKER rm -f x", '"${DOCKER}" rm -f x',
    "docker --context default rm -f x", "docker -H unix:///var/run/docker.sock rm -f x",
    "docker --host tcp://127.0.0.1:2375 rm -f x", "docker --config /tmp/cfg rm -f x",
    "docker -c default rm -f x", "docker --log-level warn rm -f x",
    "docker --context default compose down",
    "docker container remove x",
    "docker compose rm -f", 'docker compose -f "$COMPOSE_FILE" rm -fs db', "docker-compose rm -f",
    "docker container prune -f", "docker system prune -f",
    'x=$(docker rm -f "$C") y=$(grep -v a b)',
    "# see C:\\docs\\\ndocker rm -f x",
    "docker rm -f x \\ \ndocker volume ls -v",
    'echo " # "; docker rm -f x',
    "printf '%s # %s\\n' a b; docker rm -f x",
  ];
  for (const src of planted) {
    assert.ok(leakyTeardowns(src).length >= 1, `not caught: ${JSON.stringify(src)}`);
  }
  // The mixed line: the compliant half passes, the leaky half is still caught.
  assert.deepEqual(leakyTeardowns("docker rm -f -v a; docker rm -f b").map((h) => h.command), ["docker rm -f b"]);
  // A `)` ends the command: grep's -v is not borrowed.
  assert.deepEqual(leakyTeardowns('x=$(docker rm -f "$C") y=$(grep -v a b)').map((h) => h.command),
    ['docker rm -f "$C"']);
  // A comment ending in `\` joins nothing: the next line is a command, on its own line number.
  assert.deepEqual(leakyTeardowns("# see C:\\docs\\\ndocker rm -f x").map((h) => [h.line, h.command]),
    [[2, "docker rm -f x"]]);
});

test("the guard leaves compliant teardowns and comments alone", () => {
  const compliant = [
    'docker rm -f -v "$CONTAINER" >/dev/null 2>&1',
    "docker rm -fv a",
    "docker rm -vf a",
    "docker container rm --volumes a",
    'docker compose -f "$COMPOSE_FILE" down --volumes',
    "docker compose down -v",
    "docker rm -f \\\n  -v autosql-x",
    "  # A plain `docker rm -f` removes the container and leaves that volume dangling",
    "docker run --rm postgres:16-alpine postgres --version",
    "docker exec x pg_isready",
    // review round 1's shapes, written correctly
    '"$DOCKER" rm -f -v x', "docker --context default rm -fv x", "docker container remove -v x",
    "docker compose rm -fsv", "docker-compose -f x.yml rm -f -v", "docker system prune -f --volumes",
    "docker rm --volumes=true x",
    "docker rm -fv $(docker ps -aq --filter name=autosql-)",
    'docker compose -f "$D/shut-down.yml" up -d',
    "x=1 # docker rm -f x, in a trailing comment",
    "# a comment that ends in a backslash \\\necho the next line is not part of it",
  ];
  for (const src of compliant) {
    assert.deepEqual(leakyTeardowns(src), [], `false positive: ${JSON.stringify(src)}`);
  }
});
