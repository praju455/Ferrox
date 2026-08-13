"""Add pgvector-backed source chunks for retrieval.

Revision ID: 20260814_0006
Revises: 20260812_0005
"""

from collections.abc import Sequence

from alembic import op
from pgvector.sqlalchemy import VECTOR
import sqlalchemy as sa


revision: str = "20260814_0006"
down_revision: str | None = "20260812_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    embedding_type = VECTOR(768) if is_postgres else sa.JSON()
    op.create_table(
        "source_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=False),
        sa.Column("embedding", embedding_type, nullable=False),
        sa.Column("chunk_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "chunk_index", name="uq_source_chunk_index"),
    )
    op.create_index("ix_source_chunks_source_id", "source_chunks", ["source_id"])
    op.create_index("ix_source_chunks_product_id", "source_chunks", ["product_id"])
    op.create_index("ix_source_chunks_content_sha256", "source_chunks", ["content_sha256"])
    if is_postgres:
        op.create_index(
            "ix_source_chunks_embedding_hnsw",
            "source_chunks",
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )


def downgrade() -> None:
    op.drop_table("source_chunks")
