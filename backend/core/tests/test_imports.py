import ast
from pathlib import Path


def test_application_import_style_respects_module_boundaries() -> None:
    """Given application imports. When their AST is checked. Then module boundaries are enforced."""

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
                "valid-command-to-command",
                Path("apps/orders/commands/order_create_command.py"),
                "from apps.users.commands import UserCreateCommand",
                None,
            ),
            (
                "valid-query-to-query",
                Path("apps/orders/queries/order_get_query.py"),
                "from apps.users.queries import UserGetQuery",
                None,
            ),
            (
                "invalid-command-to-private-layer",
                Path("apps/orders/commands/order_create_command.py"),
                "from apps.users.models import UserModel",
                "cross-module import must use an allowed public package",
            ),
            (
                "invalid-command-to-query-implementation",
                Path("apps/orders/commands/order_create_command.py"),
                "from apps.users.queries.user_get_query import UserGetQuery",
                "cross-module import must use an allowed public package",
            ),
            (
                "invalid-query-to-command",
                Path("apps/orders/queries/order_get_query.py"),
                "from apps.users.commands import UserCreateCommand",
                "cross-module import must use an allowed public package",
            ),
            (
                "invalid-view-to-other-module",
                Path("apps/orders/views/order_list_view.py"),
                "from apps.users.queries import UserGetQuery",
                "cross-module imports are forbidden from this layer",
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
    allowed_cross_module_imports = {
        "commands": {"commands", "queries"},
        "queries": {"queries"},
    }

    for label, path, source, expected_violation in sources:
        current_module = path.parts[1]
        current_package = list(path.parent.parts)
        source_layer = path.parts[2] if len(path.parts) > 3 else ""
        violations: list[str] = []

        for node in ast.walk(ast.parse(source)):
            node_lineno = node.lineno if isinstance(node, (ast.Import, ast.ImportFrom)) else 0
            absolute_imports: list[list[str]] = []
            if isinstance(node, ast.Import):
                absolute_imports = [imported_name.name.split(".") for imported_name in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported_parts = node.module.split(".") if node.module else []
                absolute_imports = (
                    [
                        ["apps", imported_name.name.split(".", maxsplit=1)[0]]
                        for imported_name in node.names
                    ]
                    if imported_parts == ["apps"]
                    else [imported_parts]
                )

            for imported_parts in absolute_imports:
                if len(imported_parts) < 2 or imported_parts[0] != "apps":
                    continue

                imported_module = imported_parts[1]
                if imported_module == current_module:
                    violations.append(
                        f"{label}:{node_lineno}: imports from its own module must be relative"
                    )
                    continue

                if source_layer not in allowed_cross_module_imports:
                    violations.append(
                        f"{label}:{node_lineno}: cross-module imports are forbidden from this layer"
                    )
                    continue

                target_layer = imported_parts[2] if len(imported_parts) == 3 else ""
                if target_layer not in allowed_cross_module_imports[source_layer]:
                    violations.append(
                        f"{label}:{node_lineno}: "
                        "cross-module import must use an allowed public package"
                    )

            if not isinstance(node, ast.ImportFrom) or node.level == 0:
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
