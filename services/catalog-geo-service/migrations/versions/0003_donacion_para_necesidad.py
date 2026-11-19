"""Solicitudes de alimentos: un donante puede ofrecer una donación para una necesidad abierta (D-11).

La donación guarda a qué necesidad responde. Mientras esa necesidad siga ABIERTA, solo su receptor puede
reservarla; si la necesidad se cierra o se cancela, la donación queda disponible para todos.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("donacion", sa.Column(
        "id_necesidad", sa.BigInteger,
        sa.ForeignKey("necesidad_alimentaria.id_necesidad", name="fk_donacion_id_necesidad_necesidad_alimentaria"),
        nullable=True,
        comment="Necesidad a la que responde (D-11); NULL si es una donación abierta a todos."))
    op.create_index("ix_donacion_id_necesidad", "donacion", ["id_necesidad"])


def downgrade() -> None:
    op.drop_index("ix_donacion_id_necesidad", table_name="donacion")
    op.drop_column("donacion", "id_necesidad")
