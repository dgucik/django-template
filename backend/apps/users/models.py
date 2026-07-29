from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import BaseModel


class User(AbstractUser, BaseModel):
    """Application user model."""

    # Preserve the primary-key type from the applied initial user migration.
    id = models.BigAutoField(  # type: ignore[assignment]
        auto_created=True,
        primary_key=True,
        serialize=False,
        verbose_name="ID",
    )
