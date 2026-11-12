"""Esquema inicial de fulfillment-service: reserva, entrega y confirmación (S4-05).

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from cumplimiento.db import ROL_APP

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

estado_reserva = postgresql.ENUM("PENDIENTE", "CONFIRMADA", "EXPIRADA", "COMPLETADA", "CANCELADA",
                                 name="estado_reserva", create_type=False)
estado_entrega = postgresql.ENUM("PROGRAMADA", "COMPLETADA", "CON_INCIDENCIA", "CANCELADA",
                                 name="estado_entrega", create_type=False)
estado_confirmacion = postgresql.ENUM("CONFIRMADA", "CON_INCIDENCIA", name="estado_confirmacion", create_type=False)
TS = sa.DateTime(timezone=True)
TIPOS = (estado_reserva, estado_entrega, estado_confirmacion)


def upgrade() -> None:
    for tipo in TIPOS:
        tipo.create(op.get_bind())

    op.create_table(
        "reserva",
        sa.Column("id_reserva", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("id_donacion", sa.BigInteger, nullable=False,
                  comment="Donación reservada (catalog-geo-service; sin FK entre bases, D-06)."),
        sa.Column("id_receptor", sa.BigInteger, nullable=False,
                  comment="Usuario receptor (identity-service; sin FK entre bases, D-06)."),
        sa.Column("fecha_reserva", TS, nullable=False, server_default=sa.func.now(), comment="Cuándo se reservó."),
        sa.Column("fecha_expiracion", TS, nullable=False,
                  comment="Plazo para que el donante confirme (D-09: 2 horas por defecto)."),
        sa.Column("estado_reserva", estado_reserva, nullable=False, server_default="PENDIENTE",
                  comment="PENDIENTE, CONFIRMADA, EXPIRADA, COMPLETADA o CANCELADA."),
        sa.CheckConstraint("fecha_expiracion > fecha_reserva", name=op.f("ck_reserva_expira_despues_de_reservar")),
        comment="Solicitudes de reserva; cubren la donación completa (D-05).",
    )
    op.create_index("ix_reserva_id_donacion", "reserva", ["id_donacion"])
    op.create_index("ix_reserva_id_receptor", "reserva", ["id_receptor"])
    op.create_index("ux_reserva_activa", "reserva", ["id_donacion"], unique=True,
                    postgresql_where=sa.text("estado_reserva IN ('PENDIENTE', 'CONFIRMADA')"))
    op.create_index("ix_reserva_pendiente_expiracion", "reserva", ["fecha_expiracion"],
                    postgresql_where=sa.text("estado_reserva = 'PENDIENTE'"))

    op.create_table(
        "entrega",
        sa.Column("id_entrega", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("id_reserva", sa.BigInteger, sa.ForeignKey("reserva.id_reserva", name="fk_entrega_id_reserva_reserva"),
                  nullable=False, comment="Reserva que se entrega (una entrega por reserva)."),
        sa.Column("fecha_programada", TS, comment="Cuándo se acordó entregar."),
        sa.Column("fecha_entrega", TS, comment="Cuándo se completó la entrega."),
        sa.Column("estado_entrega", estado_entrega, nullable=False, server_default="PROGRAMADA",
                  comment="PROGRAMADA, COMPLETADA, CON_INCIDENCIA o CANCELADA."),
        sa.Column("observaciones", sa.Text, comment="Notas o descripción de la incidencia."),
        sa.UniqueConstraint("id_reserva", name="uq_entrega_id_reserva"),
        sa.CheckConstraint("estado_entrega <> 'COMPLETADA' OR fecha_entrega IS NOT NULL",
                           name=op.f("ck_entrega_completada_fechada")),
        comment="Entrega de una reserva confirmada; una por reserva.",
    )

    op.create_table(
        "confirmacion_entrega",
        sa.Column("id_confirmacion", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("id_entrega", sa.BigInteger,
                  sa.ForeignKey("entrega.id_entrega", name="fk_confirmacion_entrega_id_entrega_entrega"),
                  nullable=False, comment="Entrega que se confirma."),
        sa.Column("id_usuario", sa.BigInteger, nullable=False,
                  comment="Donante o receptor que confirma (identity-service; sin FK entre bases, D-06)."),
        sa.Column("fecha_confirmacion", TS, nullable=False, server_default=sa.func.now(), comment="Cuándo confirmó."),
        sa.Column("estado_confirmacion", estado_confirmacion, nullable=False, comment="CONFIRMADA o CON_INCIDENCIA."),
        sa.Column("observaciones", sa.Text, comment="Comentario o detalle de la incidencia."),
        sa.UniqueConstraint("id_entrega", "id_usuario", name="uq_confirmacion_entrega_id_entrega_id_usuario"),
        comment="Confirmación bilateral: la donación queda ENTREGADA con la del donante y la del receptor.",
    )
    op.create_index("ix_confirmacion_entrega_id_entrega", "confirmacion_entrega", ["id_entrega"])

    op.execute("""
        CREATE FUNCTION fn_reserva_validar() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.estado_reserva IS DISTINCT FROM OLD.estado_reserva AND NOT (
               (OLD.estado_reserva = 'PENDIENTE' AND NEW.estado_reserva IN ('CONFIRMADA', 'EXPIRADA', 'CANCELADA'))
            OR (OLD.estado_reserva = 'CONFIRMADA' AND NEW.estado_reserva IN ('COMPLETADA', 'CANCELADA'))
          ) THEN
            RAISE EXCEPTION 'Transición de reserva no permitida: % → %', OLD.estado_reserva, NEW.estado_reserva
              USING ERRCODE = 'check_violation';
          END IF;
          IF (NEW.id_donacion, NEW.id_receptor, NEW.fecha_reserva) IS DISTINCT FROM
             (OLD.id_donacion, OLD.id_receptor, OLD.fecha_reserva) THEN
            RAISE EXCEPTION 'La donación, el receptor y la fecha de una reserva no cambian'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_reserva_validar BEFORE UPDATE ON reserva
          FOR EACH ROW EXECUTE FUNCTION fn_reserva_validar();

        CREATE FUNCTION fn_entrega_validar() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'INSERT' AND NOT EXISTS (
              SELECT 1 FROM reserva WHERE id_reserva = NEW.id_reserva
              AND estado_reserva IN ('CONFIRMADA', 'COMPLETADA')) THEN
            RAISE EXCEPTION 'Solo se programa la entrega de una reserva CONFIRMADA'
              USING ERRCODE = 'check_violation';
          END IF;
          IF TG_OP = 'UPDATE' AND NEW.estado_entrega IS DISTINCT FROM OLD.estado_entrega AND NOT (
               (OLD.estado_entrega = 'PROGRAMADA' AND NEW.estado_entrega IN ('COMPLETADA', 'CON_INCIDENCIA', 'CANCELADA'))
            OR (OLD.estado_entrega = 'CON_INCIDENCIA' AND NEW.estado_entrega = 'CANCELADA')
          ) THEN
            RAISE EXCEPTION 'Transición de entrega no permitida: % → %', OLD.estado_entrega, NEW.estado_entrega
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_entrega_validar BEFORE INSERT OR UPDATE ON entrega
          FOR EACH ROW EXECUTE FUNCTION fn_entrega_validar();
    """)

    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            GRANT USAGE ON SCHEMA public TO {ROL_APP};
            GRANT SELECT, INSERT, UPDATE ON reserva, entrega TO {ROL_APP};
            GRANT SELECT, INSERT ON confirmacion_entrega TO {ROL_APP};
            GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {ROL_APP};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    for tabla in ("confirmacion_entrega", "entrega", "reserva"):
        op.drop_table(tabla)
    op.execute("DROP FUNCTION IF EXISTS fn_entrega_validar()")
    op.execute("DROP FUNCTION IF EXISTS fn_reserva_validar()")
    for tipo in TIPOS:
        tipo.drop(op.get_bind())
