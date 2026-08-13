from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator

from pgvector.sqlalchemy import VECTOR


class EmbeddingVector(TypeDecorator):
    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int = 768):
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(VECTOR(self.dimensions))
        return dialect.type_descriptor(JSON())
