"""Add Unilog reference data, delivery records, and evaluation runs.

Revision ID: 20260821_0007
Revises: 20260814_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260821_0007"
down_revision: str | None = "20260814_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("manufacturer_owned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_sources_manufacturer_owned", "sources", ["manufacturer_owned"])
    op.create_table(
        "reference_datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_type", sa.String(length=60), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("sheet_names", sa.JSON(), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("dataset_metadata", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reference_datasets_dataset_type", "reference_datasets", ["dataset_type"])
    op.create_index("ix_reference_datasets_content_sha256", "reference_datasets", ["content_sha256"])
    op.create_index("ix_reference_datasets_status", "reference_datasets", ["status"])
    op.create_index("ix_reference_datasets_is_active", "reference_datasets", ["is_active"])
    op.create_table(
        "reference_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_type", sa.String(length=60), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("lookup_key", sa.String(length=1000), nullable=True),
        sa.Column("normalized_key", sa.String(length=1000), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["reference_datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "sheet_name", "row_number", name="uq_reference_row"),
    )
    for name in ("dataset_id", "dataset_type", "sheet_name", "lookup_key", "normalized_key"):
        op.create_index(f"ix_reference_records_{name}", "reference_records", [name])
    op.create_table(
        "product_delivery_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("schema_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("descriptions", sa.JSON(), nullable=False),
        sa.Column("quality", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schema_dataset_id"], ["reference_datasets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index("ix_product_delivery_records_product_id", "product_delivery_records", ["product_id"])
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ground_truth_dataset_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("matched_items", sa.Integer(), nullable=False),
        sa.Column("field_accuracy", sa.Float(), nullable=False),
        sa.Column("character_limit_compliance", sa.Float(), nullable=False),
        sa.Column("lov_compliance", sa.Float(), nullable=False),
        sa.Column("manufacturer_accuracy", sa.Float(), nullable=False),
        sa.Column("taxonomy_accuracy", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("row_results", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ground_truth_dataset_id"], ["reference_datasets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_runs_ground_truth_dataset_id", "evaluation_runs", ["ground_truth_dataset_id"])
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])


def downgrade() -> None:
    op.drop_table("evaluation_runs")
    op.drop_table("product_delivery_records")
    op.drop_table("reference_records")
    op.drop_table("reference_datasets")
    op.drop_index("ix_sources_manufacturer_owned", table_name="sources")
    op.drop_column("sources", "manufacturer_owned")
