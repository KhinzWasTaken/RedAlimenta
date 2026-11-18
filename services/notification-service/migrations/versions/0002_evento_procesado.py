"""Idempotencia del consumidor de eventos (S6-05): tabla evento_procesado.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from notificaciones.db import ROL_APP

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evento_procesado",
        sa.Column("id_evento", postgresql.UUID(as_uuid=True), primary_key=True,
                  comment="Identificador del evento recibido."),
        sa.Column("cola", sa.String(60), nullable=False, comment="Cola de RabbitMQ que lo entregó."),
        sa.Column("fecha_proceso", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
                  comment="Cuándo se procesó."),
        comment="Idempotencia del consumidor: un id_evento se procesa una sola vez.",
    )
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            GRANT SELECT, INSERT ON evento_procesado TO {ROL_APP};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("evento_procesado")
