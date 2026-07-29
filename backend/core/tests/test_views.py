import ast
from dataclasses import dataclass
from pathlib import Path

from rest_framework_dataclasses.serializers import DataclassSerializer


@dataclass(frozen=True, slots=True)
class OrderGetDto:
    id: int


class OrderGetOutSerializer(DataclassSerializer[OrderGetDto]):
    class Meta:
        dataclass = OrderGetDto


def test_dataclass_serializer_serializes_a_frozen_slotted_dto() -> None:
    """Given a query DTO. When wrapped by a view serializer. Then primitive data is returned."""

    assert OrderGetOutSerializer(OrderGetDto(id=1)).data == {"id": 1}


def test_application_serializers_are_dataclass_serializers_colocated_with_views() -> None:
    """Given application serializers. When checked. Then they are dataclass view wrappers."""

    apps_path = Path(__file__).parents[2] / "apps"
    violations: list[str] = []

    for path in apps_path.rglob("*.py"):
        relative_path = path.relative_to(apps_path)
        if "serializers" in relative_path.parts:
            violations.append(f"{relative_path}: separate serializers layer is forbidden")

        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Serializer"):
                continue
            if len(relative_path.parts) < 2 or relative_path.parts[1] != "views":
                violations.append(
                    f"{relative_path}:{node.lineno}: {node.name} must be colocated with its view"
                )

            base_names = {
                base.value.id
                if isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name)
                else base.id
                if isinstance(base, ast.Name)
                else ""
                for base in node.bases
            }
            if "DataclassSerializer" not in base_names:
                violations.append(
                    f"{relative_path}:{node.lineno}: {node.name} must inherit "
                    "from DataclassSerializer"
                )

    assert not violations, "\n".join(violations)
