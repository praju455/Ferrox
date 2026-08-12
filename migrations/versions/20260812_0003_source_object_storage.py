"""Add durable source object storage metadata.

Revision ID: 20260812_0003
Revises: 20260812_0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_0003"
down_revision: str | None = "20260812_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(sa.Column("storage_backend", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("storage_key", sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column("content_type", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("content_length", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("content_sha256", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint("uq_sources_storage_key", ["storage_key"])


def downgrade() -> None:
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_constraint("uq_sources_storage_key", type_="unique")
        batch_op.drop_column("content_sha256")
        batch_op.drop_column("content_length")
        batch_op.drop_column("content_type")
        batch_op.drop_column("storage_key")
        batch_op.drop_column("storage_backend")
