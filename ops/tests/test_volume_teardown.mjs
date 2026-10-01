/**
 * T-25 — a teardown must take its volumes with it.
 *
 * Both Postgres images this repo uses declare `VOLUME /var/lib/postgresql/data`. A container
 * run with nothing mounted there gets an ANONYMOUS volume, and `docker rm -f <c>` removes the
 * container and leaves that volume dangling, invisible to `docker ps -a`. Measured on
 * 2026-10-01: one run of ops/runtime-check.sh, as it stood, took the machine's dangling count
 * from 74 to 75 (about 48 MB). REGENERATE-CORPUS §9 paid for the same thing first, at ~1 GiB.
 *
 * The guard: every tracked shell script outside spikes/ (spikes/ is frozen evidence) that runs
 * `docker rm` / `docker container rm` passes -v or --volumes, and every `compose … down` passes
 * -v or --volumes. Each test below was WATCHED FAILING before it was trusted: the planted
 * instances must be caught, and the scan must be seen to cover real files, because a scan of
 * nothing passes too.
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

const VOLUME_FLAG = (args) =>
  args.split(/\s+/).some((a) => a === "--volumes" || /^-[a-zA-Z]*v[a-zA-Z]*$/.test(a));

/** Every leaky teardown in a shell script's text: [{ line, command }]. Comment lines are
 *  skipped; `\` continuations are joined first, so a flag on the next line still counts. */
export function leakyTeardowns(text) {
  const out = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const start = i;
    let cmd = lines[i];
    while (/\\\s*$/.test(cmd) && i + 1 < lines.length) cmd = cmd.replace(/\\\s*$/, " ") + lines[++i];
    if (/^\s*#/.test(cmd)) continue;
    cmd = cmd.replace(/\s#\s.*$/, ""); // a trailing comment
    for (const m of cmd.matchAll(/\bdocker\s+(?:container\s+)?rm\b([^;&|]*)/g)) {
      if (!VOLUME_FLAG(m[1])) out.push({ line: start + 1, command: m[0].trim() });
    }
    for (const m of cmd.matchAll(/\bdocker(?:-compose|\s+compose)\b[^;&|]*?\bdown\b([^;&|]*)/g)) {
      if (!VOLUME_FLAG(m[1])) out.push({ line: start + 1, command: m[0].trim() });
    }
  }
  return out;
}

test("every tracked shell script outside spikes/ removes volumes with its containers (T-25)", () => {
  const offenders = [];
  for (const f of trackedShellScripts()) {
    for (const hit of leakyTeardowns(fs.readFileSync(path.join(REPO, f), "utf8"))) {
      offenders.push(`${f}:${hit.line}  ${hit.command}`);
    }
  }
  assert.deepEqual(offenders, [],
    "a teardown leaves an anonymous volume behind; add -v (docker rm) or --volumes (compose down):\n  " +
    offenders.join("\n  "));
});

test("the scan covers the scripts that hold this repo's teardowns (a scan of nothing passes too)", () => {
  const scripts = trackedShellScripts();
  for (const must of ["ops/runtime-check.sh", "run-demo", "start.sh"]) {
    assert.ok(scripts.includes(must), `${must} is not in the scanned set: ${scripts.join(", ")}`);
  }
  assert.ok(!scripts.some((f) => f.startsWith("spikes/")), "spikes/ is frozen evidence and is not scanned");
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
  ];
  for (const src of planted) {
    assert.ok(leakyTeardowns(src).length >= 1, `not caught: ${JSON.stringify(src)}`);
  }
  // The mixed line: the compliant half passes, the leaky half is still caught.
  assert.deepEqual(leakyTeardowns("docker rm -f -v a; docker rm -f b").map((h) => h.command), ["docker rm -f b"]);
});

test("the guard leaves compliant teardowns and prose alone", () => {
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
  ];
  for (const src of compliant) {
    assert.deepEqual(leakyTeardowns(src), [], `false positive: ${JSON.stringify(src)}`);
  }
});
