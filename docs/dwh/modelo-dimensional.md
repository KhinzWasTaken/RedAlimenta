# Almacén de datos: diseño dimensional (S7-01)

Base separada `redalimenta_dwh` con tres esquemas: `stg` (área de paso), `dw` (estrella) y `etl` (control y
calidad). Columnas y restricciones exactas: `docs/modelo/diccionario-datos.md` (sección `redalimenta_dwh`).
Código: `dwh/` (migraciones, `almacen/`), operación: `python scripts/etl.py`.

## Procesos de negocio y granularidad

| Hecho | Granularidad (una fila por…) | Tipo | Medidas | Fuente |
| --- | --- | --- | --- | --- |
| `fact_donacion` | donación | Instantánea acumulada: el estado vigente se actualiza en cada carga | cantidad, horas_vida (publicación → vencimiento), conteo | catalog-geo |
| `fact_reserva` | reserva | Instantánea acumulada | conteo (por estado: gestionadas, completadas, expiradas…) | fulfillment |
| `fact_entrega` | entrega | Instantánea acumulada | cantidad entregada (la de la donación, D-05), horas publicación → entrega, con_incidencia | fulfillment |
| `fact_cambio_estado` | evento publicado por un servicio | Transaccional (no se modifica) | conteo; permite medir tiempos entre estados | historial de eventos (analytics) |

Las tres primeras guardan su clave natural (`origen_dato`, `id_*`) como dimensión degenerada; por eso la
carga es repetible (UPSERT) y se pueden unir entre sí (reserva → donación, entrega → reserva).
`origen_dato` separa la operación real (`REAL`) de los datos generados (`SINTETICO`).

## Dimensiones

| Dimensión | Clave | Atributos | Notas |
| --- | --- | --- | --- |
| `dim_tiempo` | `sk_tiempo` = AAAAMMDD | fecha, año, trimestre, mes, semana ISO, día, día de la semana, fin de semana | Precargada 2020–2030; fechas asignadas al día de Colombia; -1 = sin fecha |
| `dim_categoria` | `sk_categoria` | id natural, nombre | Tipo 1 (se sobrescribe) |
| `dim_ubicacion` | `sk_ubicacion` | departamento, ciudad, latitud y longitud representativas | Jerarquía departamento → ciudad; punto para el mapa de cobertura |
| `dim_usuario` | `sk_usuario` | origen, id natural, rol | **Sin datos personales** (Ley 1581): ni nombre, ni correo, ni teléfono |
| `dim_estado` | `sk_estado` | entidad, estado, es_final | Las listas de D-03 |

Todas tienen un miembro -1 ("desconocido") para que un hecho nunca quede sin dimensión; la regla de calidad
`dimensiones_resueltas` vigila que no se use.

## Matriz de bus

| Hecho \ Dimensión | Tiempo | Categoría | Ubicación | Usuario | Estado |
| --- | --- | --- | --- | --- | --- |
| fact_donacion | publicación, vencimiento | ✓ | ✓ | donante | ✓ |
| fact_reserva | reserva | ✓ (de su donación) | ✓ | donante, receptor | ✓ |
| fact_entrega | programada, entrega | ✓ | ✓ | donante, receptor | ✓ |
| fact_cambio_estado | evento | — | — | actor | anterior, nuevo |

## Indicadores del RF9 (una consulta cada uno)

Implementados en `dwh/almacen/indicadores.py`, todos filtrables por periodo y granularidad (día, mes, año),
departamento, ciudad, categoría y origen. La prueba `test_indicadores_iguales_a_consulta_manual` compara
cada cifra con una consulta directa al área de paso.

| Indicador | Consulta |
| --- | --- |
| Donaciones registradas | `count(*)` de `fact_donacion` por `sk_tiempo_publicacion` |
| Reservas gestionadas | `count(*)` de `fact_reserva` por `sk_tiempo_reserva` |
| Entregas finalizadas | `count(*)` de `fact_entrega` con estado COMPLETADA, por `sk_tiempo_entrega` |
| Volumen de alimentos distribuidos | `sum(cantidad)` de entregas COMPLETADAS **por unidad de medida** (no se suman kg con litros) |
| Proporción canceladas o vencidas | donaciones CANCELADA o VENCIDA / total de donaciones del periodo |
| Cobertura por región | por departamento y ciudad: donaciones, entregadas, perdidas, tasa de entrega y coordenadas |

Ejemplo (donaciones por mes en Antioquia, solo operación real):

```sql
SELECT date_trunc('month', t.fecha)::date AS mes, count(*) AS donaciones
FROM dw.fact_donacion f
JOIN dw.dim_tiempo t ON t.sk_tiempo = f.sk_tiempo_publicacion
JOIN dw.dim_ubicacion u ON u.sk_ubicacion = f.sk_ubicacion
WHERE u.departamento = 'Antioquia' AND f.origen_dato = 'REAL'
GROUP BY 1 ORDER BY 1;
```

## Cargas (S7-03 a S7-07)

| Carga | Qué hace | Cuándo |
| --- | --- | --- |
| Histórica | Copia fresca de identity, catalog-geo y fulfillment al área de paso (rol `dwh_lector`, transacciones de solo lectura) y UPSERT a la estrella (`almacen/sql/transformar.sql`) | Al arrancar y cada noche (CronJob `etl-historica`) |
| Continua | Eventos nuevos del historial de analytics (marca de agua por fecha de recepción) → `stg.evento` → `fact_cambio_estado` y estado vigente de los hechos (`transformar_eventos.sql`); un evento repetido no se duplica | Cada 10 min en Kubernetes, cada 5 min en Compose |
| Sintética | 50.000 donaciones con reservas y entregas coherentes (`almacen/sintetico.py`, semilla fija) | Con la carga completa inicial |

Cada carga corre en una sola transacción (si falla no deja nada a medias), queda en `etl.ejecucion`
(inicio, fin, estado, filas, error, intento), se reintenta hasta 3 veces con espera creciente y termina con
las pruebas de calidad (`etl.resultado_calidad`; informe: `python scripts/etl.py informe`).

## Datos sintéticos (S7-03)

Generados para que los indicadores tengan volumen; **no son operación real** y están marcados con
`origen_dato = 'SINTETICO'` (todo indicador puede excluirlos). Características:

- 50.000 donaciones entre enero de 2025 y hoy, con menos actividad los fines de semana y un pico (×4,5 que
  decae en unas seis semanas) tras el terremoto del 10 de agosto de 2026.
- 20 ciudades de 20 departamentos, ponderadas por población; donantes y receptores de la misma ciudad.
- Vida útil, unidades y cantidades por categoría (comidas preparadas en horas, enlatados en meses, agua sin
  vencimiento).
- Reglas de negocio respetadas: fechas en orden y nunca futuras, una sola reserva activa por donación,
  reservas que expiran o se cancelan y dan paso a una segunda, ENTREGADA solo con reserva y entrega
  COMPLETADAS, incidencias, entregas imposibles porque el alimento venció.
