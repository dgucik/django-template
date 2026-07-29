from abc import ABC


class Command(ABC):
    """Represent serialization-safe input for a write use case."""


class Query(ABC):
    """Represent serialization-safe input for a read use case."""


class Dto(ABC):
    """Represent serialization-safe output from a read use case."""
