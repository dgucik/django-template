# Worked Architecture Examples

## Business scenario

A customer places an order for Catalog products. Orders keeps a historical
snapshot of the customer and product name/price on every line, so later changes
in Customers or Catalog do not change an already placed order. Catalog remains
the source of current availability and fulfillment time. The fulfillment
overview therefore combines the saved Order with current Catalog data to answer
whether every requested line can be fulfilled and when.

The examples use only the local modular-monolith boundary: apps call another
app directly through its public `commands` or `queries` package.

```text
HTTP view → Orders command → Customers/Catalog queries → factory/services → Order
HTTP view → Orders query   → local ORM + Catalog query + services          → DTO
```

## App `catalog`: public data supplied to other apps

Catalog exposes the product data needed by Order use cases. Orders imports only
this package interface, never a Catalog model or service.

```python
# apps/catalog/queries/__init__.py -- the Catalog public interface
from .product_fulfillment_data_get_query import (
    ProductFulfillmentDataGetDto,
    ProductFulfillmentDataGetHandler,
    ProductFulfillmentDataGetQuery,
)


# apps/catalog/queries/product_fulfillment_data_get_query.py
@dataclass(frozen=True, slots=True)
class ProductFulfillmentDataGetQuery(Query):
    product_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ProductFulfillmentDataItemDto(Dto):
    product_id: int
    name: str
    unit_price: Decimal
    available_quantity: int
    fulfillment_days: int


@dataclass(frozen=True, slots=True)
class ProductFulfillmentDataGetDto(Dto):
    products: tuple[ProductFulfillmentDataItemDto, ...]


class ProductFulfillmentDataGetHandler(
    QueryHandler[ProductFulfillmentDataGetQuery, ProductFulfillmentDataGetDto]
):
    def handle(
        self,
        query: ProductFulfillmentDataGetQuery,
    ) -> ProductFulfillmentDataGetDto:
        products = ProductModel.objects.filter(id__in=query.product_ids).order_by("id")
        return ProductFulfillmentDataGetDto(
            products=tuple(
                ProductFulfillmentDataItemDto(
                    product_id=product.id,
                    name=product.name,
                    unit_price=product.unit_price,
                    available_quantity=product.available_quantity,
                    fulfillment_days=product.fulfillment_days,
                )
                for product in products
            )
        )
```

## App `customers`: public customer data

Orders needs a customer snapshot when creating an order. It receives that data
through the Customers public query.

```python
# apps/customers/queries/customer_get_query.py
@dataclass(frozen=True, slots=True)
class CustomerGetQuery(Query):
    customer_id: int


@dataclass(frozen=True, slots=True)
class CustomerGetDto(Dto):
    id: int
    full_name: str
    email: str
    default_currency: str


class CustomerGetHandler(QueryHandler[CustomerGetQuery, CustomerGetDto]):
    def handle(self, query: CustomerGetQuery) -> CustomerGetDto:
        customer = CustomerModel.objects.get(id=query.customer_id)
        return CustomerGetDto(
            id=customer.id,
            full_name=customer.full_name,
            email=customer.email,
            default_currency=customer.default_currency,
        )
```

## App `orders`: command to place an order

The handler obtains external facts through queries, uses simple local
calculations, and asks its aggregate to mutate itself. It does not create an
`OrderLineModel` directly.

