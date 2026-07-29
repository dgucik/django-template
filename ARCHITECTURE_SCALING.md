# Architecture That Scales

**Commands and queries are the only public interfaces of an app. Every adapter
wraps a command or a query; nothing reaches around one.** This is the explicit
scaling rule: as requirements grow, replace or add wrappers and transport, but
do not change the domain-facing command/query interface, aggregates, services,
or their business rules. A command is a write use case and a query is a read
use case returning a DTO.

```text
HTTP API / form / template / task / consumer / another app / remote client
                                ↓
                              wrapper
                                ↓
              apps.<module>.commands or apps.<module>.queries
                                ↓
                    local services and aggregates
```

## Commands and queries are the scaling boundary

`commands` and `queries` are the only way one app communicates with another.
Even inside the monolith, an app never imports another app's models, factories,
services, or implementation files.

```python
from apps.orders.queries import OrderGetHandler, OrderGetQuery


order = OrderGetHandler().handle(OrderGetQuery(order_id=order_id))
```

Commands may call another app's public commands or queries. Queries may call
only another app's public queries. This keeps ownership of aggregates and
business rules local while allowing modules to compose use cases safely.

Commands, queries, and DTOs inherit from the corresponding `core.contracts`
marker, are immutable, and use serialization-safe fields. They can therefore
pass through a process, HTTP, a queue, or RPC without leaking Django models or
lazy ORM objects.

## Base: wrappers preserve the use-case boundary

A wrapper is a thin adapter around a public command or query interface. It
validates and maps input, invokes the use case, and maps its result to the
transport. It contains no business rules and never bypasses the interface.

The same use case can have many wrappers:

- DRF view and dataclass serializer for a JSON API;
- Django form and template view for server-rendered HTML;
- background task, CLI command, or message consumer;
- HTTP, RPC, or queue client when the app is remote.

Changing or adding a wrapper changes how the application is reached, not how
its domain logic works. The command/query contract remains stable for callers
while HTTP, Celery, queues, REST, gRPC, read replicas, and deployment topology
change around it. Commands retain transactional write ownership; queries return
materialized DTOs from the read path.

## Example 1: synchronous command → Celery event consumer

Initially, module A may synchronously call a public command in module B:

```python
# apps.orders.commands: direct in-process composition inside a command handler
from apps.inventory.commands import InventoryReserveCommand, InventoryReserveHandler


class OrderPlaceHandler(CommandHandler[OrderPlaceCommand]):
    def handle(self, command: OrderPlaceCommand) -> None:
        InventoryReserveHandler().handle(
            InventoryReserveCommand(order_id=command.order_id)
        )
```

When the side effect should be asynchronous, Orders writes an `OrderPlaced`
event to its outbox in the command transaction. The outbox publisher submits a
Celery task only after commit; the task is a consumer wrapper around the same
public Inventory command:

```python
# Celery consumer wrapper owned by Inventory
@shared_task
def consume_order_placed(*, order_id: int) -> None:
    from .commands import InventoryReserveCommand, InventoryReserveHandler

    InventoryReserveHandler().handle(InventoryReserveCommand(order_id=order_id))
```

The event introduces eventual consistency, but aggregate ownership and the
public `InventoryReserveCommand` interface stay unchanged. Celery is only the
transport wrapper; it does not contain inventory rules.

## Example 2: direct module query → REST or gRPC microservice wrapper

Initially, module A reads module B by importing B's public query interface:

```python
# apps.checkout.queries: direct local dependency inside a query handler
from apps.catalog.queries import ProductGetHandler, ProductGetQuery


class CheckoutGetHandler(QueryHandler[CheckoutGetQuery, CheckoutGetDto]):
    def handle(self, query: CheckoutGetQuery) -> CheckoutGetDto:
        product = ProductGetHandler().handle(
            ProductGetQuery(product_id=query.product_id)
        )
        return CheckoutGetDto(product_id=product.id, price=product.price)
```

After Catalog becomes a microservice, Checkout removes that direct import. Its
private wrapper maps Checkout's need to Catalog's versioned REST or gRPC
contract, then maps the response into Checkout-local data:

```python
# apps.checkout.services.catalog_api_query_wrapper.py
class CatalogApiQueryWrapper:
    @staticmethod
    def get(*, product_id: int) -> CatalogProductDto:
        payload = catalog_grpc.get_product(product_id=product_id)  # or REST call
        return CatalogProductDto(id=payload.id, price=payload.price)
```

`CatalogApiQueryWrapper` is the REST/gRPC adapter. Checkout's query handler
uses it as a local service and still returns its own DTO. Catalog's models and
implementation never leak into Checkout. Cross-service writes follow the same
pattern as Example 1: events and an outbox, never a shared transaction.

## Forms and templates

Django Forms and templates are presentation wrappers, just like API views. A
form maps request input to a command; a template receives a query DTO. They do
not contain aggregate rules or perform direct ORM work.

The current application policy uses `APIView` and dataclass serializers. If
server-rendered views are introduced, the presentation rules and corresponding
architecture tests must allow that wrapper type while preserving the same
command/query-only boundary.

## Boundary rule

**Scale by wrapping a use case, never by reaching around it.** Keep models,
factories, and services private to their owning app. Commands and queries are
the stable domain-facing contract consumed by HTTP, workers, templates, other
apps, and future services; only the wrapper and transport change as scale
demands it.
