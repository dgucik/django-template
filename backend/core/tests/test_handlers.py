import ast
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.db import connection, connections, router

from apps.users.models import User
from core.handlers import CommandHandler, QueryHandler, _query_database_alias


@dataclass(frozen=True, slots=True)
class ExampleViewModel:
    database_alias: str
    count: int


@pytest.mark.django_db(transaction=True)
def test_command_handler_is_always_atomic() -> None:
    """Given a failing command. When handled. Then its transaction is rolled back."""

    class ExampleError(Exception):
        pass

    class ExampleCommandHandler(CommandHandler[object]):
        def handle(self, command: object) -> None:
            assert connection.in_atomic_block
            User.objects.create(username="rollback-test")
            raise ExampleError

    with pytest.raises(ExampleError):
        ExampleCommandHandler().handle(object())
    assert not User.objects.filter(username="rollback-test").exists()


@pytest.mark.django_db(
    databases=["default", "default_readonly"],
    transaction=True,
)
def test_command_handler_always_uses_the_default_database() -> None:
    """Given a command handler. When handled. Then only the default database is atomic."""

    class ExampleCommandHandler(CommandHandler[object]):
        def handle(self, command: object) -> None:
            assert connection.in_atomic_block
            assert not connections["default_readonly"].in_atomic_block

    ExampleCommandHandler().handle(object())


@pytest.mark.django_db(databases=["default", "default_readonly"])
def test_query_handler_routes_reads_to_its_declared_database() -> None:
    """Given a query handler. When it reads. Then it uses its declared database."""

    class ExampleQueryHandler(QueryHandler[object, ExampleViewModel]):
        def handle(self, query: object) -> ExampleViewModel:
            return ExampleViewModel(
                database_alias=router.db_for_read(User),
                count=User.objects.count(),
            )

    assert ExampleQueryHandler().handle(object()) == ExampleViewModel(
        database_alias="default_readonly",
        count=0,
    )


def test_query_handler_routes_writes_to_its_read_only_database() -> None:
    """Given a query handler. When ORM selects a writer. Then it receives the read-only alias."""

    class ExampleQueryHandler(QueryHandler[object, ExampleViewModel]):
        def handle(self, query: object) -> ExampleViewModel:
            return ExampleViewModel(
                database_alias=router.db_for_write(User),
                count=0,
            )

    assert ExampleQueryHandler().handle(object()).database_alias == "default_readonly"


@pytest.mark.django_db(databases=["default", "default_readonly"])
def test_query_handler_cannot_use_an_explicit_writer_queryset() -> None:
    """Given a query handler. When it selects the writer explicitly. Then execution is rejected."""

    class ExampleQueryHandler(QueryHandler[object, ExampleViewModel]):
        def handle(self, query: object) -> ExampleViewModel:
            return ExampleViewModel(
                database_alias="default",
                count=User.objects.using("default").count(),
            )

    with pytest.raises(RuntimeError, match="cannot use the default database"):
        ExampleQueryHandler().handle(object())


@pytest.mark.django_db(databases=["default", "default_readonly"])
def test_query_handler_cannot_use_the_writer_connection_directly() -> None:
    """Given a query handler. When it opens the writer connection. Then execution is rejected."""

    class ExampleQueryHandler(QueryHandler[object, ExampleViewModel]):
        def handle(self, query: object) -> ExampleViewModel:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM users_user")
                row = cursor.fetchone()
            assert row is not None
            return ExampleViewModel(database_alias="default", count=row[0])

    with pytest.raises(RuntimeError, match="cannot use the default database"):
        ExampleQueryHandler().handle(object())


