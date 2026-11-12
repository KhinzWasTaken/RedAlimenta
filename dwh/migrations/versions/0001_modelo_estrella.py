"""Almacén de datos (S7-01, S7-02): área de paso (stg), modelo en estrella (dw) y control del ETL (etl).

Base separada de las transaccionales: redalimenta_dwh. Claves sustitutas (sk_*) en dimensiones y hechos;
las claves naturales (origen_dato, id_*) se conservan como degeneradas para que la carga sea repetible.
Diseño y granularidad: docs/dwh/modelo-dimensional.md.

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""
import os
import re

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ROL_ETL = os.environ.get("DWH_APP_ROLE", "dwh_app")
if not re.fullmatch(r"[a-z_][a-z0-9_]*", ROL_ETL):
    raise ValueError("DWH_APP_ROLE no es un identificador válido")

ESTADOS = {
    "donacion": [("DISPONIBLE", False), ("RESERVADA", False), ("ENTREGADA", True), ("CANCELADA", True),
                 ("VENCIDA", True)],
    "reserva": [("PENDIENTE", False), ("CONFIRMADA", False), ("EXPIRADA", True), ("COMPLETADA", True),
                ("CANCELADA", True)],
    "entrega": [("PROGRAMADA", False), ("COMPLETADA", True), ("CON_INCIDENCIA", False), ("CANCELADA", True)],
    "necesidad": [("ABIERTA", False), ("CERRADA", True), ("CANCELADA", True)],
    "verificacion": [("PENDIENTE", False), ("APROBADA", True), ("RECHAZADA", True)],
    "usuario": [("ACTIVA", False), ("DESACTIVADA", True)],
    "notificacion": [("NO_LEIDA", False), ("LEIDA", False), ("ARCHIVADA", True)],
}


def upgrade() -> None:
    op.execute("""
    CREATE SCHEMA stg;
    CREATE SCHEMA dw;
    CREATE SCHEMA etl;
    COMMENT ON SCHEMA stg IS 'Área de paso: datos tal como llegan de las fuentes (bases transaccionales, eventos y generador sintético).';
    COMMENT ON SCHEMA dw IS 'Modelo en estrella para indicadores y reportes (RF9).';
    COMMENT ON SCHEMA etl IS 'Control de las cargas: ejecuciones, marcas de agua y resultados de calidad.';

    -- ===================== Dimensiones =====================
    CREATE TABLE dw.dim_tiempo (
        sk_tiempo        integer PRIMARY KEY,
        fecha            date UNIQUE,
        anio             smallint,
        trimestre        smallint,
        mes              smallint,
        nombre_mes       varchar(12),
        semana_iso       smallint,
        dia              smallint,
        dia_semana       smallint,
        nombre_dia       varchar(12),
        es_fin_de_semana boolean
    );
    COMMENT ON TABLE dw.dim_tiempo IS 'Calendario (un día por fila, 2020–2030). sk_tiempo = AAAAMMDD; -1 = sin fecha.';

    INSERT INTO dw.dim_tiempo VALUES (-1, NULL, NULL, NULL, NULL, 'Sin fecha', NULL, NULL, NULL, 'Sin fecha', NULL);
    INSERT INTO dw.dim_tiempo
    SELECT to_char(d, 'YYYYMMDD')::int, d, extract(year FROM d), extract(quarter FROM d), extract(month FROM d),
           (ARRAY['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre',
                  'noviembre','diciembre'])[extract(month FROM d)],
           extract(week FROM d), extract(day FROM d), extract(isodow FROM d),
           (ARRAY['lunes','martes','miércoles','jueves','viernes','sábado','domingo'])[extract(isodow FROM d)],
           extract(isodow FROM d) >= 6
    FROM generate_series(date '2020-01-01', date '2030-12-31', interval '1 day') AS d;

    CREATE TABLE dw.dim_categoria (
        sk_categoria     serial PRIMARY KEY,
        id_categoria     integer UNIQUE,
        nombre_categoria varchar(60) NOT NULL
    );
    COMMENT ON TABLE dw.dim_categoria IS 'Categorías de alimentos (tipo 1: se sobrescribe el nombre). -1 = sin categoría.';
    INSERT INTO dw.dim_categoria VALUES (-1, NULL, 'Sin categoría');

    CREATE TABLE dw.dim_ubicacion (
        sk_ubicacion serial PRIMARY KEY,
        departamento varchar(80) NOT NULL,
        ciudad       varchar(80) NOT NULL,
        latitud      double precision,
        longitud     double precision,
        UNIQUE (departamento, ciudad)
    );
    COMMENT ON TABLE dw.dim_ubicacion IS 'Geografía al nivel de ciudad (jerarquía departamento → ciudad) con un punto representativo para mapas.';
    INSERT INTO dw.dim_ubicacion VALUES (-1, 'Desconocido', 'Desconocida', NULL, NULL);

    CREATE TABLE dw.dim_usuario (
        sk_usuario  serial PRIMARY KEY,
        origen_dato varchar(10) NOT NULL,
        id_usuario  bigint,
        rol         varchar(20) NOT NULL,
        UNIQUE (origen_dato, id_usuario)
    );
    COMMENT ON TABLE dw.dim_usuario IS 'Participantes sin datos personales (Ley 1581): solo identificador y rol.';
    INSERT INTO dw.dim_usuario VALUES (-1, 'N/A', NULL, 'DESCONOCIDO');

    CREATE TABLE dw.dim_estado (
        sk_estado smallint PRIMARY KEY,
        entidad   varchar(20) NOT NULL,
        estado    varchar(30) NOT NULL,
        es_final  boolean NOT NULL,
        UNIQUE (entidad, estado)
    );
    COMMENT ON TABLE dw.dim_estado IS 'Estados del ciclo de vida de cada entidad (D-03). -1 = sin estado.';
    INSERT INTO dw.dim_estado VALUES (-1, 'ninguna', 'SIN_ESTADO', false);

    -- ===================== Hechos =====================
    CREATE TABLE dw.fact_donacion (
        sk_donacion            bigserial PRIMARY KEY,
        origen_dato            varchar(10) NOT NULL CHECK (origen_dato IN ('REAL', 'SINTETICO')),
        id_donacion            bigint NOT NULL,
        sk_tiempo_publicacion  integer NOT NULL REFERENCES dw.dim_tiempo,
        sk_tiempo_vencimiento  integer NOT NULL REFERENCES dw.dim_tiempo,
        sk_categoria           integer NOT NULL REFERENCES dw.dim_categoria,
        sk_ubicacion           integer NOT NULL REFERENCES dw.dim_ubicacion,
        sk_donante             integer NOT NULL REFERENCES dw.dim_usuario,
        sk_estado              smallint NOT NULL REFERENCES dw.dim_estado,
        cantidad               numeric(12,2) NOT NULL CHECK (cantidad > 0),
        unidad_medida          varchar(30) NOT NULL,
        horas_vida             numeric(10,2),
        fecha_publicacion      timestamptz NOT NULL,
        fecha_vencimiento      timestamptz,
        fecha_actualizacion    timestamptz NOT NULL DEFAULT now(),
        UNIQUE (origen_dato, id_donacion)
    );
    COMMENT ON TABLE dw.fact_donacion IS 'Granularidad: una fila por donación (instantánea acumulada: el estado se actualiza en cada carga).';

    CREATE TABLE dw.fact_reserva (
        sk_reserva           bigserial PRIMARY KEY,
        origen_dato          varchar(10) NOT NULL CHECK (origen_dato IN ('REAL', 'SINTETICO')),
        id_reserva           bigint NOT NULL,
        id_donacion          bigint NOT NULL,
        sk_tiempo_reserva    integer NOT NULL REFERENCES dw.dim_tiempo,
        sk_categoria         integer NOT NULL REFERENCES dw.dim_categoria,
        sk_ubicacion         integer NOT NULL REFERENCES dw.dim_ubicacion,
        sk_donante           integer NOT NULL REFERENCES dw.dim_usuario,
        sk_receptor          integer NOT NULL REFERENCES dw.dim_usuario,
        sk_estado            smallint NOT NULL REFERENCES dw.dim_estado,
        fecha_reserva        timestamptz NOT NULL,
        fecha_expiracion     timestamptz NOT NULL,
        fecha_actualizacion  timestamptz NOT NULL DEFAULT now(),
        UNIQUE (origen_dato, id_reserva)
    );
    COMMENT ON TABLE dw.fact_reserva IS 'Granularidad: una fila por reserva, con el estado vigente.';

    CREATE TABLE dw.fact_entrega (
        sk_entrega                  bigserial PRIMARY KEY,
        origen_dato                 varchar(10) NOT NULL CHECK (origen_dato IN ('REAL', 'SINTETICO')),
        id_entrega                  bigint NOT NULL,
        id_reserva                  bigint NOT NULL,
        id_donacion                 bigint NOT NULL,
        sk_tiempo_programada        integer NOT NULL REFERENCES dw.dim_tiempo,
        sk_tiempo_entrega           integer NOT NULL REFERENCES dw.dim_tiempo,
        sk_categoria                integer NOT NULL REFERENCES dw.dim_categoria,
        sk_ubicacion                integer NOT NULL REFERENCES dw.dim_ubicacion,
        sk_donante                  integer NOT NULL REFERENCES dw.dim_usuario,
        sk_receptor                 integer NOT NULL REFERENCES dw.dim_usuario,
        sk_estado                   smallint NOT NULL REFERENCES dw.dim_estado,
        cantidad                    numeric(12,2) NOT NULL CHECK (cantidad > 0),
        unidad_medida               varchar(30) NOT NULL,
        horas_publicacion_a_entrega numeric(10,2),
        con_incidencia              boolean NOT NULL DEFAULT false,
        fecha_entrega               timestamptz,
        fecha_actualizacion         timestamptz NOT NULL DEFAULT now(),
        UNIQUE (origen_dato, id_entrega)
    );
    COMMENT ON TABLE dw.fact_entrega IS 'Granularidad: una fila por entrega; la cantidad es la de la donación entregada (D-05: la reserva cubre la donación completa).';

    CREATE TABLE dw.fact_cambio_estado (
        id_evento          uuid PRIMARY KEY,
        sk_tiempo          integer NOT NULL REFERENCES dw.dim_tiempo,
        fecha              timestamptz NOT NULL,
        tipo               varchar(60) NOT NULL,
        entidad            varchar(40) NOT NULL,
        id_entidad         bigint NOT NULL,
        sk_estado_anterior smallint NOT NULL REFERENCES dw.dim_estado,
        sk_estado_nuevo    smallint NOT NULL REFERENCES dw.dim_estado,
        sk_actor           integer NOT NULL REFERENCES dw.dim_usuario,
        servicio_origen    varchar(40),
        id_correlacion     varchar(64)
    );
    COMMENT ON TABLE dw.fact_cambio_estado IS 'Granularidad: un evento (cambio de estado u operación) tal como lo publicó un servicio. Carga continua (S7-05).';

    CREATE INDEX ix_fact_donacion_tiempo ON dw.fact_donacion (sk_tiempo_publicacion);
    CREATE INDEX ix_fact_donacion_ubicacion ON dw.fact_donacion (sk_ubicacion, sk_categoria);
    CREATE INDEX ix_fact_reserva_tiempo ON dw.fact_reserva (sk_tiempo_reserva);
    CREATE INDEX ix_fact_reserva_donacion ON dw.fact_reserva (origen_dato, id_donacion);
    CREATE INDEX ix_fact_entrega_tiempo ON dw.fact_entrega (sk_tiempo_entrega);
    CREATE INDEX ix_fact_entrega_reserva ON dw.fact_entrega (origen_dato, id_reserva);
    CREATE INDEX ix_fact_cambio_entidad ON dw.fact_cambio_estado (entidad, id_entidad, fecha);

    -- ===================== Área de paso =====================
    CREATE TABLE stg.usuario (
        origen_dato varchar(10) NOT NULL, id_usuario bigint NOT NULL, rol varchar(20) NOT NULL,
        estado_verificacion varchar(20), fecha_carga timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (origen_dato, id_usuario));
    CREATE TABLE stg.categoria (
        id_categoria integer PRIMARY KEY, nombre_categoria varchar(60) NOT NULL,
        fecha_carga timestamptz NOT NULL DEFAULT now());
    CREATE TABLE stg.donacion (
        origen_dato varchar(10) NOT NULL, id_donacion bigint NOT NULL, id_donante bigint NOT NULL,
        id_categoria integer, cantidad numeric(12,2), unidad_medida varchar(30), fecha_publicacion timestamptz,
        fecha_vencimiento timestamptz, estado_donacion varchar(20), ciudad varchar(80), departamento varchar(80),
        latitud double precision, longitud double precision, fecha_carga timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (origen_dato, id_donacion));
    CREATE TABLE stg.reserva (
        origen_dato varchar(10) NOT NULL, id_reserva bigint NOT NULL, id_donacion bigint NOT NULL,
        id_receptor bigint NOT NULL, fecha_reserva timestamptz, fecha_expiracion timestamptz,
        estado_reserva varchar(20), fecha_carga timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (origen_dato, id_reserva));
    CREATE TABLE stg.entrega (
        origen_dato varchar(10) NOT NULL, id_entrega bigint NOT NULL, id_reserva bigint NOT NULL,
        fecha_programada timestamptz, fecha_entrega timestamptz, estado_entrega varchar(20),
        con_incidencia boolean NOT NULL DEFAULT false, fecha_carga timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (origen_dato, id_entrega));
    CREATE TABLE stg.evento (
        id_evento uuid PRIMARY KEY, tipo varchar(60) NOT NULL, version smallint, origen varchar(40),
        fecha timestamptz NOT NULL, id_actor bigint, entidad varchar(40) NOT NULL, id_entidad bigint NOT NULL,
        estado_anterior varchar(40), estado_nuevo varchar(40), datos jsonb NOT NULL DEFAULT '{}',
        id_correlacion varchar(64), fecha_recepcion timestamptz NOT NULL,
        fecha_carga timestamptz NOT NULL DEFAULT now(), transformado boolean NOT NULL DEFAULT false);
    COMMENT ON TABLE stg.evento IS 'Eventos crudos copiados del historial de analytics (carga continua, S7-05).';
    CREATE INDEX ix_stg_evento_pendiente ON stg.evento (fecha) WHERE NOT transformado;

    -- ===================== Control del ETL =====================
    CREATE TABLE etl.ejecucion (
        id_ejecucion bigserial PRIMARY KEY,
        tipo         varchar(30) NOT NULL,
        intento      smallint NOT NULL DEFAULT 1,
        inicio       timestamptz NOT NULL DEFAULT now(),
        fin          timestamptz,
        estado       varchar(12) NOT NULL DEFAULT 'EN_CURSO' CHECK (estado IN ('EN_CURSO', 'EXITOSA', 'FALLIDA')),
        filas        jsonb NOT NULL DEFAULT '{}',
        error        text
    );
    COMMENT ON TABLE etl.ejecucion IS 'Registro de cada carga (S7-07): cuándo corrió, cuánto cargó y si falló.';
    CREATE TABLE etl.marca_agua (
        fuente varchar(40) PRIMARY KEY,
        valor  timestamptz NOT NULL
    );
    COMMENT ON TABLE etl.marca_agua IS 'Hasta dónde se leyó cada fuente incremental (eventos por fecha de recepción).';
    CREATE TABLE etl.resultado_calidad (
        id_resultado       bigserial PRIMARY KEY,
        id_ejecucion       bigint NOT NULL REFERENCES etl.ejecucion,
        regla              varchar(60) NOT NULL,
        descripcion        text NOT NULL,
        filas_con_problema bigint NOT NULL,
        aprobada           boolean NOT NULL,
        fecha              timestamptz NOT NULL DEFAULT now()
    );
    COMMENT ON TABLE etl.resultado_calidad IS 'Informe de calidad generado en cada carga (S7-06).';
    """)
    valores = []
    sk = 1
    for entidad, estados in ESTADOS.items():
        for estado, final in estados:
            valores.append(f"({sk}, '{entidad}', '{estado}', {'true' if final else 'false'})")
            sk += 1
    op.execute("INSERT INTO dw.dim_estado VALUES " + ", ".join(valores))
    op.execute(f"""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROL_ETL}') THEN
        GRANT USAGE ON SCHEMA stg, dw, etl TO {ROL_ETL};
        GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA stg TO {ROL_ETL};
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA dw, etl TO {ROL_ETL};
        -- Solo para regenerar los datos sintéticos (el ETL nunca borra hechos reales)
        GRANT DELETE ON dw.fact_donacion, dw.fact_reserva, dw.fact_entrega TO {ROL_ETL};
        GRANT USAGE ON ALL SEQUENCES IN SCHEMA dw, etl TO {ROL_ETL};
      END IF;
    END $$;
    """)


def downgrade() -> None:
    op.execute("DROP SCHEMA etl CASCADE; DROP SCHEMA dw CASCADE; DROP SCHEMA stg CASCADE;")