```python
# apps/orders/commands/order_place_command.py
from apps.catalog.queries import (
    ProductFulfillmentDataGetHandler,
    ProductFulfillmentDataGetQuery,
)
from apps.customers.queries import CustomerGetHandler, CustomerGetQuery

from ..factories.order_factory import OrderFactory, _OrderInitialLine
from ..services.order_pricing_service import OrderPricingService


@dataclass(frozen=True, slots=True)
class _OrderPlaceLineCommand(Command):
    product_id: int
    quantity: int


@dataclass(frozen=True, slots=True)
class OrderPlaceCommand(Command):
    customer_id: int
    lines: tuple[_OrderPlaceLineCommand, ...]


class OrderPlaceHandler(CommandHandler[OrderPlaceCommand]):
    def handle(self, command: OrderPlaceCommand) -> None:
        customer = CustomerGetHandler().handle(
            CustomerGetQuery(customer_id=command.customer_id)
        )
        catalog = ProductFulfillmentDataGetHandler().handle(
            ProductFulfillmentDataGetQuery(
                product_ids=tuple(line.product_id for line in command.lines),
            )
        )
        products_by_id = {product.product_id: product for product in catalog.products}
        if products_by_id.keys() != {line.product_id for line in command.lines}:
            raise OrderProductUnavailableError

        initial_lines = tuple(
            _OrderInitialLine(
                product_id=line.product_id,
                product_name=products_by_id[line.product_id].name,
                quantity=line.quantity,
                unit_price=products_by_id[line.product_id].unit_price,
                line_total=OrderPricingService.calculate_line_total(
                    quantity=line.quantity,
                    unit_price=products_by_id[line.product_id].unit_price,
                ),
            )
            for line in command.lines
        )
        order = OrderFactory.create(
            customer_id=customer.id,
            customer_name=customer.full_name,
            customer_email=customer.email,
            currency=customer.default_currency,
            initial_lines=initial_lines,
        )
        order.place()
```

`OrderFactory` receives scalar customer fields and a private, typed collection
of initial lines. It creates the initial root and its owned lines, including a
snapshot of customer data; later Customer changes do not rewrite a historical
order.

```python
# apps/orders/factories/order_factory.py
@dataclass(frozen=True, slots=True)
class _OrderInitialLine:
    """Private construction data for one initial Order line."""

    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class OrderFactory:
    @staticmethod
    def create(
        *,
        customer_id: int,
        customer_name: str,
        customer_email: str,
        currency: str,
        initial_lines: tuple[_OrderInitialLine, ...],
    ) -> OrderModel:
        order = OrderModel.objects.create(
            customer_id=customer_id,
            customer_name=customer_name,
            customer_email=customer_email,
            currency=currency,
            status=OrderStatus.DRAFT,
            total=Decimal("0"),
        )
        for line in initial_lines:
            OrderLineModel.objects.create(
                order=order,
                product_id=line.product_id,
                product_name=line.product_name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
        return order
```

Services are small stateless calculations over primitives. The handler performs
the per-line loop and passes calculated values to the aggregate.

```python
# apps/orders/services/order_pricing_service.py
class OrderPricingService:
    @staticmethod
    def calculate_line_total(*, quantity: int, unit_price: Decimal) -> Decimal:
        if quantity <= 0:
            raise OrderLineQuantityInvalidError
        return quantity * unit_price
```

The aggregate owns all local persistence and invariants for its children.

```python
# apps/orders/models/order_model.py -- the Orders aggregate and its persistence
class OrderModel(BaseModel):
    customer_id = models.PositiveBigIntegerField()
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=OrderStatus.choices)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    def place(self) -> None:
        lines = tuple(self.lines.all())
        if not lines:
            raise OrderLinesEmptyError
        self.total = sum((line.line_total for line in lines), Decimal("0"))
        self.status = OrderStatus.PLACED
        self.save(update_fields=("total", "status"))


class OrderLineModel(BaseModel):
    order = models.ForeignKey(OrderModel, on_delete=models.CASCADE, related_name="lines")
    product_id = models.PositiveBigIntegerField()
    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
```

## App `orders`: business query composed from Orders and Catalog

`OrderFulfillmentOverviewGet` answers a business question rather than returning
an Order row. It reads the local aggregate, obtains current availability from
Catalog, calculates every line in a loop, and returns a fully materialized DTO.

