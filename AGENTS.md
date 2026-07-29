# AGENTS.md

Repository-wide rules for AI agents and contributors.

## Architecture

Build a loosely coupled Django modular monolith with lightweight CQRS. Each app
in `backend/apps/` is an independent business module.

```text
apps/<module>/
├── views/
│   └── order_create_view.py
├── serializers/
│   └── order_create_serializer.py
├── commands/
│   └── order_create_command.py  # command + handler
├── queries/
│   └── order_get_query.py       # query + handler + view model
├── models/
│   └── order_model.py
├── services/     # optional domain services
├── factories/    # optional aggregate factories
└── selectors.py  # thin ORM read helpers
```

Use `scripts/create_app.sh` to create this standard module structure. Create
additional optional directories only when needed.
Use `selectors.py` by default; split it into a `selectors/` package only when it
becomes too large to maintain clearly.

## Module boundaries

A module exposes only the `commands` and `queries` package interfaces. Their
public classes must be re-exported from the package `__init__.py`. Models,
selectors, services, factories, and files inside the public packages are
implementation details.

```python
# Allowed
from apps.orders.commands import OrderCreateCommand, OrderCreateHandler
from apps.orders.queries import OrderGetQuery, OrderGetHandler

# Forbidden
from apps.orders.commands.order_create_command import OrderCreateCommand
from apps.orders.queries.order_get_query import OrderGetQuery
```

| Code in module A | May import from module B |
| --- | --- |
| `A.commands` | `B.commands`, `B.queries` |
| `A.queries` | `B.queries` |
| Other code in A | Nothing directly |

Rules:

- Never import another module's models, selectors, services, or factories.
- Import another module only through `apps.<module>.commands` or
  `apps.<module>.queries`, never from files below those packages.
- Local commands and queries do not import each other.
- Do not call another handler from the same command or query layer.
- Keep the module dependency graph acyclic.
- Before adding a cross-module import, define the modules' dependency level in
  an explicit Import Linter contract. Document which modules may import the new
  module and which modules the new module may import.
- Resolve cycles by changing ownership or using events, never hidden imports.

## Naming

Business class and file names follow:

```text
Entity + Action + Layer
entity_action_layer.py
```

Examples:

| Type | Class | File |
| --- | --- | --- |
| Command | `OrderCreateCommand` | `order_create_command.py` |
| Command handler | `OrderCreateHandler` | `order_create_command.py` |
| Query | `OrderGetQuery` | `order_get_query.py` |
| Query handler | `OrderGetHandler` | `order_get_query.py` |
| View model | `OrderGetViewModel` | `order_get_query.py` |
| View | `OrderCreateView` | `order_create_view.py` |
| Input serializer | `OrderCreateInSerializer` | `order_create_serializer.py` |
| Output serializer | `OrderCreateOutSerializer` | `order_create_serializer.py` |
| Model | `OrderModel` | `order_model.py` |
| Domain service | `OrderPricingService` | `order_pricing_service.py` |
| Aggregate factory | `OrderCreateFactory` | `order_create_factory.py` |

Use the entity first, the action second, and the layer suffix last. Use
`OrderCreateCommand`, never `CreateOrderCommand`. Models have no action segment
but must keep the `Model` suffix. Framework files such as `admin.py`, `apps.py`,
`urls.py`, `selectors.py`, migrations, and `__init__.py` are exceptions.

Keep all input, output, and handler types next to their use case:

- `order_create_command.py` contains `OrderCreateCommand` and `OrderCreateHandler`;
- `order_get_query.py` contains `OrderGetQuery`, `OrderGetHandler`, and
  `OrderGetViewModel`.

## Commands

Each write use case has a command dataclass and a handler:

```python
from core.handlers import CommandHandler


@dataclass(frozen=True, slots=True)
class OrderCreateCommand:
    customer_id: int


class OrderCreateHandler(CommandHandler[OrderCreateCommand]):
    def handle(self, command: OrderCreateCommand) -> None:
        ...
```

- Commands contain input data only.
- Handlers inherit directly from `CommandHandler`, expose only the synchronous
  public method `handle`, and always return `None`.
- `CommandHandler` wraps the complete use case in `transaction.atomic` on
  `default`.
- A command writes to the `default` database only. Do not attempt distributed
  transactions; coordinate cross-database work with an outbox or events.
- Use local models, selectors, services, and factories.
- Call other modules only through their commands or queries.
- Schedule irreversible side effects with `transaction.on_commit()`.

