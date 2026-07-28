from abc import ABC, abstractmethod
from contextvars import ContextVar
from functools import wraps
from typing import Any, ClassVar

from django.db import transaction
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
    database_alias: ClassVar[str] = "default"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        handle = cls.__dict__.get("handle")
        if handle is not None and not getattr(handle, "__isabstractmethod__", False):
            atomic_handle = transaction.atomic(using=cls.database_alias)(handle)
            type.__setattr__(cls, "handle", atomic_handle)

    @abstractmethod
    def handle(self, command: CommandT) -> None:
        raise NotImplementedError


class QueryHandler[QueryT, ResultT](ABC):
    database_alias: ClassVar[str] = "default_readonly"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        handle = cls.__dict__.get("handle")
        if handle is None or getattr(handle, "__isabstractmethod__", False):
            return

        @wraps(handle)
        def read_only_handle(self: Any, query: Any) -> Any:
            token = _query_database_alias.set(cls.database_alias)
            try:
                return handle(self, query)
            finally:
                _query_database_alias.reset(token)

        type.__setattr__(cls, "handle", read_only_handle)

    @abstractmethod
    def handle(self, query: QueryT) -> ResultT:
        raise NotImplementedError
