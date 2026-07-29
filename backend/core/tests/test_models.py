from django.apps import apps

from core.models import BaseModel


def test_application_models_inherit_from_base_model() -> None:
    """Given application models. When bases are checked. Then each model uses BaseModel."""
    violations = [
        model._meta.label
        for model in apps.get_models()
        if model.__module__.startswith("apps.") and not issubclass(model, BaseModel)
    ]

    assert not violations, f"Models must inherit from BaseModel: {', '.join(violations)}"
