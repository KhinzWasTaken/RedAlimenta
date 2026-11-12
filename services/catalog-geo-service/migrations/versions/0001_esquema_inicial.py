"""Esquema inicial de catalog-geo-service: categoría, ubicación, donación y necesidad (S4-04).

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

from catalogo.db import ROL_APP

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

estado_donacion = postgresql.ENUM("DISPONIBLE", "RESERVADA", "ENTREGADA", "CANCELADA", "VENCIDA",
                                  name="estado_donacion", create_type=False)
estado_necesidad = postgresql.ENUM("ABIERTA", "CERRADA", "CANCELADA", name="estado_necesidad", create_type=False)
nivel_urgencia = postgresql.ENUM("BAJA", "MEDIA", "ALTA", "CRITICA", name="nivel_urgencia", create_type=False)
TS = sa.DateTime(timezone=True)
TIPOS = (estado_donacion, estado_necesidad, nivel_urgencia)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    for tipo in TIPOS:
        tipo.create(op.get_bind())

    categoria = op.create_table(
        "categoria_alimento",
        sa.Column("id_categoria", sa.SmallInteger, primary_key=True, comment="Identificador."),
        sa.Column("nombre_categoria", sa.String(60), nullable=False, comment="Nombre único de la categoría."),
        sa.Column("descripcion", sa.String(200), comment="Qué alimentos incluye."),
        sa.UniqueConstraint("nombre_categoria", name="uq_categoria_alimento_nombre_categoria"),
        comment="Clasificación de los alimentos de donaciones y necesidades.",
    )
    op.bulk_insert(categoria, [
        {"id_categoria": 1, "nombre_categoria": "Frutas y verduras", "descripcion": "Productos frescos"},
        {"id_categoria": 2, "nombre_categoria": "Lácteos y huevos", "descripcion": "Leche, yogur, queso, huevos"},
        {"id_categoria": 3, "nombre_categoria": "Panadería", "descripcion": "Pan y productos horneados"},
        {"id_categoria": 4, "nombre_categoria": "Granos y enlatados",
         "descripcion": "Arroz, fríjol, lentejas, enlatados"},
        {"id_categoria": 5, "nombre_categoria": "Carnes y proteínas", "descripcion": "Carne, pollo, pescado"},
        {"id_categoria": 6, "nombre_categoria": "Comidas preparadas", "descripcion": "Almuerzos y refrigerios listos"},
        {"id_categoria": 7, "nombre_categoria": "Bebidas", "descripcion": "Agua potable, jugos"},
    ])

    op.create_table(
        "ubicacion_geografica",
        sa.Column("id_ubicacion", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("direccion_referencia", sa.String(200),
                  comment="Dirección escrita como referencia; el punto manda."),
        sa.Column("ciudad", sa.String(80), nullable=False, comment="Ciudad o municipio."),
        sa.Column("departamento", sa.String(80), nullable=False, comment="Departamento de Colombia."),
        sa.Column("coordenada_geografica", Geography("POINT", srid=4326, spatial_index=False), nullable=False,
                  comment="Punto WGS84 (SRID 4326); distancias en metros."),
        comment="Puntos de recogida (donaciones) y de entrega (necesidades).",
    )
    op.create_index("ix_ubicacion_coordenada", "ubicacion_geografica", ["coordenada_geografica"],
                    postgresql_using="gist")

    op.create_table(
        "donacion",
        sa.Column("id_donacion", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("id_donante", sa.BigInteger, nullable=False,
                  comment="Usuario donante (identity-service; sin FK entre bases, D-06)."),
        sa.Column("id_categoria", sa.SmallInteger,
                  sa.ForeignKey("categoria_alimento.id_categoria", name="fk_donacion_id_categoria_categoria_alimento"),
                  nullable=False, comment="Categoría del alimento."),
        sa.Column("id_ubicacion", sa.BigInteger,
                  sa.ForeignKey("ubicacion_geografica.id_ubicacion",
                                name="fk_donacion_id_ubicacion_ubicacion_geografica"),
                  nullable=False, comment="Punto de recogida."),
        sa.Column("nombre_alimento", sa.String(120), nullable=False, comment="Qué se dona."),
        sa.Column("descripcion", sa.Text, comment="Detalle del alimento."),
        sa.Column("cantidad", sa.Numeric(12, 2), nullable=False, comment="Cantidad ofrecida; mayor que cero."),
        sa.Column("unidad_medida", sa.String(30), nullable=False, comment="kg, litros, unidades, porciones..."),
        sa.Column("fecha_vencimiento", TS,
                  comment="Hasta cuándo es apto; NULL si no aplica (p. ej. agua embotellada)."),
        sa.Column("fecha_publicacion", TS, nullable=False, server_default=sa.func.now(), comment="Cuándo se publicó."),
        sa.Column("condiciones_recogida", sa.Text, comment="Horario, cadena de frío, acceso..."),
        sa.Column("estado_donacion", estado_donacion, nullable=False, server_default="DISPONIBLE",
                  comment="DISPONIBLE, RESERVADA, ENTREGADA, CANCELADA o VENCIDA."),
        sa.CheckConstraint("cantidad > 0", name=op.f("ck_donacion_cantidad_positiva")),
        sa.CheckConstraint("fecha_vencimiento IS NULL OR fecha_vencimiento > fecha_publicacion",
                           name=op.f("ck_donacion_vence_despues_de_publicar")),
        comment="Alimentos ofrecidos por los donantes. Solo este servicio cambia estado_donacion (D-01).",
    )
    for columna in ("id_donante", "id_categoria", "id_ubicacion", "estado_donacion"):
        op.create_index(f"ix_donacion_{columna}", "donacion", [columna])

    op.create_table(
        "necesidad_alimentaria",
        sa.Column("id_necesidad", sa.BigInteger, primary_key=True, comment="Identificador."),
        sa.Column("id_receptor", sa.BigInteger, nullable=False,
                  comment="Usuario receptor (identity-service; sin FK entre bases, D-06)."),
        sa.Column("id_categoria", sa.SmallInteger,
                  sa.ForeignKey("categoria_alimento.id_categoria",
                                name="fk_necesidad_alimentaria_id_categoria_categoria_alimento"),
                  nullable=False, comment="Tipo de alimento requerido."),
        sa.Column("id_ubicacion", sa.BigInteger,
                  sa.ForeignKey("ubicacion_geografica.id_ubicacion",
                                name="fk_necesidad_alimentaria_id_ubicacion_ubicacion_geografica"),
                  nullable=False, comment="Dónde se atiende a la población."),
        sa.Column("descripcion", sa.Text, nullable=False, comment="Qué se necesita y para quién."),
        sa.Column("cantidad_requerida", sa.Numeric(12, 2), nullable=False,
                  comment="Cantidad requerida; mayor que cero."),
        sa.Column("unidad_medida", sa.String(30), nullable=False, comment="kg, litros, unidades, porciones..."),
        sa.Column("nivel_urgencia", nivel_urgencia, nullable=False, comment="BAJA, MEDIA, ALTA o CRITICA."),
        sa.Column("fecha_limite", TS, comment="Hasta cuándo se necesita."),
        sa.Column("estado_necesidad", estado_necesidad, nullable=False, server_default="ABIERTA",
                  comment="ABIERTA, CERRADA o CANCELADA."),
        sa.CheckConstraint("cantidad_requerida > 0", name=op.f("ck_necesidad_alimentaria_cantidad_positiva")),
        comment="Lo que necesitan los receptores; alimenta la búsqueda y la prioridad (D-05).",
    )
    for columna in ("id_receptor", "id_categoria", "id_ubicacion"):
        op.create_index(f"ix_necesidad_alimentaria_{columna}", "necesidad_alimentaria", [columna])

    # D-01 y docs/modelo/estados.md: la base rechaza transiciones ilegales y cambios a registros cerrados
    op.execute("""
        CREATE FUNCTION fn_donacion_validar() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.estado_donacion IS DISTINCT FROM OLD.estado_donacion AND NOT (
               (OLD.estado_donacion = 'DISPONIBLE' AND NEW.estado_donacion IN ('RESERVADA', 'CANCELADA', 'VENCIDA'))
            OR (OLD.estado_donacion = 'RESERVADA' AND NEW.estado_donacion IN ('DISPONIBLE', 'VENCIDA', 'ENTREGADA'))
          ) THEN
            RAISE EXCEPTION 'Transición de donación no permitida: % → %', OLD.estado_donacion, NEW.estado_donacion
              USING ERRCODE = 'check_violation';
          END IF;
          IF OLD.estado_donacion <> 'DISPONIBLE' AND
             (NEW.nombre_alimento, NEW.descripcion, NEW.cantidad, NEW.unidad_medida, NEW.fecha_vencimiento,
              NEW.condiciones_recogida, NEW.id_categoria, NEW.id_ubicacion, NEW.id_donante)
             IS DISTINCT FROM
             (OLD.nombre_alimento, OLD.descripcion, OLD.cantidad, OLD.unidad_medida, OLD.fecha_vencimiento,
              OLD.condiciones_recogida, OLD.id_categoria, OLD.id_ubicacion, OLD.id_donante) THEN
            RAISE EXCEPTION 'Solo se modifica una donación DISPONIBLE (está %)', OLD.estado_donacion
              USING ERRCODE = 'check_violation';
          END IF;
          IF OLD.estado_donacion = 'DISPONIBLE' AND NEW.estado_donacion = 'RESERVADA'
             AND NEW.fecha_vencimiento IS NOT NULL AND NEW.fecha_vencimiento <= now() THEN
            RAISE EXCEPTION 'La donación ya venció y no se puede reservar' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_donacion_validar BEFORE UPDATE ON donacion
          FOR EACH ROW EXECUTE FUNCTION fn_donacion_validar();

        CREATE FUNCTION fn_necesidad_validar() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.estado_necesidad <> 'ABIERTA' THEN
            RAISE EXCEPTION 'La necesidad está % y no se puede modificar', OLD.estado_necesidad
              USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_necesidad_validar BEFORE UPDATE ON necesidad_alimentaria
          FOR EACH ROW EXECUTE FUNCTION fn_necesidad_validar();
    """)

    # Permisos del rol de la aplicación: cancelar es un cambio de estado, no un DELETE
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_APP}') THEN
            GRANT USAGE ON SCHEMA public TO {ROL_APP};
            GRANT SELECT ON categoria_alimento, spatial_ref_sys TO {ROL_APP};
            GRANT SELECT, INSERT, UPDATE ON ubicacion_geografica, donacion, necesidad_alimentaria TO {ROL_APP};
            GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {ROL_APP};
          END IF;
        END $$;
    """)


def downgrade() -> None:
    for tabla in ("necesidad_alimentaria", "donacion", "ubicacion_geografica", "categoria_alimento"):
        op.drop_table(tabla)
    op.execute("DROP FUNCTION IF EXISTS fn_necesidad_validar()")
    op.execute("DROP FUNCTION IF EXISTS fn_donacion_validar()")
    for tipo in TIPOS:
        tipo.drop(op.get_bind())
    # La extensión PostGIS se conserva: la instala el administrador de la base (infra/postgres/init)
