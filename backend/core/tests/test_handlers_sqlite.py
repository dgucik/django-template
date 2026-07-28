from dataclasses import dataclass
from pathlib import Path

import pytest
from django.db import OperationalError, router
from django.db.utils import ConnectionHandler

from apps.users.models import User
from core.handlers import QueryHandler

pytestmark = pytest.mark.sqlite


@dataclass(frozen=True, slots=True)
class SQLiteResultViewModel:
    value: str


@pytest.mark.django_db(databases=["default", "default_readonly"])
def test_query_handler_cannot_write_to_a_read_only_sqlite_connection(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "database.sqlite3"
    test_connections = ConnectionHandler(
        {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": database_path,
            },
            "default_readonly": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": f"file:{database_path}?mode=ro",
                "OPTIONS": {"uri": True},
            },
        }
    )

    with test_connections["default"].cursor() as cursor:
        cursor.execute("CREATE TABLE example (value TEXT NOT NULL)")

    class ExampleCreateHandler(QueryHandler[object, SQLiteResultViewModel]):
        def handle(self, query: object) -> SQLiteResultViewModel:
            database_alias = router.db_for_write(User)
            with test_connections[database_alias].cursor() as cursor:
                cursor.execute("INSERT INTO example (value) VALUES ('forbidden')")
            return SQLiteResultViewModel(value="unreachable")

    try:
        with pytest.raises(OperationalError, match="attempt to write a readonly database"):
            ExampleCreateHandler().handle(object())
    finally:
        test_connections.close_all()
