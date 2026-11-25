"""Initial canonical document/chunk schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("document_id", sa.String(36), primary_key=True),
        sa.Column("source_uri", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "document_versions",
        sa.Column("version_id", sa.String(64), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.document_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("parser_name", sa.Text, nullable=False, server_default="unknown"),
        sa.Column("parser_version", sa.Text, nullable=False, server_default="unknown"),
        sa.Column("extraction_status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("parsed_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("document_id", "content_sha256", name="uq_document_content"),
    )
    op.create_index("ix_document_versions_document", "document_versions", ["document_id"])
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.String(36), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(64),
            sa.ForeignKey("document_versions.version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.document_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("chunk_type", sa.Text, nullable=False, server_default="paragraph"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("page_start", sa.Integer),
        sa.Column("page_end", sa.Integer),
        sa.Column("section", sa.Text),
        sa.Column("subsection", sa.Text),
        sa.Column("parent_chunk_id", sa.String(36)),
        sa.Column("previous_chunk_id", sa.String(36)),
        sa.Column("next_chunk_id", sa.String(36)),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.UniqueConstraint("version_id", "ordinal", name="uq_version_ordinal"),
    )
    for column in ("version_id", "document_id", "page_start", "parent_chunk_id"):
        op.create_index(f"ix_chunks_{column}", "chunks", [column])
    op.create_table(
        "chunk_elements",
        sa.Column(
            "chunk_id",
            sa.String(36),
            sa.ForeignKey("chunks.chunk_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("element_id", sa.String(36), primary_key=True),
        sa.Column("reading_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source_location", sa.Text, nullable=False, server_default=""),
        sa.Column("extraction_metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("extraction_warnings", sa.JSON, nullable=False, server_default="[]"),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.document_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.String(64),
            sa.ForeignKey("document_versions.version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "index_sync_state",
        sa.Column(
            "version_id",
            sa.String(64),
            sa.ForeignKey("document_versions.version_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("index_name", sa.String(32), primary_key=True),
        sa.Column("scope", sa.Text, primary_key=True, server_default=""),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("last_synced_at", sa.DateTime),
        sa.Column("failure_reason", sa.Text),
    )
    op.create_table(
        "citation_records",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column(
            "chunk_id",
            sa.String(36),
            sa.ForeignKey("chunks.chunk_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.String(64),
            sa.ForeignKey("document_versions.version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.document_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("page_start", sa.Integer),
        sa.Column("page_end", sa.Integer),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("section", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("citation_records")
    op.drop_table("index_sync_state")
    op.drop_table("ingestion_jobs")
    op.drop_table("chunk_elements")
    op.drop_table("chunks")
    op.drop_table("document_versions")
    op.drop_table("documents")
