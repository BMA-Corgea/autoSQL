// demo/frontend/build.mjs — esbuild, in GIMS's own shape (spec §9.1).
//
// ONLY `./run-demo build-ui` runs this, and it is the ONLY verb allowed to
// need Node. `up` and `test` never touch it: they run from the bundles
// this writes, which are COMMITTED under demo/static/js/ (B19 — not
// dist/, not build/, both of which .gitignore swallows at any depth).
// AC-36 is the criterion: `./run-demo up` with `node` removed from PATH
// serves a working screen.
//
// TWO BUNDLES, THE WAY GIMS DOES IT (../GIMS-Project/build.mjs, read-only):
//   • static/js/vendor.js — the real React + ReactDOM, bundled once, hung
//     on window globals. Loaded first.
//   • static/js/app.js    — the demo's own modules, with react,
//     react-dom/client and react/jsx-runtime ALIASED OUT to those globals
//     so the page bundle does not re-embed React.
// GIMS keeps its shims in frontend/vendor/shims/*.js. This build keeps
// them as VIRTUAL modules in the plugin below instead, because locate
// §3.1 fixes the demo's frontend tree and four one-line files that exist
// only to read a global are not worth four entries in it.
//
// AND THE THING THAT KEEPS THE BUNDLES HONEST (plan §9, risk 7):
//   a bundle that is stale is worse than a bundle that is missing — the
//   screen a reviewer sees would not be the screen the source describes.
//   So this writes a sha256 over the concatenated JSX/JS sources into
//   demo/manifest.json under `ui:frontend-sources:sha256`, and
//   demo/tests/test_ui.py recomputes it. Edit a .jsx without rebuilding
//   and the suite fails, by name.
//
//   node build.mjs          # production (minified)
//   node build.mjs --dev    # unminified + inline sourcemaps
//   node build.mjs --watch  # rebuild on change

import * as esbuild from "esbuild";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEMO = path.resolve(HERE, "..");
const REPO = path.resolve(DEMO, "..");
const OUT = path.join(DEMO, "static", "js");
const MANIFEST = path.join(DEMO, "manifest.json");

const watch = process.argv.includes("--watch");
const dev = process.argv.includes("--dev") || watch;

//: Every source that ends up in app.js, in a fixed order. The vendored
//: ui.jsx is in the list on purpose: it is bundled in, so a drift in it
//: is a drift in the bundle.
const SOURCES = [
  path.join(DEMO, "vendor", "ui.jsx"),
  path.join(HERE, "icons.jsx"),
  path.join(HERE, "pick.jsx"),
  path.join(HERE, "verdict.jsx"),
  path.join(HERE, "rail.jsx"),
  path.join(HERE, "panes.jsx"),
  path.join(HERE, "sqlpane.jsx"),
  path.join(HERE, "app.jsx"),
];

export function sourceDigest() {
  const h = createHash("sha256");
  for (const f of SOURCES) {
    h.update(path.relative(REPO, f).split(path.sep).join("/"));
    h.update("\0");
    h.update(readFileSync(f));
    h.update("\0");
  }
  return h.digest("hex");
}

// ── the virtual shims: react resolved to the vendor bundle's globals ──
const SHIM = {
  react: "module.exports = window.React;",
  "react-dom": "module.exports = window.ReactDOM;",
  "react-dom/client": "module.exports = window.ReactDOMClient;",
  "react/jsx-runtime": "module.exports = window.ReactJSXRuntime;",
};

const shimPlugin = {
  name: "react-globals",
  setup(build) {
    const filter = /^(react|react-dom|react-dom\/client|react\/jsx-runtime)$/;
    build.onResolve({ filter }, (a) => ({ path: a.path, namespace: "shim" }));
    build.onLoad({ filter: /.*/, namespace: "shim" }, (a) => ({
      contents: SHIM[a.path],
      loader: "js",
    }));
  },
};

// ── the vendor entry: the REAL react, hung on window ──────────────────
const VENDOR_ENTRY = `
import * as React from "react";
import * as ReactDOM from "react-dom";
import * as ReactDOMClient from "react-dom/client";
import * as ReactJSXRuntime from "react/jsx-runtime";
window.React = React;
window.ReactDOM = ReactDOM;
window.ReactDOMClient = ReactDOMClient;
window.ReactJSXRuntime = ReactJSXRuntime;
`;

const vendorEntryPlugin = {
  name: "vendor-entry",
  setup(build) {
    build.onResolve({ filter: /^autosql:vendor$/ }, () => ({
      path: "autosql:vendor",
      namespace: "vendor-entry",
    }));
    build.onLoad({ filter: /.*/, namespace: "vendor-entry" }, () => ({
      contents: VENDOR_ENTRY,
      loader: "js",
      resolveDir: HERE,
    }));
  },
};

const common = {
  bundle: true,
  format: "iife",
  jsx: "automatic",
  loader: { ".jsx": "jsx" },
  target: ["es2020"],
  minify: !dev,
  sourcemap: dev ? "inline" : false,
  legalComments: "none",
  logLevel: "info",
  define: { "process.env.NODE_ENV": dev ? '"development"' : '"production"' },
};

const vendorOpts = {
  ...common,
  entryPoints: ["autosql:vendor"],
  outfile: path.join(OUT, "vendor.js"),
  plugins: [vendorEntryPlugin],
};

const appOpts = {
  ...common,
  entryPoints: [path.join(HERE, "app.jsx")],
  outfile: path.join(OUT, "app.js"),
  plugins: [shimPlugin],
};

function recordDigest() {
  const digest = sourceDigest();
  const manifest = JSON.parse(readFileSync(MANIFEST, "utf8"));
  manifest["ui:frontend-sources:sha256"] = digest;
  writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2) + "\n");
  return digest;
}

if (watch) {
  const ctxs = await Promise.all([vendorOpts, appOpts].map((o) => esbuild.context(o)));
  await Promise.all(ctxs.map((c) => c.watch()));
  console.log("[build-ui] watching demo/frontend/** → demo/static/js/");
} else {
  await Promise.all([vendorOpts, appOpts].map((o) => esbuild.build(o)));
  const digest = recordDigest();
  console.log(`[build-ui] wrote demo/static/js/vendor.js + app.js`);
  console.log(`[build-ui] manifest ui:frontend-sources:sha256 = ${digest}`);
  console.log(`[build-ui] COMMIT BOTH BUNDLES — AC-36 runs from them, with no Node present.`);
}
