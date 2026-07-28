import ast
from pathlib import Path


def test_test_functions_use_bdd_docstrings() -> None:
    """Given project tests. When docstrings are checked. Then each test uses BDD wording."""
    backend_path = Path(__file__).parents[2]
    violations: list[str] = []

    for source_path in (backend_path / "apps", backend_path / "config", backend_path / "core"):
        for path in source_path.rglob("test_*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not node.name.startswith("test_"):
                    continue

                docstring = ast.get_docstring(node, clean=True) or ""
                if not all(keyword in docstring for keyword in ("Given", "When", "Then")):
                    violations.append(
                        f"{path.relative_to(backend_path)}:{node.lineno}: "
                        f"{node.name} must have a Given/When/Then docstring"
                    )

    assert not violations, "\n".join(violations)
