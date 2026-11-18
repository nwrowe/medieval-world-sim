"""Keep gameplay/domain modules independent of HTTP, accounts and browser adapters."""
from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path
import unittest


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "medieval_world_sim"
DOMAIN_AREAS = ("core", "systems", "content", "worldgen")
WEB_PACKAGE = "medieval_world_sim.web"


def imported_modules(source: str, package: str) -> set[str]:
    """Find statically declared Python imports, including relative imports."""
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = (
                resolve_name("." * node.level + (node.module or ""), package)
                if node.level else (node.module or "")
            )
            imported.add(module)
            if node.module is None:
                imported.update(f"{module}.{alias.name}" for alias in node.names)
    return imported


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_does_not_depend_on_web_adapters(self):
        for area in DOMAIN_AREAS:
            for path in sorted((PACKAGE_ROOT / area).rglob("*.py")):
                package = ".".join(("medieval_world_sim", *path.relative_to(
                    PACKAGE_ROOT).parts[:-1]))
                source = path.read_text(encoding="utf-8")
                with self.subTest(path=str(path.relative_to(PACKAGE_ROOT))):
                    imports = imported_modules(source, package)
                    forbidden = sorted(name for name in imports if
                                       name == WEB_PACKAGE or
                                       name.startswith(WEB_PACKAGE + "."))
                    self.assertFalse(
                        forbidden,
                        f"Gameplay code must not import web adapters: {forbidden}",
                    )

    def test_relative_imports_are_resolved(self):
        self.assertIn("medieval_world_sim.web", imported_modules(
            "from ..web import session", "medieval_world_sim.core"))
        self.assertIn("medieval_world_sim.web.session", imported_modules(
            "from medieval_world_sim.web.session import GameSession",
            "medieval_world_sim.core"))


if __name__ == "__main__":
    unittest.main()
