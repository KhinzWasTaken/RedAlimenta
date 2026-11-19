# Catálogo de eventos (S5-01)

Transporte: RabbitMQ, exchange `redalimenta.eventos` de tipo *topic* y duradero. La clave de enrutamiento es
el tipo del evento. Cada evento usa el sobre común de `sobre.schema.json` (plan, sección 4).
Los servicios publican **después** de confirmar su transacción; los consumidores confirman el mensaje
(*ack*) solo si lo procesaron bien, y si fallan el mensaje vuelve a la cola.

## Consumidores

| Cola | Servicio | Claves | Qué hace |
| --- | --- | --- | --- |
| `identity.auditoria` | identity | `#` | Guarda cada evento de otros servicios en `registro_auditoria` (D-04). Los suyos los audita en su propia transacción. |
| `notification.bandeja` | notification | `#` | Crea la notificación in-app de cada destinatario (`notificaciones/consumidor.py::destinatarios`). |
| `analytics.historial` | analytics | `#` | Guarda el evento en `historial_evento`, sin duplicar por `id_evento` (S5-15). |

## Eventos

En negrita, los tres que nombra el documento de los Sprints 2 y 3; el resto completa el catálogo propuesto en el plan.
Todos los consumen auditoría y analytics; la columna "Notifica a" dice quién recibe aviso in-app.

| Tipo | Publica | Entidad · transición | `datos` | Notifica a |
| --- | --- | --- | --- | --- |
| USUARIO_REGISTRADO | identity | usuario · ∅ → ACTIVA | rol | el usuario |
| USUARIO_DESACTIVADO | identity | usuario · ACTIVA → DESACTIVADA | — | — |
| VERIFICACION_SOLICITADA | identity | verificacion · RECHAZADA → PENDIENTE | id_usuario | — |
| USUARIO_VERIFICADO | identity | verificacion · PENDIENTE → APROBADA/RECHAZADA | id_usuario, observaciones | el usuario |
| DONACION_CREADA | catalog-geo | donacion · ∅ → DISPONIBLE | id_donante, nombre_alimento, id_categoria, ciudad, departamento, cantidad, unidad_medida; si responde a una solicitud (D-11): id_necesidad, id_receptor, necesidad | donante; y el receptor de la solicitud |
| DONACION_ACTUALIZADA | catalog-geo | donacion · sin cambio de estado | id_donante, nombre_alimento, campos | — |
| DONACION_RESERVADA | catalog-geo | donacion · DISPONIBLE → RESERVADA | id_donante, nombre_alimento, id_receptor, id_reserva, fecha_expiracion | donante |
| DONACION_LIBERADA | catalog-geo | donacion · RESERVADA → DISPONIBLE | id_donante, nombre_alimento, motivo | donante |
| DONACION_ENTREGADA | catalog-geo | donacion · RESERVADA → ENTREGADA | id_donante, nombre_alimento, id_receptor | donante |
| DONACION_CANCELADA | catalog-geo | donacion · DISPONIBLE → CANCELADA | id_donante, nombre_alimento | donante |
| DONACION_VENCIDA | catalog-geo | donacion · DISPONIBLE/RESERVADA → VENCIDA | id_donante, nombre_alimento | donante |
| **DONACION_POR_VENCER** | fulfillment | donacion · sin cambio (aviso 24 h antes, D-09) | id_donante, id_receptor (si hay reserva), nombre_alimento, fecha_vencimiento | donante y receptor |
| NECESIDAD_CREADA / AJUSTADA / CERRADA / CANCELADA | catalog-geo | necesidad · ∅ → ABIERTA → CERRADA/CANCELADA | id_receptor, descripcion | receptor |
| **RESERVA_CREADA** | fulfillment | reserva · ∅ → PENDIENTE | id_reserva, id_donacion, id_donante, id_receptor, nombre_alimento, fecha_expiracion | receptor |
| RESERVA_CONFIRMADA | fulfillment | reserva · PENDIENTE → CONFIRMADA | contexto de la reserva | receptor |
| RESERVA_EXPIRADA | fulfillment | reserva · PENDIENTE → EXPIRADA | contexto de la reserva | donante y receptor |
| RESERVA_CANCELADA | fulfillment | reserva · PENDIENTE/CONFIRMADA → CANCELADA | contexto, por, motivo (si fue compensación D-02) | donante y receptor |
| RESERVA_COMPLETADA | fulfillment | reserva · CONFIRMADA → COMPLETADA | contexto de la reserva | receptor |
| ENTREGA_PROGRAMADA | fulfillment | entrega · ∅ → PROGRAMADA | id_entrega + contexto | donante y receptor |
| **ENTREGA_CONFIRMADA** | fulfillment | entrega · sin cambio (una confirmación) | confirmacion, por, observaciones + contexto | la otra parte |
| ENTREGA_COMPLETADA | fulfillment | entrega · PROGRAMADA → COMPLETADA | id_entrega + contexto | donante y receptor |
| ENTREGA_CON_INCIDENCIA | fulfillment | entrega · PROGRAMADA → CON_INCIDENCIA | observaciones + contexto | donante y receptor |
| ENTREGA_CANCELADA | fulfillment | entrega · PROGRAMADA/CON_INCIDENCIA → CANCELADA | id_entrega + contexto | donante y receptor |

"Contexto de la reserva" = `id_reserva, id_donacion, id_donante, id_receptor, nombre_alimento`.

## Llamadas síncronas entre servicios

La única dependencia síncrona es fulfillment → catalog-geo, por la API interna (`/internal/*`, cabecera
`X-Token-Interno`, contrato en `openapi/catalog-geo-service.interno.yaml`):

| Ruta | Para qué |
| --- | --- |
| `POST /internal/donaciones/{id}/transiciones` | D-01: pedir un cambio de estado; 409 si es ilegal |
| `GET /internal/donaciones?ids=&id_donante=&estado=` | Leer los datos de las donaciones de una reserva (dueño, alimento) |
| `POST /internal/tareas/vencer` | RF8: que catalog marque VENCIDA lo que pasó su fecha |
| `GET /internal/donaciones-por-vencer?horas=` | RF8: candidatas al aviso DONACION_POR_VENCER |

El plan hablaba de una sola llamada directa (la transición); las lecturas se agregaron porque fulfillment
necesita saber quién es el donante para autorizar la confirmación y la entrega sin copiar ese dato en su base (D-06).
