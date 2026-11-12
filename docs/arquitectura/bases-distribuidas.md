# Bases de datos distribuidas en RedAlimenta (S7-08)

## 1. Qué datos viven en qué servicio

| Base | Servicio | Datos | Tipo de carga |
| --- | --- | --- | --- |
| `redalimenta_identity` | identity | usuarios, roles, verificaciones, auditoría | OLTP; auditoría solo inserción |
| `redalimenta_catalog` | catalog-geo | categorías, ubicaciones (PostGIS), donaciones, necesidades | OLTP con consultas geoespaciales |
| `redalimenta_fulfillment` | fulfillment | reservas, entregas, confirmaciones | OLTP con alta concurrencia (reservas) |
| `redalimenta_notification` | notification | notificaciones | Escritura por eventos, lectura por usuario |
| `redalimenta_analytics` | analytics | historial de eventos | Solo inserción, alimenta el almacén |
| `redalimenta_dwh` | almacén (ETL) | estrella, área de paso, control de cargas | OLAP: lecturas grandes, cargas por lotes |

Es una **base de datos distribuida por fragmentación vertical funcional**: cada servicio es dueño de un
subconjunto de entidades, con su propio esquema, rol y migraciones. No hay claves foráneas entre bases
(D-06); las referencias son identificadores y su coherencia se vigila con `scripts/bd.py verificar` y la
tarea de conciliación de fulfillment.

Hoy las seis bases están en un mismo servidor PostgreSQL: el aislamiento es **lógico** (bases y roles
separados; un servicio no puede conectarse a la base de otro). Pasar a servidores distintos solo exige
cambiar las URL de conexión, porque ningún servicio hace consultas entre bases.

## 2. Consistencia entre servicios

- **Dentro de un servicio:** transacciones ACID de PostgreSQL. Ejemplos: el índice único parcial que
  garantiza una sola reserva activa (D-02), los triggers que validan transiciones.
- **Entre servicios: consistencia eventual.** No hay transacciones distribuidas (sin 2PC). Se usan:
  1. **Una llamada síncrona con compensación** donde la regla lo exige: reservar inserta la reserva, pide a
     catalog el cambio de estado y, si falla, cancela la reserva (patrón saga de dos pasos).
  2. **Eventos** para todo lo demás (auditoría, notificaciones, historial): llegan con retraso de
     milisegundos a segundos, y si un consumidor está caído, cuando vuelva.
  3. **Idempotencia** (`evento_procesado`, `ON CONFLICT`) para que reintentos y reentregas no dupliquen.
  4. **Conciliación** periódica que detecta y corrige diferencias (donación RESERVADA sin reserva activa).
- **Almacén:** consistencia eventual de minutos (carga continua) a un día (carga histórica). Es aceptable
  porque sirve indicadores, no operaciones.

Según el teorema CAP, ante una partición entre servicios RedAlimenta elige **disponibilidad** para lo que
no es crítico (los avisos se retrasan) y **consistencia** para la reserva (si catalog no responde, reservar
falla con 503 en lugar de arriesgar dos receptores con la misma donación).

## 3. Opciones de réplica y partición evaluadas

| Opción | Qué resuelve | Costo | Decisión |
| --- | --- | --- | --- |
| **Réplica de lectura** (streaming replication) del almacén y de catalog | Separar consultas pesadas (indicadores, búsquedas) de las escrituras; alta disponibilidad con promoción manual | Retraso de réplica (lecturas ligeramente viejas); un servidor más | **Adoptar primero para el almacén** cuando el tablero (Sprint 8) compita con las cargas |
| **Réplica síncrona** de fulfillment | No perder reservas confirmadas si cae el servidor | Más latencia en cada reserva | Adoptar en producción real; no necesaria en el prototipo |
| **Partición por departamento** (fragmentación horizontal) de donaciones y reservas | Escalar la operación por región; datos cerca de cada territorio | Consultas nacionales tocan todas las particiones; la reserva sigue siendo por donación (no cruza particiones) | **Particionar el almacén por año** (`PARTITION BY RANGE` sobre la fecha) antes que la operación por departamento |
| **Partición declarativa por fecha** en `fact_donacion`, `fact_cambio_estado` e `historial_evento` | Cargas y borrados por periodo rápidos; consultas por rango de fechas | Mantenimiento de particiones nuevas | Adoptar cuando se pase del millón de filas |
| **Sharding** de toda la base | Volúmenes muy grandes | Complejidad alta (enrutamiento, consultas globales) | No se justifica para el volumen esperado |

## 4. Lo que adopta RedAlimenta

1. **Una base por servicio** (fragmentación vertical) y almacén separado: ya implementado.
2. **Consistencia eventual con compensación, idempotencia y conciliación**: ya implementado.
3. **Siguiente paso de escala:** réplica de lectura para el almacén y el catálogo, y partición por rango de
   fecha en los hechos y el historial de eventos.
4. **Si la operación crece por regiones** (por ejemplo, varias emergencias simultáneas), particionar
   donaciones y reservas por departamento: cada reserva toca una sola donación, así que la regla D-02 se
   sigue cumpliendo dentro de cada partición sin transacciones distribuidas.
