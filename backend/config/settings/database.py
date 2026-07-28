from django.core.exceptions import ImproperlyConfigured

from .env import (
    DATABASE_ENGINE,
    DATABASE_HOST,
    DATABASE_NAME,
    DATABASE_PASSWORD,
    DATABASE_PORT,
    DATABASE_READONLY_HOST,
    DATABASE_READONLY_NAME,
    DATABASE_READONLY_PASSWORD,
    DATABASE_READONLY_PORT,
    DATABASE_READONLY_USER,
    DATABASE_USER,
)

if DATABASE_ENGINE not in {
    "django.db.backends.postgresql",
    "django.db.backends.sqlite3",
}:
    raise ImproperlyConfigured("Only PostgreSQL and SQLite database backends are supported")

DATABASES: dict[str, dict[str, object]] = {
    "default": {
        "ENGINE": DATABASE_ENGINE,
        "NAME": DATABASE_NAME,
        "USER": DATABASE_USER,
        "PASSWORD": DATABASE_PASSWORD,
        "HOST": DATABASE_HOST,
        "PORT": DATABASE_PORT,
    }
}

if DATABASE_ENGINE == "django.db.backends.postgresql":
    if not DATABASE_READONLY_USER or DATABASE_READONLY_USER == DATABASE_USER:
        raise ImproperlyConfigured(
            "DJANGO_DB_READONLY_USER must identify a dedicated read-only PostgreSQL role"
        )

    DATABASES["default_readonly"] = {
        "ENGINE": DATABASE_ENGINE,
        "NAME": DATABASE_READONLY_NAME,
        "USER": DATABASE_READONLY_USER,
        "PASSWORD": DATABASE_READONLY_PASSWORD,
        "HOST": DATABASE_READONLY_HOST,
        "PORT": DATABASE_READONLY_PORT,
        "OPTIONS": {"options": "-c default_transaction_read_only=on"},
        "TEST": {"MIRROR": "default"},
    }
else:
    DATABASES["default_readonly"] = {
        "ENGINE": DATABASE_ENGINE,
        "NAME": f"file:{DATABASE_NAME}?mode=ro",
        "OPTIONS": {"uri": True},
        "TEST": {"MIRROR": "default"},
    }

DATABASE_ROUTERS = ["core.handlers._QueryDatabaseRouter"]
