/* ══════════════════════════════════════════════════════════════════════════════════════════
   skin.js — the skin registry and the switcher. Vanilla, dependency-free, no build step.

   ── Why this is a FILE and not an inline <script> ────────────────────────────────────────
   index.html's Content-Security-Policy is `script-src 'self'` with NO 'unsafe-inline'. An
   inline script would be refused by the browser and the page would silently open in the
   wrong skin. ('unsafe-inline' appears once in that policy, for style only, because React
   writes element.style directly.)

   ── Why it is loaded SYNCHRONOUSLY in <head> rather than deferred ────────────────────────
   The stored choice has to be on <html> before the first paint, or every reader who picked a
   light skin gets a dark flash on every load. This file is tiny and does no layout work
   before DOMContentLoaded for exactly that reason.

   ── Why it touches no .jsx ───────────────────────────────────────────────────────────────
   demo/frontend/*.jsx is covered by manifest.json's `ui:frontend-sources:sha256`, so editing
   it means re-running `./run-demo build-ui` and re-baselining that digest — the exact step
   T-14 skipped and T-16 had to repair. The switcher therefore builds its own DOM and appends
   it to <body>, and the React app never knows it is there.

   ── THE CONTRACT: adding a skin ──────────────────────────────────────────────────────────
   Write demo/static/skins/<name>.css with every rule scoped under :root[data-theme="<name>"],
   add ONE row to SKINS below, and add ONE <link> in index.html. Nothing else changes.
   ══════════════════════════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  /* The first row is the base: `system` is not a file, it is the ABSENCE of a data-theme
     attribute, which lets base.css's prefers-color-scheme block decide. It is first because
     a tool that opens in the wrong brightness for someone's desk is a tool they close. */
  var SKINS = [
    { name: "system",   label: "System",   note: "Follows your OS light or dark setting." },
    { name: "light",    label: "Light",    note: "The base palette, always light." },
    { name: "dark",     label: "Dark",     note: "The base palette, always dark." },
    { name: "gunmetal", label: "Gunmetal", note: "Brushed graphite and one electric cyan." },
    { name: "titanium", label: "Titanium", note: "Warm light metal and a deep teal. Built for daylight." },
    { name: "classic",  label: "Classic",  note: "Win9x desktop — gray chrome, navy, square corners." },
    { name: "jrpg",     label: "JRPG",     note: "A console menu: teal field, gold frames, cream text." }
  ];

  var DEFAULT_SKIN = "system";
  var STORAGE_KEY = "autosql-demo-skin";

  /* localStorage throws outright in some contexts (a browser set to block site data, some
     private modes) rather than returning null, so every read and write is guarded and the
     page renders correctly with no stored value. */
  function known(v) {
    for (var i = 0; i < SKINS.length; i++) if (SKINS[i].name === v) return v;
    return null;
  }

  /* `#skin=<name>` wins over the stored choice, for this load only.
     It makes a look linkable ("open it in Classic and see"), and it is the only way to
     drive the skin from a headless browser, which is how each of these was actually
     looked at rather than assumed. It deliberately does NOT persist: a link someone
     sent you should not silently change the skin you chose for yourself. */
  function readHash() {
    var m = /(?:^|[#&])skin=([a-z]+)/.exec(window.location.hash || "");
    return m ? known(m[1]) : null;
  }

  function readStored() {
    try {
      var v = known(window.localStorage.getItem(STORAGE_KEY));
      if (v) return v;
    } catch (e) { /* no storage: fall through to the default */ }
    return DEFAULT_SKIN;
  }

  function writeStored(name) {
    try { window.localStorage.setItem(STORAGE_KEY, name); } catch (e) { /* not fatal */ }
  }

  function apply(name) {
    var root = document.documentElement;
    if (name === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", name);
  }

  var current = readHash() || readStored();
  apply(current);                       // before first paint — this is why we are not deferred

  /* ── the picker ───────────────────────────────────────────────────────────────────────── */
  function build() {
    if (document.getElementById("skin-picker")) return;

    var wrap = document.createElement("div");
    wrap.className = "skin-picker";
    wrap.id = "skin-picker";

    var label = document.createElement("label");
    label.className = "skin-picker-label";
    label.setAttribute("for", "skin-picker-select");
    label.textContent = "Skin";

    var select = document.createElement("select");
    select.className = "skin-picker-select";
    select.id = "skin-picker-select";

    for (var i = 0; i < SKINS.length; i++) {
      var opt = document.createElement("option");
      opt.value = SKINS[i].name;
      opt.textContent = SKINS[i].label;
      opt.title = SKINS[i].note;
      if (SKINS[i].name === current) opt.selected = true;
      select.appendChild(opt);
    }

    var note = document.createElement("span");
    note.className = "skin-picker-note";
    function setNote(name) {
      for (var j = 0; j < SKINS.length; j++) {
        if (SKINS[j].name === name) { note.textContent = SKINS[j].note; return; }
      }
      note.textContent = "";
    }
    setNote(current);

    select.addEventListener("change", function () {
      current = select.value;
      apply(current);
      writeStored(current);
      setNote(current);
    });

    wrap.appendChild(label);
    wrap.appendChild(select);
    wrap.appendChild(note);
    document.body.appendChild(wrap);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
