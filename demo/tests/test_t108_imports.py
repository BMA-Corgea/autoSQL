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


_DYNAMIC = {"import_module", "__import__"}


def _absolute_self_imports(rel: Path, path: Path) -> list:
    """Any absolute import of a vendored package -- the module's own or a sibling (GIMS renames them all) -- and
    any dynamic one by name (a-chk's T-108 LOW): ``importlib.import_module("picks…")``, ``__import__("compiler")``."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(rel))):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] in PACKAGES:
                found.append(f"{rel}:{node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in PACKAGES:
                    found.append(f"{rel}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.Call) and node.args:
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            arg = node.args[0]
            if (name in _DYNAMIC and isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    and arg.value.split(".")[0] in PACKAGES):
                found.append(f"{rel}:{node.lineno}: {name}({arg.value!r})")
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


def test_the_scan_sees_dynamic_and_sibling_imports(tmp_path):
    """a-chk's T-108 LOW: a dynamic import by name, and an absolute import of a SIBLING vendored package, break under
    GIMS's private names the same way."""
    pkg = tmp_path / "picks"
    pkg.mkdir()
    (pkg / "m.py").write_text("import importlib\nimport compiler\nfrom runtime import this_runtime\n"
                              "importlib.import_module('picks.zones')\n__import__('compiler')\n"
                              "importlib.import_module('json')\nimport os\n")
    assert _absolute_self_imports(Path("picks/m.py"), pkg / "m.py") == [
        "picks/m.py:2: import compiler", "picks/m.py:3: from runtime import ...",
        "picks/m.py:4: import_module('picks.zones')", "picks/m.py:5: __import__('compiler')"]
