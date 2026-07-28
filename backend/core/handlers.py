from abc import ABC, abstractmethod
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import Any, ClassVar, NoReturn

from django.db import connections, transaction
from django.db.models import Model

_query_database_alias: ContextVar[str | None] = ContextVar(
    "query_database_alias",
    default=None,
)


class _QueryDatabaseRouter:
    def db_for_read(self, model: type[Model], **hints: Any) -> str | None:
        return _query_database_alias.get()

    def db_for_write(self, model: type[Model], **hints: Any) -> str | None:
        return _query_database_alias.get()


class CommandHandler[CommandT](ABC):
    """Execute a command atomically on the writer database."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Wrap each concrete command handler in a database transaction."""
        super().__init_subclass__(**kwargs)
        handle = cls.__dict__.get("handle")
        if handle is not None and not getattr(handle, "__isabstractmethod__", False):
            atomic_handle = transaction.atomic(using="default")(handle)
            type.__setattr__(cls, "handle", atomic_handle)

    @abstractmethod
    def handle(self, command: CommandT) -> None:
        """Execute the command."""
        raise NotImplementedError


class QueryHandler[QueryT, ResultT](ABC):
    """Execute a query through the read-only database connection."""

    database_alias: ClassVar[str] = "default_readonly"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Route each concrete query handler to its read-only connection."""
        super().__init_subclass__(**kwargs)
        handle = cls.__dict__.get("handle")
        if handle is None or getattr(handle, "__isabstractmethod__", False):
            return

        @wraps(handle)
        def read_only_handle(self: Any, query: Any) -> Any:
            def reject_writer_database(
                _execute: Callable[..., Any],
                _sql: str,
                _params: Any,
                _many: bool,
                _context: dict[str, Any],
            ) -> NoReturn:
                raise RuntimeError("Query handlers cannot use the default database")

            token = _query_database_alias.set(cls.database_alias)
            try:
                with connections["default"].execute_wrapper(reject_writer_database):
                    return handle(self, query)
            finally:
                _query_database_alias.reset(token)

        type.__setattr__(cls, "handle", read_only_handle)

    @abstractmethod
    def handle(self, query: QueryT) -> ResultT:
        """Execute the query and return a materialized result."""
        raise NotImplementedError
