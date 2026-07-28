import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")


def get_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable, failing early for invalid values."""
    value = os.getenv(name)
    if value is None:
        return default

    normalized_value = value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"{name} must be a boolean value.")


def get_list(name: str, default: tuple[str, ...] = ()) -> list[str]:
    """Read a comma-separated environment variable as a list."""
    value = os.getenv(name)
    if value is None:
        return list(default)

    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
DEBUG = get_bool("DJANGO_DEBUG")
ALLOWED_HOSTS = get_list("DJANGO_ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = get_list(
    "CORS_ALLOWED_ORIGINS",
)

DATABASE_ENGINE = os.getenv("DJANGO_DB_ENGINE", "django.db.backends.sqlite3")
DATABASE_NAME = os.getenv("DJANGO_DB_NAME", str(BASE_DIR / "db.sqlite3"))
DATABASE_USER = os.getenv("DJANGO_DB_USER", "")
DATABASE_PASSWORD = os.getenv("DJANGO_DB_PASSWORD", "")
DATABASE_HOST = os.getenv("DJANGO_DB_HOST", "")
DATABASE_PORT = os.getenv("DJANGO_DB_PORT", "")
DATABASE_READONLY_NAME = os.getenv("DJANGO_DB_READONLY_NAME", DATABASE_NAME)
DATABASE_READONLY_USER = os.getenv("DJANGO_DB_READONLY_USER", "")
DATABASE_READONLY_PASSWORD = os.getenv("DJANGO_DB_READONLY_PASSWORD", "")
DATABASE_READONLY_HOST = os.getenv("DJANGO_DB_READONLY_HOST", DATABASE_HOST)
DATABASE_READONLY_PORT = os.getenv("DJANGO_DB_READONLY_PORT", DATABASE_PORT)
