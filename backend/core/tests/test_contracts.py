import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from rest_framework.renderers import JSONRenderer
from rest_framework_dataclasses.serializers import DataclassSerializer

from core.contracts import Command, Dto, Query


@dataclass(frozen=True, slots=True)
class OrderCreateCommand(Command):
    customer_id: int


@dataclass(frozen=True, slots=True)
class OrderGetQuery(Query):
    order_id: int


@dataclass(frozen=True, slots=True)
class OrderGetDto(Dto):
    id: int


class OrderGetOutSerializer(DataclassSerializer[OrderGetDto]):
    class Meta:
        dataclass = OrderGetDto


def test_contract_dataclasses_are_serializable() -> None:
    """Given use-case data. When serialized. Then it contains only transport-safe values."""

    command = OrderCreateCommand(customer_id=1)
    query = OrderGetQuery(order_id=1)
    dto = OrderGetDto(id=1)

    assert json.loads(json.dumps(asdict(command))) == {"customer_id": 1}
    assert json.loads(json.dumps(asdict(query))) == {"order_id": 1}
    assert JSONRenderer().render(OrderGetOutSerializer(dto).data) == b'{"id":1}'


def test_application_contract_data_types_follow_the_contract() -> None:
    """Given application contracts. When checked. Then they are immutable and transport-safe."""

    apps_path = Path(__file__).parents[2] / "apps"
    sources: list[tuple[str, str, str | None]] = [
        (
            str(path.relative_to(apps_path)),
            path.read_text(),
            None,
        )
        for path in apps_path.rglob("*.py")
        if "migrations" not in path.parts
    ]
    sources.extend(
        [
            (
                "valid",
                """
@dataclass(frozen=True, slots=True)
class OrderCreateCommand(Command):
    customer_id: int

@dataclass(frozen=True, slots=True)
class OrderGetQuery(Query):
    order_id: int

@dataclass(frozen=True, slots=True)
class OrderGetDto(Dto):
    id: int
""",
                None,
            ),
            (
                "wrong-base",
                """
@dataclass(frozen=True, slots=True)
class OrderCreateCommand:
    customer_id: int
""",
                "must inherit from Command",
            ),
            (
                "mutable-command-field",
                """
@dataclass(frozen=True, slots=True)
class OrderCreateCommand(Command):
    customer_ids: list[int]
""",
                "has forbidden field types",
            ),
            (
                "orm-query-field",
                """
@dataclass(frozen=True, slots=True)
class OrderGetQuery(Query):
    order: OrderModel
""",
                "has forbidden field types",
            ),
        ]
    )

    contract_bases = {
        "Command": "Command",
        "Query": "Query",
        "Dto": "Dto",
    }
    forbidden_field_types = {
        "Any",
        "AsyncGenerator",
        "AsyncIterator",
        "Awaitable",
        "Collection",
        "Coroutine",
        "Deque",
        "Dict",
        "Generator",
        "Iterable",
        "Iterator",
        "List",
        "Manager",
        "Mapping",
        "Model",
        "MutableMapping",
        "MutableSequence",
        "MutableSet",
        "QuerySet",
        "RawQuerySet",
        "RelatedManager",
        "Sequence",
        "Set",
        "dict",
        "list",
        "set",
    }
    unexpected_violations: list[str] = []

    for label, source, expected_violation in sources:
        tree = ast.parse(source)
        violations: list[str] = []
        imported_model_names = {
            alias.asname or alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and (node.module == "models" or node.module.endswith(".models"))
            for alias in node.names
        }

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            contract_suffix = next(
                (suffix for suffix in contract_bases if node.name.endswith(suffix)),
                None,
            )
            if contract_suffix is None or node.name == contract_suffix:
                continue

            expected_base = contract_bases[contract_suffix]
            base_names = {
                base.value.id
                if isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name)
                else base.id
                if isinstance(base, ast.Name)
                else base.attr
                if isinstance(base, ast.Attribute)
                else ""
                for base in node.bases
            }
            if expected_base not in base_names:
                violations.append(
                    f"{label}:{node.lineno}: {node.name} must inherit from {expected_base}"
                )

            dataclass_decorator = next(
                (
                    decorator
                    for decorator in node.decorator_list
                    if isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Name)
                    and decorator.func.id == "dataclass"
                ),
                None,
            )
            dataclass_options = (
                {
                    keyword.arg: keyword.value.value
                    for keyword in dataclass_decorator.keywords
                    if keyword.arg is not None and isinstance(keyword.value, ast.Constant)
                }
                if dataclass_decorator is not None
                else {}
            )
            if not (
                dataclass_options.get("frozen") is True and dataclass_options.get("slots") is True
            ):
                violations.append(
                    f"{label}:{node.lineno}: {node.name} must be a frozen, slotted dataclass"
                )

            for field in node.body:
                if not isinstance(field, ast.AnnAssign):
                    continue
                annotation = field.annotation
                if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
                    annotation = ast.parse(annotation.value, mode="eval").body
                annotation_names = {
                    annotation.id
                    if isinstance(annotation, ast.Name)
                    else annotation.attr
                    if isinstance(annotation, ast.Attribute)
                    else ""
                    for annotation in ast.walk(annotation)
                }
                invalid_names = {
                    annotation_name
                    for annotation_name in annotation_names
                    if annotation_name in forbidden_field_types
                    or annotation_name in imported_model_names
                    or annotation_name.endswith(("Manager", "Model", "QuerySet"))
                }
                if invalid_names:
                    violations.append(
                        f"{label}:{field.lineno}: {node.name} has forbidden field types: "
                        f"{', '.join(sorted(invalid_names))}"
                    )

        rendered_violations = "\n".join(violations)
        if expected_violation is None:
            unexpected_violations.extend(violations)
        else:
            assert expected_violation in rendered_violations, (
                f"{label} did not produce {expected_violation!r}:\n{rendered_violations}"
            )

    assert not unexpected_violations, "\n".join(unexpected_violations)
