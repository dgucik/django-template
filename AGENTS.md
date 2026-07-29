# AGENTS.md

Repository-wide rules for AI agents and contributors.

## Architecture

Build a loosely coupled Django modular monolith with lightweight CQRS. Each app
in `backend/apps/` is an independent business module.

```text
apps/<module>/
├── urls.py                       # URL routing
├── views/
│   └── order_create_view.py
├── commands/
│   └── order_create_command.py  # command + handler
├── queries/
│   └── order_get_query.py       # query + handler + DTO
├── models/ or models.py
│   └── order_model.py
├── factories/
│   └── order_factory.py          # aggregate construction
└── services/ or services.py
    └── order_pricing_service.py  # domain logic outside the aggregate
```

Use `scripts/create_app.sh` to create this standard module structure. The
generated `factories/` and `services/` packages may remain empty until a use
case needs them. `models` and `services` may each be a single `.py` module or a
package; use a package when the module would become too large to maintain
clearly.

The immediate contents of every `apps/<module>/` directory are enforced by
`core/tests/test_app_structure.py`. Add a common new layer or framework file to
`GLOBAL_ALLOWED_APP_ELEMENTS` in that test. For a legitimate exception in one
module only, add it to `MODULE_ALLOWED_APP_ELEMENTS` in that test.

## Module boundaries

A module exposes only the `commands` and `queries` package interfaces. Their
public classes must be re-exported from the package `__init__.py`. Models,
services, factories, and files inside the public packages are implementation
details.

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

- Never import another module's models, services, or factories.
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
| Data Transfer Object | `OrderGetDto` | `order_get_query.py` |
| View | `OrderCreateView` | `order_create_view.py` |
| Input serializer | `OrderCreateInSerializer` | `order_create_view.py` |
| Output serializer | `OrderCreateOutSerializer` | `order_create_view.py` |
| Model | `OrderModel` | `order_model.py` |
| Domain service | `OrderPricingService` | `order_pricing_service.py` |
| Aggregate factory | `OrderFactory` | `order_factory.py` |

Use the entity first, the action second, and the layer suffix last. Use
`OrderCreateCommand`, never `CreateOrderCommand`. Models have no action segment
but must keep the `Model` suffix. Factories use the aggregate entity and the
`Factory` suffix, for example `OrderFactory`. Framework files such as
`admin.py`, `apps.py`, `urls.py`, migrations, and `__init__.py` are exceptions.

Keep all input, output, and handler types next to their use case:

- `order_create_command.py` contains `OrderCreateCommand` and `OrderCreateHandler`;
- `order_get_query.py` contains `OrderGetQuery`, `OrderGetHandler`, and
  `OrderGetDto`.

## Commands

Each write use case has a command dataclass and a handler:

```python
from core.contracts import Command
from core.handlers import CommandHandler


@dataclass(frozen=True, slots=True)
class OrderCreateCommand(Command):
    customer_id: int


class OrderCreateHandler(CommandHandler[OrderCreateCommand]):
    def handle(self, command: OrderCreateCommand) -> None:
        ...
```

- Commands contain serialization-safe input data only and inherit from
  `core.contracts.Command`.
- Handlers inherit directly from `CommandHandler`, expose only the synchronous
  public method `handle`, and always return `None`.
- `CommandHandler` wraps the complete use case in `transaction.atomic` on
  `default`.
- A command writes to the `default` database only. Do not attempt distributed
  transactions; coordinate cross-database work with an outbox or events.
- Use local models, services, and factories. Perform ORM writes directly in the
  handler; do not add a selector layer.
- Call other modules only through their commands or queries.
- Schedule irreversible side effects with `transaction.on_commit()`.

## Queries

Each read use case has a query, Data Transfer Object (DTO), and handler:

```python
from core.contracts import Dto, Query
from core.handlers import QueryHandler


@dataclass(frozen=True, slots=True)
class OrderGetQuery(Query):
    order_id: int


@dataclass(frozen=True, slots=True)
class OrderGetDto(Dto):
    id: int


class OrderGetHandler(QueryHandler[OrderGetQuery, OrderGetDto]):
    def handle(self, query: OrderGetQuery) -> OrderGetDto:
        ...
```

- Query handlers inherit directly from `QueryHandler` and expose only the
  synchronous public method `handle`.
- Queries contain serialization-safe input data only and inherit from
  `core.contracts.Query`.
- Queries never write or call commands. The ORM is routed to the handler's
  read-only database alias (`default_readonly` by default).
- Never bypass read-only routing with `.using("default")`, `connection`, or
  `connections["default"]`.
- PostgreSQL permissions are the write-prevention boundary. Configure a distinct
  read-only login role and revoke execution of unaudited application functions.
- Return local DTOs defined as `@dataclass(frozen=True, slots=True)` and
  inheriting from `core.contracts.Dto`. A DTO is a Data Transfer Object: the
  serializable internal interface of a query.
- Fully materialize results inside `handle`. DTO fields may contain only
  serialization-safe values and nested DTOs. They cannot contain Django models,
  querysets, managers, iterators, `Any`, or mutable collections.
- Re-export DTOs from the module's `queries` package. Other modules may consume
  them through that public interface, and the owning HTTP view may wrap them in
  a dataclass serializer. DTOs must not depend on DRF or an HTTP representation.
- Use local models, services, and factories. Perform ORM reads directly in the
  handler; do not add a selector layer.
- Read other modules only through their queries.
- Avoid N+1 queries.

## URLs

Keep URL routing in the module that owns the endpoint:

