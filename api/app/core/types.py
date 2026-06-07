"""Cross-database compatible column types."""
from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB


class JsonB(JSON):
    """Use JSONB on PostgreSQL, plain JSON elsewhere (e.g. SQLite for tests)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class comparator_factory(JSON.Comparator):
        pass

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())
