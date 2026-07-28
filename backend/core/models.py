import uuid

from django.db import models


class BaseModel(models.Model):
    """Provide identity and audit timestamps for persisted models."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Keep the base model abstract."""

        abstract = True
