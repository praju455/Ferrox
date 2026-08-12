"""Add citation-backed enrichment and LLM run observability.

Revision ID: 20260812_0004
Revises: 20260812_0003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_0004"
down_revision: str | None = "20260812_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("task", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("product_id", "provider", "task", "status", "created_at"):
        op.create_index(f"ix_llm_runs_{column}", "llm_runs", [column])
    op.create_table(
        "citations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("extracted_field_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("cited_text", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["extracted_field_id"], ["extracted_fields.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_citations_product_id", "citations", ["product_id"])
    op.create_index("ix_citations_extracted_field_id", "citations", ["extracted_field_id"])


def downgrade() -> None:
    op.drop_table("citations")
    op.drop_table("llm_runs")