```python
# apps/orders/queries/order_fulfillment_overview_get_query.py
from apps.catalog.queries import (
    ProductFulfillmentDataGetHandler,
    ProductFulfillmentDataGetQuery,
)

from ..services.order_fulfillment_service import OrderFulfillmentService
from ..services.order_pricing_service import OrderPricingService


@dataclass(frozen=True, slots=True)
class OrderFulfillmentOverviewGetQuery(Query):
    order_id: int


@dataclass(frozen=True, slots=True)
class OrderFulfillmentOverviewLineDto(Dto):
    product_name: str
    quantity: int
    line_total: Decimal
    available_quantity: int
    can_fulfill: bool
    fulfillment_days: int


@dataclass(frozen=True, slots=True)
class OrderFulfillmentOverviewGetDto(Dto):
    order_id: int
    total: Decimal
    can_fulfill: bool
    estimated_fulfillment_days: int
    lines: tuple[OrderFulfillmentOverviewLineDto, ...]


class OrderFulfillmentOverviewGetHandler(
    QueryHandler[OrderFulfillmentOverviewGetQuery, OrderFulfillmentOverviewGetDto]
):
    def handle(
        self,
        query: OrderFulfillmentOverviewGetQuery,
    ) -> OrderFulfillmentOverviewGetDto:
        order = OrderModel.objects.prefetch_related("lines").get(id=query.order_id)
        order_lines = tuple(order.lines.all())
        catalog = ProductFulfillmentDataGetHandler().handle(
            ProductFulfillmentDataGetQuery(
                product_ids=tuple(line.product_id for line in order_lines),
            )
        )
        products_by_id = {product.product_id: product for product in catalog.products}
        if products_by_id.keys() != {line.product_id for line in order_lines}:
            raise OrderProductUnavailableError

        overview_lines: list[OrderFulfillmentOverviewLineDto] = []
        for line in order_lines:
            product = products_by_id[line.product_id]
            can_fulfill = OrderFulfillmentService.can_fulfill_line(
                available_quantity=product.available_quantity,
                requested_quantity=line.quantity,
            )
            overview_lines.append(
                OrderFulfillmentOverviewLineDto(
                    product_name=line.product_name,
                    quantity=line.quantity,
                    line_total=OrderPricingService.calculate_line_total(
                        quantity=line.quantity,
                        unit_price=line.unit_price,
                    ),
                    available_quantity=product.available_quantity,
                    can_fulfill=can_fulfill,
                    fulfillment_days=OrderFulfillmentService.fulfillment_days(
                        can_fulfill=can_fulfill,
                        base_fulfillment_days=product.fulfillment_days,
                    ),
                )
            )

        lines = tuple(overview_lines)
        return OrderFulfillmentOverviewGetDto(
            order_id=order.id,
            total=sum((line.line_total for line in lines), Decimal("0")),
            can_fulfill=all(line.can_fulfill for line in lines),
            estimated_fulfillment_days=max(
                (line.fulfillment_days for line in lines),
                default=0,
            ),
            lines=lines,
        )
```

```python
# apps/orders/services/order_fulfillment_service.py
class OrderFulfillmentService:
    @staticmethod
    def can_fulfill_line(*, available_quantity: int, requested_quantity: int) -> bool:
        return available_quantity >= requested_quantity

    @staticmethod
    def fulfillment_days(*, can_fulfill: bool, base_fulfillment_days: int) -> int:
        return base_fulfillment_days if can_fulfill else 0
```

## App `orders`: HTTP view

The view only maps HTTP input/output and calls Orders' own public interfaces.

```python
# apps/orders/views/order_place_view.py
class OrderPlaceInSerializer(DataclassSerializer[OrderPlaceCommand]):
    class Meta:
        dataclass = OrderPlaceCommand


class OrderFulfillmentOverviewOutSerializer(
    DataclassSerializer[OrderFulfillmentOverviewGetDto]
):
    class Meta:
        dataclass = OrderFulfillmentOverviewGetDto


class OrderPlaceView(APIView):
    def post(self, request: Request) -> Response:
        serializer = OrderPlaceInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        OrderPlaceHandler().handle(serializer.validated_data)
        return Response(status=204)


class OrderFulfillmentOverviewGetView(APIView):
    def get(self, request: Request, order_id: int) -> Response:
        dto = OrderFulfillmentOverviewGetHandler().handle(
            OrderFulfillmentOverviewGetQuery(order_id=order_id)
        )
        return Response(OrderFulfillmentOverviewOutSerializer(dto).data)
```

`views` map HTTP, `commands` write through their aggregate, `queries` compose
business read DTOs, `factories` initialize aggregates, and `services` perform
small local calculations. Nothing imports another app outside its public
`commands` or `queries` package.
