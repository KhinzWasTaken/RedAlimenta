"""Memoria de avisos de vencimiento para que la tarea RF8 sea idempotente (S5-13).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

from cumplimiento.db import ROL_APP

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aviso_vencimiento",
        sa.Column("id_donacion", sa.BigInteger, primary_key=True, autoincrement=False,
                  comment="Donación avisada (catalog-geo-service; sin FK entre bases, D-06)."),
        sa.Column("fecha_aviso", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
                  comment="Cuándo se avisó."),
        comment="Donaciones ya avisadas como por vencer (idempotencia de la tarea RF8).",
    )
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            GRANT SELECT, INSERT ON aviso_vencimiento TO {ROL_APP};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("aviso_vencimiento")
