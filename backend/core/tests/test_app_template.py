from pathlib import Path


def test_application_template_contains_every_architecture_layer() -> None:
    """Given the app template. When inspected. Then every architecture layer is present."""

    repository_path = Path(__file__).parents[3]
    template_path = repository_path / "scripts" / "templates" / "django_app"
    template_files = {
        path.relative_to(template_path).as_posix()
        for path in template_path.rglob("*")
        if path.is_file()
    }

    expected_files = {
        "commands/__init__.py-tpl",
        "queries/__init__.py-tpl",
        "models/__init__.py-tpl",
        "factories/__init__.py-tpl",
        "services/__init__.py-tpl",
        "views/__init__.py-tpl",
        "urls.py-tpl",
    }

    assert expected_files <= template_files
