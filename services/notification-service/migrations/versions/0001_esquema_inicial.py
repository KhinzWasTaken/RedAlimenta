"""Esquema inicial de notification-service: notificación (S4-06).

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from notificaciones.db import ROL_APP

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

estado_notificacion = postgresql.ENUM("NO_LEIDA", "LEIDA", "ARCHIVADA", name="estado_notificacion",
                                      create_type=False)


def upgrade() -> None:
    estado_notificacion.create(op.get_bind())
    op.create_table(
        "notificacion",
        sa.Column("id_notificacion", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("id_usuario", sa.BigInteger, nullable=False,
                  comment="Destinatario (identity-service; sin FK entre bases, D-06). Obligatorio."),
        sa.Column("tipo_notificacion", sa.String(60), nullable=False,
                  comment="Evento que la originó: RESERVA_CREADA, ENTREGA_CONFIRMADA..."),
        sa.Column("mensaje", sa.Text, nullable=False, comment="Texto para el usuario."),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
                  comment="Cuándo se generó."),
        sa.Column("fecha_lectura", sa.DateTime(timezone=True), comment="Cuándo la leyó el usuario."),
        sa.Column("estado_notificacion", estado_notificacion, nullable=False, server_default="NO_LEIDA",
                  comment="NO_LEIDA, LEIDA o ARCHIVADA."),
        sa.CheckConstraint("estado_notificacion <> 'LEIDA' OR fecha_lectura IS NOT NULL",
                           name=op.f("ck_notificacion_leida_fechada")),
        sa.CheckConstraint("length(trim(mensaje)) > 0", name=op.f("ck_notificacion_mensaje_no_vacio")),
        comment="Avisos in-app generados por los eventos de los demás servicios.",
    )
    op.create_index("ix_notificacion_usuario_estado", "notificacion", ["id_usuario", "estado_notificacion"])

    op.execute("""
        CREATE FUNCTION fn_notificacion_validar() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.estado_notificacion IS DISTINCT FROM OLD.estado_notificacion AND NOT (
               (OLD.estado_notificacion = 'NO_LEIDA' AND NEW.estado_notificacion IN ('LEIDA', 'ARCHIVADA'))
            OR (OLD.estado_notificacion = 'LEIDA' AND NEW.estado_notificacion = 'ARCHIVADA')
          ) THEN
            RAISE EXCEPTION 'Transición de notificación no permitida: % → %',
              OLD.estado_notificacion, NEW.estado_notificacion USING ERRCODE = 'check_violation';
          END IF;
          IF (NEW.id_usuario, NEW.tipo_notificacion, NEW.mensaje, NEW.fecha_creacion) IS DISTINCT FROM
             (OLD.id_usuario, OLD.tipo_notificacion, OLD.mensaje, OLD.fecha_creacion) THEN
            RAISE EXCEPTION 'El contenido de una notificación no cambia' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_notificacion_validar BEFORE UPDATE ON notificacion
          FOR EACH ROW EXECUTE FUNCTION fn_notificacion_validar();
    """)

    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            GRANT USAGE ON SCHEMA public TO {ROL_APP};
            GRANT SELECT, INSERT ON notificacion TO {ROL_APP};
            GRANT UPDATE (estado_notificacion, fecha_lectura) ON notificacion TO {ROL_APP};
            GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {ROL_APP};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("notificacion")
    op.execute("DROP FUNCTION IF EXISTS fn_notificacion_validar()")
    estado_notificacion.drop(op.get_bind())
