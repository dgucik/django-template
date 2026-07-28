import ast
from pathlib import Path


def test_application_import_style_respects_module_boundaries() -> None:
    backend_path = Path(__file__).parents[2]
    apps_path = backend_path / "apps"
    sources: list[tuple[str, Path, str, str | None]] = [
        (
            str(path.relative_to(backend_path)),
            path.relative_to(backend_path),
            path.read_text(),
            None,
        )
        for path in apps_path.rglob("*.py")
        if "migrations" not in path.parts and path.parent != apps_path
    ]
    sources.extend(
        [
            (
                "valid-internal-relative",
                Path("apps/orders/commands/order_create_command.py"),
                "from ..models import OrderModel",
                None,
            ),
            (
                "invalid-internal-absolute",
                Path("apps/orders/commands/order_create_command.py"),
                "from apps.orders.models import OrderModel",
                "imports from its own module must be relative",
            ),
            (
                "invalid-internal-absolute-import",
                Path("apps/orders/commands/order_create_command.py"),
                "import apps.orders.models",
                "imports from its own module must be relative",
            ),
            (
                "valid-cross-module-absolute",
                Path("apps/orders/commands/order_create_command.py"),
                "from apps.users.queries import UserGetQuery",
                None,
            ),
            (
                "invalid-cross-module-relative",
                Path("apps/orders/commands/order_create_command.py"),
                "from ...users.queries import UserGetQuery",
                "imports outside its own module must be absolute",
            ),
            (
                "invalid-cross-module-relative-package-import",
                Path("apps/orders/commands/order_create_command.py"),
                "from ... import users",
                "imports outside its own module must be absolute",
            ),
            (
                "invalid-external-relative",
                Path("apps/orders/commands/order_create_command.py"),
                "from ....core import handlers",
                "imports outside its own module must be absolute",
            ),
        ]
    )

    unexpected_violations: list[str] = []

    for label, path, source, expected_violation in sources:
        current_module = path.parts[1]
        current_package = list(path.parent.parts)
        violations: list[str] = []

        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for imported_name in node.names:
                    imported_parts = imported_name.name.split(".")
                    if imported_parts[:2] == ["apps", current_module]:
                        violations.append(
                            f"{label}:{node.lineno}: imports from its own module must be relative"
                        )
                continue

            if not isinstance(node, ast.ImportFrom):
                continue

            if node.level == 0:
                imported_parts = node.module.split(".") if node.module else []
                imported_modules = (
                    [imported_parts[1]]
                    if len(imported_parts) > 1 and imported_parts[0] == "apps"
                    else [
                        imported_name.name.split(".", maxsplit=1)[0] for imported_name in node.names
                    ]
                    if imported_parts == ["apps"]
                    else []
                )
                if current_module in imported_modules:
                    violations.append(
                        f"{label}:{node.lineno}: imports from its own module must be relative"
                    )
                continue

            parent_count = node.level - 1
            resolved_parts = (
                current_package[: len(current_package) - parent_count]
                if parent_count <= len(current_package)
                else []
            )
            if node.module:
                resolved_parts.extend(node.module.split("."))

            imported_modules = (
                [resolved_parts[1]]
                if len(resolved_parts) > 1 and resolved_parts[0] == "apps"
                else [imported_name.name.split(".", maxsplit=1)[0] for imported_name in node.names]
                if resolved_parts == ["apps"]
                else []
            )
            if imported_modules != [current_module]:
                violations.append(
                    f"{label}:{node.lineno}: imports outside its own module must be absolute"
                )

        if expected_violation is None:
            unexpected_violations.extend(violations)
        elif not any(expected_violation in violation for violation in violations):
            unexpected_violations.append(
                f"{label}: expected violation containing {expected_violation!r}"
            )

    assert not unexpected_violations, "\n".join(unexpected_violations)
