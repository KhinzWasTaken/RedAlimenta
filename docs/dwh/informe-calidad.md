# Informe de calidad del almacén

Ejecución 3 (eventos) · 2026-11-12T19:27:10+00:00

| Regla | Qué comprueba | Filas con problema | Resultado |
| --- | --- | --- | --- |
| `sin_duplicados_donacion` | Una sola fila por donación (origen_dato, id_donacion) | 0 | ✅ aprobada |
| `sin_duplicados_reserva` | Una sola fila por reserva | 0 | ✅ aprobada |
| `sin_duplicados_entrega` | Una sola fila por entrega | 0 | ✅ aprobada |
| `sin_cantidades_no_positivas` | Ninguna cantidad menor o igual a cero en donaciones ni entregas | 0 | ✅ aprobada |
| `reservas_con_donacion` | Toda reserva apunta a una donación del almacén (sin claves huérfanas) | 0 | ✅ aprobada |
| `entregas_con_reserva` | Toda entrega apunta a una reserva del almacén (sin claves huérfanas) | 0 | ✅ aprobada |
| `dimensiones_resueltas` | Hechos sin categoría, ubicación o participante desconocidos (-1) | 0 | ✅ aprobada |
| `una_reserva_activa` | Como máximo una reserva activa por donación (D-02) | 0 | ✅ aprobada |
| `fechas_en_orden` | publicación ≤ reserva ≤ entrega y entrega ≤ vencimiento | 0 | ✅ aprobada |
| `entregada_con_dos_confirmaciones` | Donación ENTREGADA ⇔ entrega COMPLETADA y reserva COMPLETADA | 0 | ✅ aprobada |
| `conteos_origen_destino` | Las filas REAL del área de paso llegaron todas a los hechos | 0 | ✅ aprobada |
| `eventos_transformados` | Todo evento del área de paso quedó en fact_cambio_estado | 0 | ✅ aprobada |

Volumen cargado:

- dw.fact_entrega: 32786
- dw.fact_reserva: 40068
- dw.fact_donacion: 50019
- stg.evento (nuevos): 0
- dw.fact_cambio_estado: 18
