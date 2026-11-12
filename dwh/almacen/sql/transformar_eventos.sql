-- Carga continua (S7-05): eventos crudos de stg.evento → hechos. Solo procesa los no transformados y es
-- idempotente: un evento repetido no se vuelve a insertar (PK id_evento) ni vuelve a mover un estado.
-- Entre dos cargas históricas, los eventos mantienen al día el estado de donaciones, reservas y entregas.

CREATE TEMP TABLE ev ON COMMIT DROP AS
SELECT * FROM stg.evento WHERE NOT transformado;

-- Participantes que aparecieron después de la última carga histórica (solo rol, sin datos personales)
INSERT INTO dw.dim_usuario (origen_dato, id_usuario, rol)
SELECT DISTINCT 'REAL', x.id, x.rol FROM (
    SELECT id_entidad AS id, datos->>'rol' AS rol FROM ev WHERE tipo = 'USUARIO_REGISTRADO' AND datos ? 'rol'
    UNION ALL SELECT (datos->>'id_donante')::bigint, 'DONANTE' FROM ev WHERE datos ? 'id_donante'
    UNION ALL SELECT (datos->>'id_receptor')::bigint, 'RECEPTOR' FROM ev
        WHERE datos ? 'id_receptor' AND jsonb_typeof(datos->'id_receptor') = 'number'
) x WHERE x.id IS NOT NULL
ON CONFLICT (origen_dato, id_usuario) DO NOTHING;

INSERT INTO dw.dim_ubicacion (departamento, ciudad)
SELECT DISTINCT datos->>'departamento', datos->>'ciudad' FROM ev
WHERE tipo = 'DONACION_CREADA' AND datos ? 'ciudad' AND datos ? 'departamento'
ON CONFLICT (departamento, ciudad) DO NOTHING;

-- 1. Hecho de cambio de estado: un evento = una fila
INSERT INTO dw.fact_cambio_estado (id_evento, sk_tiempo, fecha, tipo, entidad, id_entidad, sk_estado_anterior,
                                   sk_estado_nuevo, sk_actor, servicio_origen, id_correlacion)
SELECT ev.id_evento, to_char(ev.fecha AT TIME ZONE 'America/Bogota', 'YYYYMMDD')::int, ev.fecha, ev.tipo,
       ev.entidad, ev.id_entidad, coalesce(ea.sk_estado, -1), coalesce(en.sk_estado, -1),
       coalesce(u.sk_usuario, -1), ev.origen, ev.id_correlacion
FROM ev
LEFT JOIN dw.dim_estado ea ON ea.entidad = ev.entidad AND ea.estado = ev.estado_anterior
LEFT JOIN dw.dim_estado en ON en.entidad = ev.entidad AND en.estado = ev.estado_nuevo
LEFT JOIN dw.dim_usuario u ON u.origen_dato = 'REAL' AND u.id_usuario = ev.id_actor
ON CONFLICT (id_evento) DO NOTHING;

-- 2. Donaciones publicadas después de la última carga histórica (el vencimiento llega con la próxima)
INSERT INTO dw.fact_donacion (origen_dato, id_donacion, sk_tiempo_publicacion, sk_tiempo_vencimiento, sk_categoria,
                              sk_ubicacion, sk_donante, sk_estado, cantidad, unidad_medida, fecha_publicacion,
                              fecha_actualizacion)
SELECT 'REAL', ev.id_entidad, to_char(ev.fecha AT TIME ZONE 'America/Bogota', 'YYYYMMDD')::int, -1,
       coalesce(c.sk_categoria, -1), coalesce(ub.sk_ubicacion, -1), coalesce(u.sk_usuario, -1),
       (SELECT sk_estado FROM dw.dim_estado WHERE entidad = 'donacion' AND estado = 'DISPONIBLE'),
       (ev.datos->>'cantidad')::numeric, ev.datos->>'unidad_medida', ev.fecha, ev.fecha
FROM ev
LEFT JOIN dw.dim_categoria c ON c.id_categoria = (ev.datos->>'id_categoria')::int
LEFT JOIN dw.dim_ubicacion ub ON ub.departamento = ev.datos->>'departamento' AND ub.ciudad = ev.datos->>'ciudad'
LEFT JOIN dw.dim_usuario u ON u.origen_dato = 'REAL' AND u.id_usuario = (ev.datos->>'id_donante')::bigint
WHERE ev.tipo = 'DONACION_CREADA' AND ev.datos ? 'cantidad' AND ev.datos ? 'unidad_medida'
ON CONFLICT (origen_dato, id_donacion) DO NOTHING;

-- 3. Reservas creadas después de la última carga histórica
INSERT INTO dw.fact_reserva (origen_dato, id_reserva, id_donacion, sk_tiempo_reserva, sk_categoria, sk_ubicacion,
                             sk_donante, sk_receptor, sk_estado, fecha_reserva, fecha_expiracion, fecha_actualizacion)
SELECT 'REAL', ev.id_entidad, (ev.datos->>'id_donacion')::bigint,
       to_char(ev.fecha AT TIME ZONE 'America/Bogota', 'YYYYMMDD')::int,
       fd.sk_categoria, fd.sk_ubicacion, fd.sk_donante, coalesce(u.sk_usuario, -1),
       (SELECT sk_estado FROM dw.dim_estado WHERE entidad = 'reserva' AND estado = 'PENDIENTE'),
       ev.fecha, coalesce((ev.datos->>'fecha_expiracion')::timestamptz, ev.fecha + interval '2 hours'), ev.fecha