def test_query_handler_does_not_open_its_database_without_an_orm_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given a query without ORM work. When handled. Then no database connection is opened."""

    ensure_connection = MagicMock(side_effect=AssertionError("unexpected database connection"))
    monkeypatch.setattr(
        connections["default_readonly"],
        "ensure_connection",
        ensure_connection,
    )

    class ExampleQueryHandler(QueryHandler[object, ExampleViewModel]):
        def handle(self, query: object) -> ExampleViewModel:
            return ExampleViewModel(database_alias=self.database_alias, count=0)

    assert ExampleQueryHandler().handle(object()).count == 0
    ensure_connection.assert_not_called()


@pytest.mark.django_db(
    databases=["default", "default_readonly"],
    transaction=True,
)
def test_query_handler_can_run_inside_a_command_transaction() -> None:
    """Given an atomic command. When it invokes a query. Then the read-only connection is used."""

    class ExampleQueryHandler(QueryHandler[object, ExampleViewModel]):
        def handle(self, query: object) -> ExampleViewModel:
            return ExampleViewModel(
                database_alias=router.db_for_read(User),
                count=User.objects.count(),
            )

    class ExampleCommandHandler(CommandHandler[object]):
        def handle(self, command: object) -> None:
            assert connection.in_atomic_block
            result = ExampleQueryHandler().handle(object())
            assert result.database_alias == "default_readonly"
            assert result.count == 0

    ExampleCommandHandler().handle(object())


def test_query_handler_restores_database_routing_after_an_exception() -> None:
    """Given a failing query. When handling exits. Then the previous routing context is restored."""

    class ExampleError(Exception):
        pass

    class ExampleQueryHandler(QueryHandler[object, ExampleViewModel]):
        def handle(self, query: object) -> ExampleViewModel:
            assert _query_database_alias.get() == "default_readonly"
            raise ExampleError

    with pytest.raises(ExampleError):
        ExampleQueryHandler().handle(object())
    assert _query_database_alias.get() is None


@pytest.mark.django_db(databases=["default", "default_readonly"])
def test_query_handler_returns_a_materialized_view_model(
    django_assert_num_queries: Any,
) -> None:
    """Given a query result. When accessed after handling. Then it performs no deferred queries."""

    class ExampleQueryHandler(QueryHandler[object, ExampleViewModel]):
        def handle(self, query: object) -> ExampleViewModel:
            return ExampleViewModel(
                database_alias=router.db_for_read(User),
                count=User.objects.count(),
            )

    with django_assert_num_queries(1, using="default_readonly"):
        result = ExampleQueryHandler().handle(object())
    with django_assert_num_queries(0, using="default_readonly"):
        assert asdict(result) == {
            "database_alias": "default_readonly",
            "count": 0,
        }


def test_application_handlers_and_view_models_follow_the_contract() -> None:
    """Given application code. When its AST is checked. Then handler contracts are enforced."""

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
class OrderGetViewModel:
    id: int

class OrderGetHandler(QueryHandler[OrderGetQuery, OrderGetViewModel]):
    def handle(self, query: OrderGetQuery) -> OrderGetViewModel:
        ...
""",
                None,
            ),
            (
                "additional-method",
                """
class OrderCreateHandler(CommandHandler[OrderCreateCommand]):
    def handle(self, command: OrderCreateCommand) -> None:
        ...
    def execute(self) -> None:
        ...
""",
                "must expose only handle",
            ),
            (
                "assigned-public-callable",
                """
class OrderCreateHandler(CommandHandler[OrderCreateCommand]):
    execute = lambda self: None
    def handle(self, command: OrderCreateCommand) -> None:
        ...
""",
                "must expose only handle",
            ),
            (
                "async-handler",
                """
class OrderGetHandler(QueryHandler[OrderGetQuery, OrderGetViewModel]):
    async def handle(self, query: OrderGetQuery) -> OrderGetViewModel:
        ...
""",
                "handle must be synchronous",
            ),
            (
                "handler-mixin",
                """
class OrderGetHandler(LoggingMixin, QueryHandler[OrderGetQuery, OrderGetViewModel]):
    def handle(self, query: OrderGetQuery) -> OrderGetViewModel:
        ...
""",
                "must inherit directly",
            ),
            (
                "handler-without-suffix",
                """
class OrderProcessor(QueryHandler[OrderGetQuery, OrderGetViewModel]):
    def handle(self, query: OrderGetQuery) -> OrderGetViewModel:
        ...
""",
                "must use the Handler suffix",
            ),
            (
                "invalid-query-result",
                """
class OrderGetHandler(QueryHandler[OrderGetQuery, list[int]]):
    def handle(self, query: OrderGetQuery) -> list[int]:
        ...
""",
                "must use a local ViewModel result",
            ),
            (
                "invalid-view-model",
                """
@dataclass(frozen=True)
class OrderGetViewModel:
    orders: QuerySet[OrderModel]
""",
                "must be a frozen, slotted dataclass",
            ),
            (
                "lazy-view-model-field",
                """
@dataclass(frozen=True, slots=True)
class OrderGetViewModel:
    orders: QuerySet[OrderModel]
""",
                "has forbidden field types",
            ),
            (
                "django-model-field",
                """
from apps.users import models

@dataclass(frozen=True, slots=True)
class UserGetViewModel:
    user: models.User
""",
                "has forbidden field types",
            ),
            (
                "mismatched-return",
                """
class OrderGetHandler(QueryHandler[OrderGetQuery, OrderGetViewModel]):
    def handle(self, query: OrderGetQuery) -> OtherViewModel:
        ...
""",
                "return annotation must match",
            ),
        ]
    )

    unexpected_violations: list[str] = []
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

    for label, source, expected_violation in sources:
        tree = ast.parse(source)
        violations: list[str] = []
        local_view_model_names = {
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name.endswith("ViewModel")
        }
        imported_model_names = {
            alias.asname or alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and (node.module == "models" or node.module.endswith(".models"))
            for alias in node.names
        }
        imported_model_modules = {
            alias.asname or alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and any(alias.name == "models" for alias in node.names)
            for alias in node.names
            if alias.name == "models"
        } | {
            alias.asname or alias.name.rsplit(".", maxsplit=1)[-1]
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name.endswith(".models")
        }

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            if node.name.endswith("ViewModel"):
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
                    dataclass_options.get("frozen") is True
                    and dataclass_options.get("slots") is True
                ):
                    violations.append(
                        f"{label}:{node.lineno}: {node.name} must be a frozen, slotted dataclass"
                    )

                for field in node.body:
                    if not isinstance(field, ast.AnnAssign):
                        continue
                    annotation = field.annotation
                    if isinstance(annotation, ast.Constant) and isinstance(
                        annotation.value,
                        str,
                    ):
                        annotation = ast.parse(annotation.value, mode="eval").body
                    annotation_names = {
                        annotation.id
                        if isinstance(annotation, ast.Name)
                        else annotation.attr
                        if isinstance(annotation, ast.Attribute)
                        else ""
                        for annotation in ast.walk(annotation)
                    }
                    annotation_model_modules = {
                        annotation.value.id
                        for annotation in ast.walk(annotation)
                        if isinstance(annotation, ast.Attribute)
                        and isinstance(annotation.value, ast.Name)
                    }
                    invalid_names = {
                        annotation_name
                        for annotation_name in annotation_names
                        if annotation_name in forbidden_field_types
                        or annotation_name in imported_model_names
                        or annotation_name.endswith(("Manager", "QuerySet"))
                        or (
                            annotation_name.endswith("Model")
                            and not annotation_name.endswith("ViewModel")
                        )
                    }
                    invalid_names.update(annotation_model_modules & imported_model_modules)
                    if invalid_names:
                        violations.append(
                            f"{label}:{field.lineno}: {node.name} has forbidden field types: "
                            f"{', '.join(sorted(invalid_names))}"
                        )

            handler_bases: list[tuple[ast.expr, str]] = []
            for raw_handler_base in node.bases:
                handler_base = (
                    raw_handler_base.value
                    if isinstance(raw_handler_base, ast.Subscript)
                    else raw_handler_base
                )
                handler_base_name = (
                    handler_base.id
                    if isinstance(handler_base, ast.Name)
                    else handler_base.attr
                    if isinstance(handler_base, ast.Attribute)
                    else ""
                )
                if handler_base_name in {"CommandHandler", "QueryHandler"}:
                    handler_bases.append((raw_handler_base, handler_base_name))

            if not handler_bases:
                continue

            raw_base, base_name = handler_bases[0]
            if not node.name.endswith("Handler"):
                violations.append(f"{label}:{node.lineno}: {node.name} must use the Handler suffix")

            if len(node.bases) != 1 or len(handler_bases) != 1:
                violations.append(
                    f"{label}:{node.lineno}: {node.name} must inherit directly from one handler ABC"
                )

            public_methods = [
                child
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not child.name.startswith("_")
            ]
            public_callable_assignments = [
                child
                for child in node.body
                if isinstance(child, (ast.Assign, ast.AnnAssign))
                and (
                    (
                        isinstance(child, ast.Assign)
                        and any(
                            isinstance(target, ast.Name) and not target.id.startswith("_")
                            for target in child.targets
                        )
                    )
                    or (
                        isinstance(child, ast.AnnAssign)
                        and isinstance(child.target, ast.Name)
                        and not child.target.id.startswith("_")
                    )
                )
                and (
                    isinstance(child.value, ast.Lambda)
                    or (
                        isinstance(child.value, ast.Call)
                        and isinstance(child.value.func, ast.Name)
                        and child.value.func.id in {"classmethod", "property", "staticmethod"}
                    )
                )
            ]
            if (
                len(public_methods) != 1
                or public_methods[0].name != "handle"
                or public_callable_assignments
            ):
                violations.append(f"{label}:{node.lineno}: {node.name} must expose only handle")
                continue

            handle = public_methods[0]
            if isinstance(handle, ast.AsyncFunctionDef):
                violations.append(
                    f"{label}:{handle.lineno}: {node.name}.handle must be synchronous"
                )

            forbidden_decorators = {
                decorator.id
                for decorator in handle.decorator_list
                if isinstance(decorator, ast.Name)
            } & {"classmethod", "property", "staticmethod"}
            if forbidden_decorators:
                violations.append(
                    f"{label}:{handle.lineno}: {node.name}.handle must be an instance method"
                )

            if base_name == "CommandHandler":
                if not (isinstance(handle.returns, ast.Constant) and handle.returns.value is None):
                    violations.append(
                        f"{label}:{handle.lineno}: {node.name}.handle must return None"
                    )
                continue

            result_name = ""
            if isinstance(raw_base, ast.Subscript) and isinstance(raw_base.slice, ast.Tuple):
                generic_arguments = raw_base.slice.elts
                if len(generic_arguments) == 2:
                    result_type = generic_arguments[1]
                    result_name = (
                        result_type.id
                        if isinstance(result_type, ast.Name)
                        else result_type.attr
                        if isinstance(result_type, ast.Attribute)
                        else ""
                    )
            if (
                result_name == "ViewModel"
                or not result_name.endswith("ViewModel")
                or result_name not in local_view_model_names
            ):
                violations.append(
                    f"{label}:{node.lineno}: {node.name} must use a local ViewModel result"
                )

            return_name = (
                handle.returns.id
                if isinstance(handle.returns, ast.Name)
                else handle.returns.attr
                if isinstance(handle.returns, ast.Attribute)
                else handle.returns.value
                if isinstance(handle.returns, ast.Constant)
                and isinstance(handle.returns.value, str)
                else ""
            )
            if result_name and return_name != result_name:
                violations.append(
                    f"{label}:{handle.lineno}: {node.name}.handle "
                    "return annotation must match its generic result"
                )

        rendered_violations = "\n".join(violations)
        if expected_violation is None:
            unexpected_violations.extend(violations)
        else:
            assert expected_violation in rendered_violations, (
                f"{label} did not produce {expected_violation!r}:\n{rendered_violations}"
            )

    assert not unexpected_violations, "\n".join(unexpected_violations)
