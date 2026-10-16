"""T-108 — the vendored engine never imports itself by its own absolute name (GA-76).

GIMS loads autoSQL's engine under a private package name. An absolute self-import (``from picks import env``) then
either fails there (ModuleNotFoundError: a 500 on the first zoned question, found by asql-m-build vendoring 0fbf225)
or, if another ``picks`` were importable, silently reads THAT package. Every module of the vendored packages --
``picks/`` (with ``pyrunner/``), ``compiler/`` and ``runtime/``, their test folders aside -- imports its own
package relatively. Read from the syntax tree, so a string or a comment never counts and an import inside a
function does.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("picks", "compiler", "runtime")


def _vendored_files():
    for pkg in PACKAGES:
        for path in sorted((ROOT / pkg).rglob("*.py")):
            rel = path.relative_to(ROOT)
            if "tests" in rel.parts or "__pycache__" in rel.parts:
                continue
            yield rel, path


def _absolute_self_imports(rel: Path, path: Path) -> list:
    own = rel.parts[0]
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] == own:
                found.append(f"{rel}:{node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == own:
                    found.append(f"{rel}:{node.lineno}: import {alias.name}")
    return found


def test_the_scan_reads_every_vendored_package():
    files = [str(rel) for rel, _ in _vendored_files()]
    assert "picks/zones.py" in files and "picks/pyrunner/shape.py" in files and "compiler/compile.py" in files
    assert not any("/tests/" in f for f in files)


def test_no_vendored_module_imports_its_own_package_by_its_absolute_name():
    found = [hit for rel, path in _vendored_files() for hit in _absolute_self_imports(rel, path)]
    assert found == [], "absolute self-imports (GIMS loads the engine under another name):\n" + "\n".join(found)


def test_the_scan_sees_an_import_inside_a_function(tmp_path):
    """The defect was inside a function body: the scan must not stop at the module's top level."""
    pkg = tmp_path / "picks"
    pkg.mkdir()
    (pkg / "m.py").write_text("def f():\n    from picks import env\n    import picks.view\n    from . import ok\n")
    assert _absolute_self_imports(Path("picks/m.py"), pkg / "m.py") == [
        "picks/m.py:2: from picks import ...", "picks/m.py:3: import picks.view"]