```python
from django.urls import URLPattern, URLResolver, path

from .views.order_create_view import OrderCreateView


urlpatterns: list[URLPattern | URLResolver] = [
    path("orders/", OrderCreateView.as_view(), name="order-create"),
]
```

- `urls.py` only connects a path to a local view. It contains no HTTP, domain,
  ORM, command, or query logic.

## Views and serializers

Keep the HTTP layer inside the module that owns the endpoint:

```text
apps/orders/
└── views/
    ├── order_create_view.py
    └── order_list_create_view.py
```

- Put every view in the module's `views/` package. Define its serializers in the
  same file as the view; do not create a `serializers/` layer or module-level
  `views.py` or `serializers.py`.
- Views inherit from `rest_framework.views.APIView` only. Django REST Framework
  generic views, `ViewSet`, `ModelViewSet`, mixins, and similar abstractions are
  forbidden.
- Serializers inherit from
  `rest_framework_dataclasses.serializers.DataclassSerializer` and declare their
  input command or output DTO in `Meta.dataclass`. `Serializer`,
  `ModelSerializer`, and their other subclasses are forbidden for application
  views.
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
- An input dataclass serializer validates request data into its command
  dataclass. An output dataclass serializer wraps a query DTO before its data is
  passed to `Response`. For example:

```python
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_dataclasses.serializers import DataclassSerializer

from ..commands import OrderCreateCommand, OrderCreateHandler
from ..queries import OrderGetDto, OrderGetHandler, OrderGetQuery


class OrderCreateInSerializer(DataclassSerializer[OrderCreateCommand]):
    """Validate an HTTP request into an order command."""

    class Meta:
        dataclass = OrderCreateCommand


class OrderGetOutSerializer(DataclassSerializer[OrderGetDto]):
    """Serialize an order DTO for the HTTP response."""

    class Meta:
        dataclass = OrderGetDto


class OrderGetView(APIView):
    """Return an order."""

    def get(self, request: Request, order_id: int) -> Response:
        dto = OrderGetHandler().handle(OrderGetQuery(order_id=order_id))
        return Response(OrderGetOutSerializer(dto).data)


class OrderCreateView(APIView):
    """Create an order."""

    def post(self, request: Request) -> Response:
        serializer = OrderCreateInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = serializer.validated_data
        OrderCreateHandler().handle(command)
        return Response(status=204)
```

- Keep views thin. A view validates request data with an input serializer,
  constructs a command or query, invokes its handler, serializes the result, and
  returns the HTTP response. Views contain no business logic and perform no
  direct ORM operations.
- Views may invoke commands and queries only from their own module, imported
  through that module's `commands` and `queries` package interfaces. They must
  never invoke another module's commands or queries directly.
- Serializers define the HTTP contract and validation only. They contain no
  business logic, ORM operations, or handler calls.

## Models and aggregates

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

The root exposes mutation operations only. Query handlers read local models
directly through the ORM and map results to DTOs. Command handlers load the
root and invoke one of its mutation methods inside the transaction supplied by
`CommandHandler`.

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

## Services

Services hold domain logic that does not naturally belong to one aggregate.
They are private to the module, receive only plain values or local domain
objects, and do not perform ORM reads or writes. Commands and queries use the
ORM directly.

```python
from decimal import Decimal, ROUND_HALF_UP


class OrderPricingService:
    """Calculate order prices outside the Order aggregate."""

    @staticmethod
    def calculate_discount(
        *,
        subtotal: Decimal,
        discount_rate: Decimal,
    ) -> Decimal:
        """Return the monetary discount for an order subtotal."""
        return (subtotal * discount_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

    @staticmethod
    def calculate_total(*, subtotal: Decimal, discount: Decimal) -> Decimal:
        """Return the order total after applying a discount."""
        return subtotal - discount
```

- Use a service for cohesive rules such as pricing, eligibility, or scheduling
  that need more than one domain value but do not belong to a model.
- Service methods are `@staticmethod`s. Services keep no instance state or
  dependencies; pass every required value explicitly.
- Services never become a cross-module API. Another module invokes the owning
  module through its commands or queries.

## Factories

Factories construct a new aggregate when its initial state needs more than a
simple model constructor. They are private to the module; the command handler
persists the aggregate inside its transaction.

```python
from ..models import OrderModel


class OrderFactory:
    """Create a new Order aggregate in its initial state."""

    @staticmethod
    def create(*, customer_id: int) -> OrderModel:
        """Construct an unsaved order aggregate for a customer."""
        return OrderModel(customer_id=customer_id)
```

- Use `OrderFactory` to centralize non-trivial aggregate construction, for
  example initial child entities or default state.
- Factory methods are `@staticmethod`s. Factories keep no instance state or
  dependencies; pass every construction input explicitly.
- Keep invariant-preserving mutations on the aggregate root, not in a factory.

## Shared technical code

- `backend/core/` contains only shared, domain-independent technical code.
- `core.exceptions.ApplicationError` is the base class for every custom
  application exception. Module-specific exceptions live in the module's
  `exceptions.py` and must inherit from `ApplicationError`. Built-in and
  framework exceptions are not application-defined custom exceptions.

## Summary

| Layer | Responsibility |
| --- | --- |
| `commands` | Write use cases. |
| `queries` | Read use cases and DTOs. |
| `models` | Aggregates and invariants. |
| `factories` | Aggregate construction. |
| `services` | Domain calculations. |
| `views` | HTTP and serializers. |
| `urls` | Route-to-view mapping. |
