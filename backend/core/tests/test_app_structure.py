from pathlib import Path

GLOBAL_ALLOWED_APP_ELEMENTS = frozenset(
    {
        "__init__.py",
        "admin.py",
        "apps.py",
        "commands",
        "exceptions.py",
        "factories",
        "factories.py",
        "migrations",
        "models",
        "models.py",
        "queries",
        "services",
        "services.py",
        "tests",
        "urls.py",
        "views",
    }
)
"""Files and packages allowed in every application module."""


MODULE_ALLOWED_APP_ELEMENTS: dict[str, frozenset[str]] = {
    # "orders": frozenset({"integrations"}),
}
"""Additional allowed elements keyed by the application module name."""


def test_application_modules_use_only_the_declared_architecture() -> None:
    """Given application modules. When inspected. Then only declared elements exist."""

    apps_path = Path(__file__).parents[2] / "apps"
    violations: list[str] = []

    for module_path in apps_path.iterdir():
        if not module_path.is_dir() or module_path.name == "__pycache__":
            continue

        allowed_elements = GLOBAL_ALLOWED_APP_ELEMENTS | MODULE_ALLOWED_APP_ELEMENTS.get(
            module_path.name,
            frozenset(),
        )
        unexpected_elements = sorted(
            element.name
            for element in module_path.iterdir()
            if element.name != "__pycache__" and element.name not in allowed_elements
        )
        if unexpected_elements:
            violations.append(
                f"apps.{module_path.name}: undeclared elements: {', '.join(unexpected_elements)}"
            )

    assert not violations, "\n".join(violations)