## Queries

Each read use case has a query, view model, and handler:

```python
from core.handlers import QueryHandler


@dataclass(frozen=True, slots=True)
class OrderGetQuery:
    order_id: int


@dataclass(frozen=True, slots=True)
class OrderGetViewModel:
    id: int


class OrderGetHandler(QueryHandler[OrderGetQuery, OrderGetViewModel]):
    def handle(self, query: OrderGetQuery) -> OrderGetViewModel:
        ...
```

- Query handlers inherit directly from `QueryHandler` and expose only the
  synchronous public method `handle`.
- Queries never write or call commands. The ORM is routed to the handler's
  read-only database alias (`default_readonly` by default).
- Never bypass read-only routing with `.using("default")`, `connection`, or
  `connections["default"]`.
- PostgreSQL permissions are the write-prevention boundary. Configure a distinct
  read-only login role and revoke execution of unaudited application functions.
- Return local view models defined as `@dataclass(frozen=True, slots=True)`.
- Fully materialize results inside `handle`. View-model fields cannot contain
  Django models, querysets, managers, iterators, `Any`, or mutable collections.
- Use local models, selectors, services, and factories.
- Read other modules only through their queries.
- Avoid N+1 queries.

## Views and serializers

Keep the HTTP layer inside the module that owns the endpoint:

```text
apps/orders/
├── views/
│   ├── order_create_view.py
│   └── order_list_create_view.py
└── serializers/
    ├── order_create_serializer.py
    └── order_list_serializer.py
```

- Put every view in the module's `views/` package and every serializer in its
  `serializers/` package. Do not use module-level `views.py` or `serializers.py`.
- Views inherit from `rest_framework.views.APIView` only. Django REST Framework
  generic views, `ViewSet`, `ModelViewSet`, mixins, and similar abstractions are
  forbidden.
- Serializers inherit from `rest_framework.serializers.Serializer` only.
  `ModelSerializer` and its subclasses are forbidden.
- Name a view after its entity and supported action, followed by `View`.
  For example, use `OrderCreateView` for a POST-only create endpoint and
  `OrderListCreateView` for an `orders/` collection endpoint supporting GET and
  POST.
- Name serializers after the view action they serve and their data direction:
  `<Entity><Action>InSerializer` for request data and
  `<Entity><Action>OutSerializer` for response data. For example,
  `OrderCreateInSerializer`, `OrderCreateOutSerializer`, and
  `OrderListOutSerializer`.
- A multi-method view uses the serializer matching each operation. For example,
  `OrderListCreateView.get()` uses `OrderListOutSerializer`, while
  `OrderListCreateView.post()` uses `OrderCreateInSerializer` and, when it
  returns a body, `OrderCreateOutSerializer`.
- Keep views thin. A view validates request data with an input serializer,
  constructs a command or query, invokes its handler, serializes the result, and
  returns the HTTP response. Views contain no business logic and perform no
  direct ORM operations.
- Views may invoke commands and queries only from their own module, imported
  through that module's `commands` and `queries` package interfaces. They must
  never invoke another module's commands or queries directly.
- Serializers define the HTTP contract and validation only. They contain no
  business logic, ORM operations, or handler calls.

## Aggregates

Prefer one aggregate per module.

- The aggregate root owns its child entities and enforces invariants.
- Child entities are not created or modified outside the aggregate.
- Other modules never import aggregate models.
- Keep business rules in the aggregate whenever possible.
- Add `services/` only for domain logic that does not belong to one model.
- Add `factories/` only for non-trivial aggregate construction.
- Use-case orchestration belongs in handlers.
- Do not use Django signals for cross-module workflows.

### Aggregate example

`ProductModel` is the aggregate root. It is the only model allowed to create or
modify `ProductYearModel` and `ProductSettingsModel`. The child entities are
data containers: they declare fields and database constraints but have no
domain methods.

The root exposes mutation operations only. Reads and projections belong in
selectors and query handlers. Command handlers load the root and invoke one of
its mutation methods inside the transaction supplied by `CommandHandler`.

The product module defines its custom exceptions in `apps/products/exceptions.py`.
Every custom exception inherits from `ApplicationError`:

```python
from core.exceptions import ApplicationError


class ProductNameEmptyError(ApplicationError):
    """Raised when a product name is empty."""


class ProductNotSavedError(ApplicationError):
    """Raised when an operation requires a persisted product."""


class ProductPriceInvalidError(ApplicationError):
    """Raised when a product price is invalid."""


class ProductYearAlreadyExistsError(ApplicationError):
    """Raised when a product already contains the requested year."""


class ProductYearInvalidError(ApplicationError):
    """Raised when a product year is invalid."""
```

