"""initial schema

Revision ID: 20260812_0001
Revises:
Create Date: 2026-08-12
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260812_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


source_type = sa.Enum("pdf", "url", "text", name="sourcetype")
field_status = sa.Enum("extracted", "conflict_resolved", "validated", "needs_review", "enriched", name="fieldstatus")
review_status = sa.Enum("open", "resolved", "dismissed", name="reviewstatus")


def upgrade() -> None:
    source_type.create(op.get_bind(), checkfirst=True)
    field_status.create(op.get_bind(), checkfirst=True)
    review_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("dynamic_schema", sa.JSON(), nullable=True),
        sa.Column("completeness_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_name"), "products", ["name"], unique=False)
    op.create_index(op.f("ix_products_category"), "products", ["category"], unique=False)

    op.create_table(
        "batch_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("processed_items", sa.Integer(), nullable=False),
        sa.Column("failed_items", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_jobs_status"), "batch_jobs", ["status"], unique=False)

    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("source_identifier", sa.String(length=500), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("extracted_metadata", sa.JSON(), nullable=True),
        sa.Column("authority_rank", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sources_product_id"), "sources", ["product_id"], unique=False)
    op.create_index(op.f("ix_sources_source_type"), "sources", ["source_type"], unique=False)

    op.create_table(
        "extracted_fields",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", field_status, nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("alternatives", sa.JSON(), nullable=True),
        sa.Column("validation", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "field_name", name="uq_product_field"),
    )
    op.create_index(op.f("ix_extracted_fields_product_id"), "extracted_fields", ["product_id"], unique=False)
    op.create_index(op.f("ix_extracted_fields_source_id"), "extracted_fields", ["source_id"], unique=False)
    op.create_index(op.f("ix_extracted_fields_field_name"), "extracted_fields", ["field_name"], unique=False)

    op.create_table(
        "review_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("field_name", sa.String(length=120), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", review_status, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_items_product_id"), "review_items", ["product_id"], unique=False)

    op.create_table(
        "batch_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["batch_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_items_batch_id"), "batch_items", ["batch_id"], unique=False)
    op.create_index(op.f("ix_batch_items_product_id"), "batch_items", ["product_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_batch_items_product_id"), table_name="batch_items")
    op.drop_index(op.f("ix_batch_items_batch_id"), table_name="batch_items")
    op.drop_table("batch_items")
    op.drop_index(op.f("ix_review_items_product_id"), table_name="review_items")
    op.drop_table("review_items")
    op.drop_index(op.f("ix_extracted_fields_field_name"), table_name="extracted_fields")
    op.drop_index(op.f("ix_extracted_fields_source_id"), table_name="extracted_fields")
    op.drop_index(op.f("ix_extracted_fields_product_id"), table_name="extracted_fields")
    op.drop_table("extracted_fields")
    op.drop_index(op.f("ix_sources_source_type"), table_name="sources")
    op.drop_index(op.f("ix_sources_product_id"), table_name="sources")
    op.drop_table("sources")
    op.drop_index(op.f("ix_batch_jobs_status"), table_name="batch_jobs")
    op.drop_table("batch_jobs")
    op.drop_index(op.f("ix_products_category"), table_name="products")
    op.drop_index(op.f("ix_products_name"), table_name="products")
    op.drop_table("products")
    review_status.drop(op.get_bind(), checkfirst=True)
    field_status.drop(op.get_bind(), checkfirst=True)
    source_type.drop(op.get_bind(), checkfirst=True)
