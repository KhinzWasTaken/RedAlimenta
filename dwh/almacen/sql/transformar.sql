-- Transformación del área de paso al modelo en estrella (S7-04, S7-03).
-- Idempotente: claves naturales (origen_dato, id_*) con ON CONFLICT … DO UPDATE; repetirla no duplica filas.
-- Las fechas se asignan al día calendario de Colombia (America/Bogota).

-- Dimensiones -------------------------------------------------------------------------------------------
INSERT INTO dw.dim_categoria (id_categoria, nombre_categoria)
SELECT id_categoria, nombre_categoria FROM stg.categoria
ON CONFLICT (id_categoria) DO UPDATE SET nombre_categoria = EXCLUDED.nombre_categoria;

INSERT INTO dw.dim_ubicacion (departamento, ciudad, latitud, longitud)
SELECT departamento, ciudad, avg(latitud), avg(longitud)
FROM stg.donacion
WHERE ciudad IS NOT NULL AND departamento IS NOT NULL
GROUP BY departamento, ciudad
ON CONFLICT (departamento, ciudad) DO UPDATE SET latitud = EXCLUDED.latitud, longitud = EXCLUDED.longitud;

INSERT INTO dw.dim_usuario (origen_dato, id_usuario, rol)
SELECT origen_dato, id_usuario, rol FROM stg.usuario
ON CONFLICT (origen_dato, id_usuario) DO UPDATE SET rol = EXCLUDED.rol;

-- Hechos: donaciones ------------------------------------------------------------------------------------
INSERT INTO dw.fact_donacion (origen_dato, id_donacion, sk_tiempo_publicacion, sk_tiempo_vencimiento, sk_categoria,
                              sk_ubicacion, sk_donante, sk_estado, cantidad, unidad_medida, horas_vida,
                              fecha_publicacion, fecha_vencimiento, fecha_actualizacion)
SELECT d.origen_dato, d.id_donacion,
       to_char(d.fecha_publicacion AT TIME ZONE 'America/Bogota', 'YYYYMMDD')::int,
       coalesce(to_char(d.fecha_vencimiento AT TIME ZONE 'America/Bogota', 'YYYYMMDD')::int, -1),
       coalesce(c.sk_categoria, -1), coalesce(u.sk_ubicacion, -1), coalesce(p.sk_usuario, -1),
       coalesce(e.sk_estado, -1), d.cantidad, d.unidad_medida,
       round((extract(epoch FROM d.fecha_vencimiento - d.fecha_publicacion) / 3600)::numeric, 2),
       d.fecha_publicacion, d.fecha_vencimiento, now()
FROM stg.donacion d
LEFT JOIN dw.dim_categoria c ON c.id_categoria = d.id_categoria
LEFT JOIN dw.dim_ubicacion u ON u.departamento = d.departamento AND u.ciudad = d.ciudad
LEFT JOIN dw.dim_usuario p ON p.origen_dato = d.origen_dato AND p.id_usuario = d.id_donante
LEFT JOIN dw.dim_estado e ON e.entidad = 'donacion' AND e.estado = d.estado_donacion
ON CONFLICT (origen_dato, id_donacion) DO UPDATE SET
    sk_tiempo_vencimiento = EXCLUDED.sk_tiempo_vencimiento, sk_categoria = EXCLUDED.sk_categoria,
    sk_ubicacion = EXCLUDED.sk_ubicacion, sk_donante = EXCLUDED.sk_donante, sk_estado = EXCLUDED.sk_estado,
    cantidad = EXCLUDED.cantidad, unidad_medida = EXCLUDED.unidad_medida, horas_vida = EXCLUDED.horas_vida,
    fecha_vencimiento = EXCLUDED.fecha_vencimiento, fecha_actualizacion = now();

