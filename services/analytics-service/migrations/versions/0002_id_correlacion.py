"""Identificador de correlación en el historial (S6-09).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("historial_evento", sa.Column(
        "id_correlacion", sa.String(64),
        comment="Operación que lo originó (S6-09); une eventos de varios servicios."))
    op.create_index("ix_historial_evento_id_correlacion", "historial_evento", ["id_correlacion"])


def downgrade() -> None:
    op.drop_index("ix_historial_evento_id_correlacion", "historial_evento")
    op.drop_column("historial_evento", "id_correlacion")
