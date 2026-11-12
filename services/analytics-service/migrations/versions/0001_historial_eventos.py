"""Historial de eventos de analytics-service (S5-15): inmutable e idempotente.

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from analitica.db import ROL_APP

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "historial_evento",
        sa.Column("id_evento", postgresql.UUID(as_uuid=True), primary_key=True,
                  comment="Identificador del evento; repetido = mismo evento (idempotencia)."),
        sa.Column("tipo", sa.String(60), nullable=False, comment="Tipo: RESERVA_CREADA, ENTREGA_CONFIRMADA..."),
        sa.Column("version", sa.SmallInteger, nullable=False, comment="Versión del esquema del evento."),
        sa.Column("origen", sa.String(40), nullable=False, comment="Servicio que lo publicó."),
        sa.Column("fecha", sa.DateTime(timezone=True), nullable=False, comment="Cuándo ocurrió (según el origen)."),
        sa.Column("id_actor", sa.BigInteger, comment="Usuario que lo provocó; NULL = sistema."),
        sa.Column("entidad", sa.String(40), nullable=False, comment="Entidad afectada."),
        sa.Column("id_entidad", sa.BigInteger, nullable=False, comment="Identificador del registro afectado."),
        sa.Column("estado_anterior", sa.String(40), comment="Estado antes del cambio."),
        sa.Column("estado_nuevo", sa.String(40), comment="Estado después del cambio."),
        sa.Column("datos", postgresql.JSONB, nullable=False, comment="Contexto del evento (participantes, alimento...)."),
        sa.Column("fecha_recepcion", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
                  comment="Cuándo lo recibió analytics."),
        comment="Eventos de todos los servicios, tal como se publicaron. Solo inserción.",
    )
    op.create_index("ix_historial_entidad", "historial_evento", ["entidad", "id_entidad"])
    op.create_index("ix_historial_actor", "historial_evento", ["id_actor"])
    op.create_index("ix_historial_fecha", "historial_evento", ["fecha"])
    op.create_index("ix_historial_datos", "historial_evento", ["datos"], postgresql_using="gin")
    op.execute("""
        CREATE FUNCTION fn_historial_solo_insercion() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'historial_evento es de solo inserción' USING ERRCODE = 'insufficient_privilege';
        END $$;
        CREATE TRIGGER trg_historial_solo_insercion BEFORE UPDATE OR DELETE ON historial_evento
          FOR EACH ROW EXECUTE FUNCTION fn_historial_solo_insercion();
    """)
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            GRANT USAGE ON SCHEMA public TO {ROL_APP};
            GRANT SELECT, INSERT ON historial_evento TO {ROL_APP};
            REVOKE UPDATE, DELETE, TRUNCATE ON historial_evento FROM {ROL_APP};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("historial_evento")
    op.execute("DROP FUNCTION IF EXISTS fn_historial_solo_insercion()")