-- Hechos: reservas (heredan categoría, ubicación y donante de su donación) ------------------------------
INSERT INTO dw.fact_reserva (origen_dato, id_reserva, id_donacion, sk_tiempo_reserva, sk_categoria, sk_ubicacion,
                             sk_donante, sk_receptor, sk_estado, fecha_reserva, fecha_expiracion, fecha_actualizacion)
SELECT r.origen_dato, r.id_reserva, r.id_donacion,
       to_char(r.fecha_reserva AT TIME ZONE 'America/Bogota', 'YYYYMMDD')::int,
       coalesce(fd.sk_categoria, -1), coalesce(fd.sk_ubicacion, -1), coalesce(fd.sk_donante, -1),
       coalesce(p.sk_usuario, -1), coalesce(e.sk_estado, -1), r.fecha_reserva, r.fecha_expiracion, now()
FROM stg.reserva r
LEFT JOIN dw.fact_donacion fd ON fd.origen_dato = r.origen_dato AND fd.id_donacion = r.id_donacion
LEFT JOIN dw.dim_usuario p ON p.origen_dato = r.origen_dato AND p.id_usuario = r.id_receptor
LEFT JOIN dw.dim_estado e ON e.entidad = 'reserva' AND e.estado = r.estado_reserva
ON CONFLICT (origen_dato, id_reserva) DO UPDATE SET
    sk_estado = EXCLUDED.sk_estado, sk_categoria = EXCLUDED.sk_categoria, sk_ubicacion = EXCLUDED.sk_ubicacion,
    sk_donante = EXCLUDED.sk_donante, sk_receptor = EXCLUDED.sk_receptor,
    fecha_expiracion = EXCLUDED.fecha_expiracion, fecha_actualizacion = now();

-- Hechos: entregas --------------------------------------------------------------------------------------
INSERT INTO dw.fact_entrega (origen_dato, id_entrega, id_reserva, id_donacion, sk_tiempo_programada,
                             sk_tiempo_entrega, sk_categoria, sk_ubicacion, sk_donante, sk_receptor, sk_estado,
                             cantidad, unidad_medida, horas_publicacion_a_entrega, con_incidencia, fecha_entrega,
                             fecha_actualizacion)
SELECT en.origen_dato, en.id_entrega, en.id_reserva, fr.id_donacion,
       coalesce(to_char(en.fecha_programada AT TIME ZONE 'America/Bogota', 'YYYYMMDD')::int, -1),
       coalesce(to_char(en.fecha_entrega AT TIME ZONE 'America/Bogota', 'YYYYMMDD')::int, -1),
       fr.sk_categoria, fr.sk_ubicacion, fr.sk_donante, fr.sk_receptor, coalesce(e.sk_estado, -1),
       fd.cantidad, fd.unidad_medida,
       round((extract(epoch FROM en.fecha_entrega - fd.fecha_publicacion) / 3600)::numeric, 2),
       en.con_incidencia OR en.estado_entrega = 'CON_INCIDENCIA', en.fecha_entrega, now()
FROM stg.entrega en
JOIN dw.fact_reserva fr ON fr.origen_dato = en.origen_dato AND fr.id_reserva = en.id_reserva
JOIN dw.fact_donacion fd ON fd.origen_dato = fr.origen_dato AND fd.id_donacion = fr.id_donacion
LEFT JOIN dw.dim_estado e ON e.entidad = 'entrega' AND e.estado = en.estado_entrega
ON CONFLICT (origen_dato, id_entrega) DO UPDATE SET
    sk_tiempo_programada = EXCLUDED.sk_tiempo_programada, sk_tiempo_entrega = EXCLUDED.sk_tiempo_entrega,
    sk_estado = EXCLUDED.sk_estado, cantidad = EXCLUDED.cantidad, unidad_medida = EXCLUDED.unidad_medida,
    horas_publicacion_a_entrega = EXCLUDED.horas_publicacion_a_entrega, con_incidencia = EXCLUDED.con_incidencia,
    fecha_entrega = EXCLUDED.fecha_entrega, fecha_actualizacion = now();