FROM ev
JOIN dw.fact_donacion fd ON fd.origen_dato = 'REAL' AND fd.id_donacion = (ev.datos->>'id_donacion')::bigint
LEFT JOIN dw.dim_usuario u ON u.origen_dato = 'REAL' AND u.id_usuario = (ev.datos->>'id_receptor')::bigint
WHERE ev.tipo = 'RESERVA_CREADA'
ON CONFLICT (origen_dato, id_reserva) DO NOTHING;

-- 4. Entregas programadas después de la última carga histórica
INSERT INTO dw.fact_entrega (origen_dato, id_entrega, id_reserva, id_donacion, sk_tiempo_programada,
                             sk_tiempo_entrega, sk_categoria, sk_ubicacion, sk_donante, sk_receptor, sk_estado,
                             cantidad, unidad_medida, fecha_actualizacion)
SELECT 'REAL', ev.id_entidad, fr.id_reserva, fr.id_donacion, -1, -1, fr.sk_categoria, fr.sk_ubicacion,
       fr.sk_donante, fr.sk_receptor,
       (SELECT sk_estado FROM dw.dim_estado WHERE entidad = 'entrega' AND estado = 'PROGRAMADA'),
       fd.cantidad, fd.unidad_medida, ev.fecha
FROM ev
JOIN dw.fact_reserva fr ON fr.origen_dato = 'REAL' AND fr.id_reserva = (ev.datos->>'id_reserva')::bigint
JOIN dw.fact_donacion fd ON fd.origen_dato = 'REAL' AND fd.id_donacion = fr.id_donacion
WHERE ev.tipo = 'ENTREGA_PROGRAMADA'
ON CONFLICT (origen_dato, id_entrega) DO NOTHING;

-- 5. Estado vigente: el último cambio de estado de cada registro, si es más nuevo que lo que hay en el hecho
WITH ultimo AS (
    SELECT DISTINCT ON (ev.entidad, ev.id_entidad) ev.entidad, ev.id_entidad, ev.estado_nuevo, ev.fecha, ev.tipo,
           e.sk_estado
    FROM ev JOIN dw.dim_estado e ON e.entidad = ev.entidad AND e.estado = ev.estado_nuevo
    WHERE ev.estado_anterior IS DISTINCT FROM ev.estado_nuevo
    ORDER BY ev.entidad, ev.id_entidad, ev.fecha DESC
)
UPDATE dw.fact_donacion f SET sk_estado = ultimo.sk_estado, fecha_actualizacion = ultimo.fecha
FROM ultimo
WHERE ultimo.entidad = 'donacion' AND f.origen_dato = 'REAL' AND f.id_donacion = ultimo.id_entidad
  AND ultimo.fecha > f.fecha_actualizacion;

WITH ultimo AS (
    SELECT DISTINCT ON (ev.id_entidad) ev.id_entidad, ev.fecha, e.sk_estado
    FROM ev JOIN dw.dim_estado e ON e.entidad = 'reserva' AND e.estado = ev.estado_nuevo
    WHERE ev.entidad = 'reserva' AND ev.estado_anterior IS DISTINCT FROM ev.estado_nuevo
    ORDER BY ev.id_entidad, ev.fecha DESC
)
UPDATE dw.fact_reserva f SET sk_estado = ultimo.sk_estado, fecha_actualizacion = ultimo.fecha
FROM ultimo
WHERE f.origen_dato = 'REAL' AND f.id_reserva = ultimo.id_entidad AND ultimo.fecha > f.fecha_actualizacion;

WITH ultimo AS (
    SELECT DISTINCT ON (ev.id_entidad) ev.id_entidad, ev.fecha, ev.estado_nuevo, e.sk_estado
    FROM ev JOIN dw.dim_estado e ON e.entidad = 'entrega' AND e.estado = ev.estado_nuevo
    WHERE ev.entidad = 'entrega' AND ev.estado_anterior IS DISTINCT FROM ev.estado_nuevo
    ORDER BY ev.id_entidad, ev.fecha DESC
)
UPDATE dw.fact_entrega f SET
    sk_estado = ultimo.sk_estado, fecha_actualizacion = ultimo.fecha,
    con_incidencia = f.con_incidencia OR ultimo.estado_nuevo = 'CON_INCIDENCIA',
    fecha_entrega = CASE WHEN ultimo.estado_nuevo = 'COMPLETADA' THEN ultimo.fecha ELSE f.fecha_entrega END,
    sk_tiempo_entrega = CASE WHEN ultimo.estado_nuevo = 'COMPLETADA'
                             THEN to_char(ultimo.fecha AT TIME ZONE 'America/Bogota', 'YYYYMMDD')::int
                             ELSE f.sk_tiempo_entrega END,
    horas_publicacion_a_entrega = CASE WHEN ultimo.estado_nuevo = 'COMPLETADA'
        THEN round((extract(epoch FROM ultimo.fecha - (SELECT fecha_publicacion FROM dw.fact_donacion d
              WHERE d.origen_dato = 'REAL' AND d.id_donacion = f.id_donacion)) / 3600)::numeric, 2)
        ELSE f.horas_publicacion_a_entrega END
FROM ultimo
WHERE f.origen_dato = 'REAL' AND f.id_entrega = ultimo.id_entidad AND ultimo.fecha > f.fecha_actualizacion;

UPDATE stg.evento SET transformado = true WHERE id_evento IN (SELECT id_evento FROM ev);
