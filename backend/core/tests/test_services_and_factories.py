import ast
from pathlib import Path


def test_application_services_and_factories_use_static_methods() -> None:
    """Given service and factory classes. When inspected. Then their methods are static."""

    apps_path = Path(__file__).parents[2] / "apps"
    sources: list[tuple[str, str, str | None]] = [
        (
            str(path.relative_to(apps_path)),
            path.read_text(),
            None,
        )
        for path in apps_path.rglob("*.py")
        if "migrations" not in path.parts
        and (
            path.parent.name in {"factories", "services"}
            or path.name in {"factories.py", "services.py"}
        )
    ]
    sources.extend(
        [
            (
                "valid",
                """
class OrderFactory:
    @staticmethod
    def create(*, customer_id: int) -> OrderModel:
        ...
""",
                None,
            ),
            (
                "invalid-instance-method",
                """
class OrderPricingService:
    def calculate_total(self, *, subtotal: Decimal) -> Decimal:
        ...
""",
                "must be a staticmethod",
            ),
        ]
    )

    unexpected_violations: list[str] = []
    for label, source, expected_violation in sources:
        violations: list[str] = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.ClassDef):
                continue

            for method in node.body:
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                is_static = any(
                    isinstance(decorator, ast.Name) and decorator.id == "staticmethod"
                    for decorator in method.decorator_list
                )
                if not is_static:
                    violations.append(
                        f"{label}:{method.lineno}: {node.name}.{method.name} must be a staticmethod"
                    )

        rendered_violations = "\n".join(violations)
        if expected_violation is None:
            unexpected_violations.extend(violations)
        else:
            assert expected_violation in rendered_violations, (
                f"{label} did not produce {expected_violation!r}:\n{rendered_violations}"
            )

    assert not unexpected_violations, "\n".join(unexpected_violations)
