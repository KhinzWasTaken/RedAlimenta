"""Esquema inicial de identity-service: rol, usuario, verificación y auditoría (S4-03).

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from identidad.db import ROL_APP

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

estado_cuenta = postgresql.ENUM("ACTIVA", "DESACTIVADA", name="estado_cuenta", create_type=False)
estado_verificacion = postgresql.ENUM("PENDIENTE", "APROBADA", "RECHAZADA", name="estado_verificacion",
                                      create_type=False)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    estado_cuenta.create(op.get_bind())
    estado_verificacion.create(op.get_bind())

    rol = op.create_table(
        "rol",
        sa.Column("id_rol", sa.SmallInteger, primary_key=True, comment="Identificador del rol."),
        sa.Column("nombre_rol", sa.String(30), nullable=False, comment="Nombre único del rol."),
        sa.Column("descripcion", sa.String(200), comment="Qué puede hacer el rol."),
        sa.UniqueConstraint("nombre_rol", name="uq_rol_nombre_rol"),
        comment="Tipos de usuario y sus permisos: DONANTE, RECEPTOR, ADMINISTRADOR.",
    )
    op.bulk_insert(rol, [
        {"id_rol": 1, "nombre_rol": "DONANTE", "descripcion": "Publica y gestiona donaciones"},
        {"id_rol": 2, "nombre_rol": "RECEPTOR", "descripcion": "Publica necesidades y reserva donaciones"},
        {"id_rol": 3, "nombre_rol": "ADMINISTRADOR", "descripcion": "Verifica cuentas y supervisa la plataforma"},
    ])

    op.create_table(
        "usuario",
        sa.Column("id_usuario", sa.BigInteger, primary_key=True, comment="Identificador del usuario."),
        sa.Column("id_rol", sa.SmallInteger, sa.ForeignKey("rol.id_rol", name="fk_usuario_id_rol_rol"),
                  nullable=False, comment="Rol del usuario."),
        sa.Column("nombre", sa.String(120), nullable=False, comment="Nombre de la persona u organización."),
        sa.Column("correo_electronico", sa.String(254), nullable=False,
                  comment="Correo de inicio de sesión; único sin distinguir mayúsculas."),
        sa.Column("contrasena_hash", sa.String(255), nullable=False,
                  comment="Hash PBKDF2-SHA256 de la contraseña; nunca la contraseña en claro."),
        sa.Column("telefono", sa.String(30), comment="Teléfono de contacto (dato personal)."),
        sa.Column("estado_cuenta", estado_cuenta, nullable=False, server_default="ACTIVA",
                  comment="ACTIVA o DESACTIVADA; desactivar no borra la fila."),
        sa.Column("fecha_registro", TS, nullable=False, server_default=sa.func.now(),
                  comment="Fecha de creación de la cuenta."),
        sa.CheckConstraint("correo_electronico LIKE '%_@_%'", name="ck_usuario_correo_valido"),
        comment="Personas y organizaciones registradas (donantes, receptores, administradores).",
    )
    op.create_index("ix_usuario_id_rol", "usuario", ["id_rol"])
    op.create_index("ux_usuario_correo", "usuario", [sa.text("lower(correo_electronico)")], unique=True)

    op.create_table(
        "verificacion_usuario",
        sa.Column("id_verificacion", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("id_usuario", sa.BigInteger,
                  sa.ForeignKey("usuario.id_usuario", name="fk_verificacion_usuario_id_usuario_usuario"),
                  nullable=False, comment="Usuario que se verifica."),
        sa.Column("id_administrador", sa.BigInteger,
                  sa.ForeignKey("usuario.id_usuario", name="fk_verificacion_usuario_id_administrador_usuario"),
                  comment="Administrador que resolvió; NULL mientras está PENDIENTE."),
        sa.Column("estado_verificacion", estado_verificacion, nullable=False, server_default="PENDIENTE",
                  comment="PENDIENTE, APROBADA o RECHAZADA."),
        sa.Column("fecha_solicitud", TS, nullable=False, server_default=sa.func.now(),
                  comment="Cuándo se solicitó."),
        sa.Column("fecha_resolucion", TS, comment="Cuándo se resolvió; NULL mientras está PENDIENTE."),
        sa.Column("observaciones", sa.Text, comment="Motivo de la decisión."),
        sa.CheckConstraint("(estado_verificacion = 'PENDIENTE') = (fecha_resolucion IS NULL)",
                           name="ck_verificacion_usuario_resolucion_fechada"),
        sa.CheckConstraint("estado_verificacion = 'PENDIENTE' OR id_administrador IS NOT NULL",
                           name="ck_verificacion_usuario_resolucion_con_administrador"),
        comment="Procesos de verificación de identidad; solo un administrador los resuelve.",
    )
    op.create_index("ix_verificacion_usuario_id_usuario", "verificacion_usuario", ["id_usuario"])
    op.create_index("ux_verificacion_pendiente", "verificacion_usuario", ["id_usuario"], unique=True,
                    postgresql_where=sa.text("estado_verificacion = 'PENDIENTE'"))

    op.create_table(
        "registro_auditoria",
        sa.Column("id_auditoria", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("id_usuario", sa.BigInteger,
                  sa.ForeignKey("usuario.id_usuario", name="fk_registro_auditoria_id_usuario_usuario"),
                  comment="Quién hizo la operación; NULL = sistema."),
        sa.Column("entidad_afectada", sa.String(40), nullable=False,
                  comment="Entidad: donacion, reserva, entrega..."),
        sa.Column("id_registro_afectado", sa.BigInteger, nullable=False,
                  comment="Identificador del registro afectado."),
        sa.Column("accion_realizada", sa.String(60), nullable=False, comment="Acción o tipo de evento."),
        sa.Column("valor_anterior", sa.Text, comment="Estado o valor antes del cambio."),
        sa.Column("valor_nuevo", sa.Text, comment="Estado o valor después del cambio."),
        sa.Column("fecha_operacion", TS, nullable=False, server_default=sa.func.now(), comment="Cuándo ocurrió."),
        comment="Historial de operaciones y cambios de estado de todos los servicios (D-04). Solo inserción.",
    )
    op.create_index("ix_registro_auditoria_id_usuario", "registro_auditoria", ["id_usuario"])
    op.create_index("ix_auditoria_entidad", "registro_auditoria", ["entidad_afectada", "id_registro_afectado"])

    # Reglas que la base hace cumplir aunque la aplicación falle
    op.execute("""
        CREATE FUNCTION fn_verificacion_validar() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'UPDATE' AND OLD.estado_verificacion <> 'PENDIENTE' THEN
            RAISE EXCEPTION 'Una verificación resuelta (%) no se puede modificar', OLD.estado_verificacion
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.id_administrador IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM usuario u JOIN rol r ON r.id_rol = u.id_rol
              WHERE u.id_usuario = NEW.id_administrador AND r.nombre_rol = 'ADMINISTRADOR') THEN
            RAISE EXCEPTION 'Solo un administrador puede resolver verificaciones'
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_verificacion_validar BEFORE INSERT OR UPDATE ON verificacion_usuario
          FOR EACH ROW EXECUTE FUNCTION fn_verificacion_validar();

        CREATE FUNCTION fn_auditoria_solo_insercion() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'registro_auditoria es de solo inserción' USING ERRCODE = 'insufficient_privilege';
        END $$;
        CREATE TRIGGER trg_auditoria_solo_insercion BEFORE UPDATE OR DELETE ON registro_auditoria
          FOR EACH ROW EXECUTE FUNCTION fn_auditoria_solo_insercion();
    """)

    # Permisos del rol de la aplicación (D-04: sin UPDATE ni DELETE sobre la auditoría; sin borrar usuarios)
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            GRANT USAGE ON SCHEMA public TO {ROL_APP};
            GRANT SELECT ON rol TO {ROL_APP};
            GRANT SELECT, INSERT, UPDATE ON usuario, verificacion_usuario TO {ROL_APP};
            GRANT SELECT, INSERT ON registro_auditoria TO {ROL_APP};
            REVOKE UPDATE, DELETE, TRUNCATE ON registro_auditoria FROM {ROL_APP};
            GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {ROL_APP};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("registro_auditoria")
    op.drop_table("verificacion_usuario")
    op.drop_table("usuario")
    op.drop_table("rol")
    op.execute("DROP FUNCTION IF EXISTS fn_auditoria_solo_insercion()")
    op.execute("DROP FUNCTION IF EXISTS fn_verificacion_validar()")
    estado_verificacion.drop(op.get_bind())
    estado_cuenta.drop(op.get_bind())
