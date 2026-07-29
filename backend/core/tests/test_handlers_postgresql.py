from dataclasses import dataclass

import pytest
from django.conf import settings
from django.db import DatabaseError, connection, connections, router

from apps.users.models import User
from core.handlers import QueryHandler

pytestmark = [
    pytest.mark.postgresql,
    pytest.mark.skipif(
        connection.vendor != "postgresql",
        reason="PostgreSQL permission tests require PostgreSQL",
    ),
]


@dataclass(frozen=True, slots=True)
class PostgreSQLResultDto:
    value: str


@dataclass(frozen=True, slots=True)
class PostgreSQLPermissionDto:
    allowed: bool


@pytest.mark.django_db(databases=["default", "default_readonly"], transaction=True)
def test_query_handler_connects_as_the_dedicated_read_only_role() -> None:
    """Given PostgreSQL. When a query connects. Then it uses the dedicated read-only role."""

    class CurrentUserGetHandler(QueryHandler[object, PostgreSQLResultDto]):
        def handle(self, query: object) -> PostgreSQLResultDto:
            database_alias = router.db_for_read(User)
            with connections[database_alias].cursor() as cursor:
                cursor.execute("SELECT current_user")
                row = cursor.fetchone()
            assert row is not None
            return PostgreSQLResultDto(value=row[0])

    assert (
        CurrentUserGetHandler().handle(object()).value
        == settings.DATABASES["default_readonly"]["USER"]
    )


@pytest.mark.django_db(databases=["default", "default_readonly"], transaction=True)
def test_query_handler_role_cannot_create_temporary_tables() -> None:
    """Given the read-only role. When privileges are checked. Then temporary tables are denied."""

    class TemporaryPermissionGetHandler(
        QueryHandler[object, PostgreSQLPermissionDto],
    ):
        def handle(self, query: object) -> PostgreSQLPermissionDto:
            database_alias = router.db_for_read(User)
            with connections[database_alias].cursor() as cursor:
                cursor.execute(
                    "SELECT has_database_privilege(current_user, current_database(), 'TEMPORARY')"
                )
                row = cursor.fetchone()
            assert row is not None
            return PostgreSQLPermissionDto(allowed=row[0])

    assert not TemporaryPermissionGetHandler().handle(object()).allowed


@pytest.mark.django_db(databases=["default", "default_readonly"], transaction=True)
def test_query_handler_cannot_write_through_the_orm() -> None:
    """Given a query handler. When the ORM attempts a write. Then PostgreSQL rejects it."""

    class UserCreateHandler(QueryHandler[object, PostgreSQLResultDto]):
        def handle(self, query: object) -> PostgreSQLResultDto:
            User.objects.create(username="forbidden-query-write")
            return PostgreSQLResultDto(value="unreachable")

    with pytest.raises(DatabaseError, match=r"permission denied|read-only"):
        UserCreateHandler().handle(object())

    assert not User.objects.filter(username="forbidden-query-write").exists()


@pytest.mark.django_db(databases=["default", "default_readonly"], transaction=True)
def test_query_handler_allows_a_common_table_expression() -> None:
    """Given a read-only connection. When a CTE is selected. Then PostgreSQL returns its result."""

    class CommonTableExpressionGetHandler(
        QueryHandler[object, PostgreSQLResultDto],
    ):
        def handle(self, query: object) -> PostgreSQLResultDto:
            database_alias = router.db_for_read(User)
            with connections[database_alias].cursor() as cursor:
                cursor.execute(
                    "WITH result(value) AS (VALUES ('allowed')) SELECT value FROM result"
                )
                row = cursor.fetchone()
            assert row is not None
            return PostgreSQLResultDto(value=row[0])

    assert CommonTableExpressionGetHandler().handle(object()).value == "allowed"


@pytest.mark.django_db(databases=["default", "default_readonly"], transaction=True)
def test_query_handler_cannot_execute_an_ungranted_security_definer_function() -> None:
    """Given an ungranted function. When a query invokes it. Then PostgreSQL rejects execution."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE FUNCTION public.query_test_dangerous_function()
            RETURNS integer
            LANGUAGE plpgsql
            SECURITY DEFINER
            AS $$
            BEGIN
                UPDATE users_user SET is_active = FALSE;
                RETURN 1;
            END;
            $$
            """
        )

    class DangerousFunctionGetHandler(
        QueryHandler[object, PostgreSQLResultDto],
    ):
        def handle(self, query: object) -> PostgreSQLResultDto:
            database_alias = router.db_for_read(User)
            with connections[database_alias].cursor() as cursor:
                cursor.execute("SELECT public.query_test_dangerous_function()")
            return PostgreSQLResultDto(value="unreachable")

    try:
        with pytest.raises(DatabaseError, match="permission denied for function"):
            DangerousFunctionGetHandler().handle(object())
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP FUNCTION public.query_test_dangerous_function()")