```python
from decimal import Decimal

from django.db import models

from core.models import BaseModel

from ..exceptions import (
    ProductNameEmptyError,
    ProductNotSavedError,
    ProductPriceInvalidError,
    ProductYearAlreadyExistsError,
    ProductYearInvalidError,
)


class ProductModel(BaseModel):
    """Aggregate root that maintains the consistency of a product."""

    name = models.CharField(max_length=200)

    def update_name(self, *, name: str) -> None:
        """Update the product name while preserving its invariant."""
        normalized_name = name.strip()
        if not normalized_name:
            raise ProductNameEmptyError

        self.name = normalized_name
        self.save(update_fields=["name"])

    def add_new_year(self, *, year: int, price: Decimal) -> "ProductYearModel":
        """Create a unique year owned by this product."""
        if self.pk is None:
            raise ProductNotSavedError
        if year <= 0:
            raise ProductYearInvalidError
        if price < 0:
            raise ProductPriceInvalidError
        if ProductYearModel.objects.filter(product=self, year=year).exists():
            raise ProductYearAlreadyExistsError

        return ProductYearModel.objects.create(
            product=self,
            year=year,
            price=price,
        )

    def update_settings(self, *, sales_enabled: bool) -> None:
        """Create or update settings owned by this product."""
        if self.pk is None:
            raise ProductNotSavedError

        ProductSettingsModel.objects.update_or_create(
            product=self,
            defaults={"sales_enabled": sales_enabled},
        )


class ProductYearModel(BaseModel):
    """Year entity owned by a product aggregate."""

    product = models.ForeignKey(
        ProductModel,
        on_delete=models.CASCADE,
        related_name="years",
    )
    year = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "year"],
                name="unique_product_year",
            ),
        ]


class ProductSettingsModel(BaseModel):
    """Settings entity owned by a product aggregate."""

    product = models.OneToOneField(
        ProductModel,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    sales_enabled = models.BooleanField(default=False)
```

Code outside the aggregate must never call `ProductYearModel.objects.create`,
change a `ProductYearModel` directly, or create/update `ProductSettingsModel`.
Add another mutation method to `ProductModel` instead. This keeps aggregate
invariants in one place and prevents child entities from becoming independent
domain objects.

## Other layers

- Selectors are private, read-only Django ORM helpers without business rules.
- Services and factories are private and must not become cross-module APIs.
- `backend/core/` contains only shared, domain-independent technical code.
- `core.exceptions.ApplicationError` is the base class for every custom
  application exception. Module-specific exceptions live in the module's
  `exceptions.py` and must inherit from `ApplicationError`. Built-in and
  framework exceptions are not application-defined custom exceptions.

## Code quality

- Use Python 3.13, complete type annotations, mypy strict, and Ruff.
- Write Google-style docstrings for production classes, functions, and methods.
  Module and package docstrings are optional. Test functions use BDD docstrings
  containing explicit `Given`, `When`, and `Then` clauses.
- Write tests as pytest functions and use `pytest-django` for database access.
- Handler and view-model architecture constraints are enforced by
  `core/tests/test_handlers.py`; database permissions are verified by
  `core/tests/test_handlers_sqlite.py` and
  `core/tests/test_handlers_postgresql.py`.
- Every model under `backend/apps/` must inherit from `core.models.BaseModel`;
  this is enforced by `core/tests/test_models.py`.
- Relative imports within a business module and absolute imports across module
  boundaries, including the rule that only `commands` and `queries` are public
  module interfaces, are enforced by `core/tests/test_imports.py`.
- Mutation testing with `mutmut` covers function and method bodies under
  `backend/apps/`. Tests colocated in `apps/` participate in mutation runs but
  are not mutated. Architecture tests run separately against uninstrumented
  source code. New or changed business behavior must kill its mutants.
- Follow the `Entity + Action + Layer` naming convention.
- Avoid generic `Service`, `Manager`, and `utils.py` abstractions.
- Add tests for handlers, aggregate invariants, and bug fixes.
- Include migrations with model changes; do not edit applied migrations.
- Preserve existing user changes and avoid unrelated refactors.

## Required checks

Run from `backend/`:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run lint-imports
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest
../scripts/ci/backend/mutation-test.sh
```

Report checks that could not be run or did not pass.
