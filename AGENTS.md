# AGENTS.md

Repository-wide rules for AI agents and contributors.

## Architecture

Build a loosely coupled Django modular monolith with lightweight CQRS. Each app
in `backend/apps/` is an independent business module.

```text
apps/<module>/
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

Create optional directories only when needed.
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
| Model | `OrderModel` | `order_model.py` |
| Domain service | `OrderPricingService` | `order_pricing_service.py` |
| Aggregate factory | `OrderCreateFactory` | `order_create_factory.py` |

Use the entity first, the action second, and the layer suffix last. Use
`OrderCreateCommand`, never `CreateOrderCommand`. Models have no action segment
but must keep the `Model` suffix. Framework files such as `admin.py`, `apps.py`,
`urls.py`, `views.py`, `selectors.py`, migrations, and `__init__.py` are exceptions.

Keep all input, output, and handler types next to their use case:

- `order_create_command.py` contains `OrderCreateCommand` and `OrderCreateHandler`;
- `order_get_query.py` contains `OrderGetQuery`, `OrderGetHandler`, and
  `OrderGetViewModel`.

## Commands

Each write use case has a command dataclass and a handler:

```python
@dataclass(frozen=True, slots=True)
class OrderCreateCommand:
    customer_id: int


class OrderCreateHandler:
    @transaction.atomic
    def handle(self, command: OrderCreateCommand) -> None:
        ...
```

- Commands contain input data only.
- Handlers implement one use case and always return `None`.
- The complete use case runs inside `transaction.atomic`.
- Use local models, selectors, services, and factories.
- Call other modules only through their commands or queries.
- Schedule irreversible side effects with `transaction.on_commit()`.

## Queries

Each read use case has a query, view model, and handler:

```python
@dataclass(frozen=True, slots=True)
class OrderGetQuery:
    order_id: int


@dataclass(frozen=True, slots=True)
class OrderGetViewModel:
    id: int


class OrderGetHandler:
    def handle(self, query: OrderGetQuery) -> OrderGetViewModel:
        ...
```

- Queries never write or call commands.
- Return immutable view models, not Django models.
- Use local models, selectors, services, and factories.
- Read other modules only through their queries.
- Avoid N+1 queries.

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

## Other layers

- Selectors are private, read-only Django ORM helpers without business rules.
- Services and factories are private and must not become cross-module APIs.
- Views and serializers validate input, call handlers, and map results.
- Views and serializers do not contain business logic or direct ORM operations.
- `backend/core/` contains only shared, domain-independent technical code.

## Code quality

- Use Python 3.13, complete type annotations, mypy strict, and Ruff.
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
uv run python manage.py test
```

Report checks that could not be run or did not pass.
