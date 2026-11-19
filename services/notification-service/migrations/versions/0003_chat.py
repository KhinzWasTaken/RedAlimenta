"""Chat entre donante y receptor de una donación (D-12): conversacion y mensaje.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from notificaciones.db import ROL_APP

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

estado_conversacion = postgresql.ENUM("ABIERTA", "CERRADA", name="estado_conversacion", create_type=False)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    estado_conversacion.create(op.get_bind())
    op.create_table(
        "conversacion",
        sa.Column("id_conversacion", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("id_donacion", sa.BigInteger, nullable=False,
                  comment="Donación de la que se habla (catalog-geo; sin FK entre bases, D-06)."),
        sa.Column("id_donante", sa.BigInteger, nullable=False, comment="Donante (identity-service)."),
        sa.Column("id_receptor", sa.BigInteger, nullable=False, comment="Receptor (identity-service)."),
        sa.Column("nombre_alimento", sa.String(120), nullable=False, comment="Alimento, para mostrar la conversación."),
        sa.Column("origen", sa.String(20), nullable=False,
                  comment="RESERVA (el receptor la reservó) u OFERTA (el donante la ofreció a su solicitud)."),
        sa.Column("estado_conversacion", estado_conversacion, nullable=False, server_default="ABIERTA",
                  comment="ABIERTA (se puede escribir) o CERRADA (solo lectura)."),
        sa.Column("fecha_creacion", TS, nullable=False, server_default=sa.func.now(), comment="Cuándo se abrió."),
        sa.Column("fecha_cierre", TS, comment="Cuándo se cerró."),
        sa.Column("ultimo_leido_donante", sa.BigInteger, nullable=False, server_default="0",
                  comment="Último id_mensaje que leyó el donante (para contar no leídos)."),
        sa.Column("ultimo_leido_receptor", sa.BigInteger, nullable=False, server_default="0",
                  comment="Último id_mensaje que leyó el receptor."),
        sa.UniqueConstraint("id_donacion", "id_receptor", name="uq_conversacion_id_donacion_id_receptor"),
        sa.CheckConstraint("id_donante <> id_receptor", name=op.f("ck_conversacion_participantes_distintos")),
        sa.CheckConstraint("(estado_conversacion = 'CERRADA') = (fecha_cierre IS NOT NULL)",
                           name=op.f("ck_conversacion_cierre_fechado")),
        comment="Chat donante–receptor de una donación. Se abre cuando el receptor la reserva o el donante "
                "la ofrece para su solicitud; se cierra cuando la reserva o la donación terminan.",
    )
    op.create_index("ix_conversacion_donante", "conversacion", ["id_donante"])
    op.create_index("ix_conversacion_receptor", "conversacion", ["id_receptor"])

    op.create_table(
        "mensaje",
        sa.Column("id_mensaje", sa.BigInteger, primary_key=True, comment="Identificador (orden de envío)."),
        sa.Column("id_conversacion", sa.BigInteger,
                  sa.ForeignKey("conversacion.id_conversacion", name="fk_mensaje_id_conversacion_conversacion"),
                  nullable=False, comment="Conversación a la que pertenece."),
        sa.Column("id_autor", sa.BigInteger, nullable=False, comment="Quién lo escribió: el donante o el receptor."),
        sa.Column("texto", sa.Text, nullable=False, comment="Contenido, de 1 a 1.000 caracteres."),
        sa.Column("fecha_envio", TS, nullable=False, server_default=sa.func.now(), comment="Cuándo se envió."),
        sa.CheckConstraint("length(trim(texto)) BETWEEN 1 AND 1000", name=op.f("ck_mensaje_texto_valido")),
        comment="Mensajes de cada conversación; no se modifican ni se borran.",
    )
    op.create_index("ix_mensaje_conversacion", "mensaje", ["id_conversacion", "id_mensaje"])

    # Solo escriben los participantes de una conversación ABIERTA; lo escrito no cambia (D-12)
    op.execute("""
        CREATE FUNCTION fn_mensaje_validar() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE c conversacion%ROWTYPE;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'Los mensajes no se modifican ni se borran' USING ERRCODE = 'check_violation';
          END IF;
          SELECT * INTO c FROM conversacion WHERE id_conversacion = NEW.id_conversacion;
          IF c.estado_conversacion <> 'ABIERTA' THEN
            RAISE EXCEPTION 'La conversación está cerrada' USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.id_autor NOT IN (c.id_donante, c.id_receptor) THEN
            RAISE EXCEPTION 'Solo el donante y el receptor escriben en la conversación'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_mensaje_validar BEFORE INSERT OR UPDATE OR DELETE ON mensaje
          FOR EACH ROW EXECUTE FUNCTION fn_mensaje_validar();
    """)
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            GRANT SELECT, INSERT ON conversacion, mensaje TO {ROL_APP};
            GRANT UPDATE (estado_conversacion, fecha_cierre, ultimo_leido_donante, ultimo_leido_receptor)
              ON conversacion TO {ROL_APP};
            GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {ROL_APP};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("mensaje")
    op.execute("DROP FUNCTION IF EXISTS fn_mensaje_validar()")
    op.drop_table("conversacion")
    estado_conversacion.drop(op.get_bind())
