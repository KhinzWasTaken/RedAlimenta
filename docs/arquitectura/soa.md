# Arquitectura orientada a servicios de RedAlimenta (S6-10)

RedAlimenta son cinco servicios, cada uno con su propia base de datos, más un gateway, un broker de eventos
y un servidor PostgreSQL con PostGIS. Este documento explica qué llamadas son síncronas y cuáles por
eventos, por qué, y qué pasa cuando cae cada pieza. Contratos: `docs/contratos/`; despliegue:
`infra/docker-compose.yml` e `infra/k8s/`.

```
                         ┌──────────── gateway (nginx) ─────────────┐
   navegador ──HTTPS──▶  │ frontend compilado + reparto de /api     │   /internal → 404
                         └───┬────────┬──────────┬────────┬────────┬┘
                             │        │          │        │        │
                       identity  catalog-geo  fulfillment notification analytics
                         │  ▲        │  ▲  ◀──HTTP interno── │        ▲        ▲
                         │  │        │  │    (D-01)          │        │        │
                         ▼  │        ▼  │                    ▼        │        │
                  redalimenta_ │ redalimenta_ │       redalimenta_   │        │
                  identity     │ catalog      │       fulfillment    │        │
                               │              │                      │        │
          ┌────────────────────┴──────────────┴───── RabbitMQ (exchange topic redalimenta.eventos) ──┐
          │  publican: identity, catalog-geo, fulfillment                                             │
          │  consumen: identity (auditoría), notification (bandeja), analytics (historial)            │
          └───────────────────────────────────────────────────────────────────────────────────────────┘
```

## 1. Quién es dueño de qué

| Servicio | Base | Es dueño de | Requerimientos |
| --- | --- | --- | --- |
| identity | `redalimenta_identity` | usuarios, roles, verificación, **auditoría** | RF1, RF10 |
| catalog-geo | `redalimenta_catalog` | categorías, ubicaciones, **estado de la donación** (D-01), necesidades | RF2–RF4 |
| fulfillment | `redalimenta_fulfillment` | reservas, entregas, confirmaciones, tareas automáticas | RF5, RF6, RF8 |
| notification | `redalimenta_notification` | notificaciones in-app | RF7 |
| analytics | `redalimenta_analytics` | historial de eventos; almacén de datos en el Sprint 7 | RF9, RF10 |

Ningún servicio lee ni escribe la base de otro: cada uno tiene su propio rol de PostgreSQL, que solo puede
conectarse a su base (D-06). Las referencias entre bases son identificadores sin clave foránea y su
coherencia la vigila la conciliación (`scripts/bd.py verificar` y la tarea `conciliar` de fulfillment).

## 2. Llamadas síncronas (HTTP)

| Origen → destino | Para qué | Por qué síncrona |
| --- | --- | --- |
| navegador → gateway → servicio | Toda la API pública (`/api/...`) | El usuario espera la respuesta |
| fulfillment → catalog-geo `POST /internal/donaciones/{id}/transiciones` | Pedir RESERVADA, DISPONIBLE, ENTREGADA o VENCIDA | D-01: solo catalog cambia el estado y la reserva necesita saber **ya** si se aceptó para responder 201 o 409 |
| fulfillment → catalog-geo `GET /internal/donaciones` | Saber el dueño y el estado de la donación | Autorizar al donante (confirmar, entregar) sin copiar ese dato en fulfillment |
| fulfillment → catalog-geo `POST /internal/tareas/vencer`, `GET /internal/donaciones-por-vencer` | Tareas automáticas (RF8) | Las dispara el CronJob de fulfillment; catalog aplica el cambio |

Reglas de las llamadas internas: cabecera `X-Token-Interno` (secreto compartido), tiempo límite de 3 s,
lecturas con hasta 2 reintentos, transiciones **sin** reintento (no son idempotentes) y el gateway nunca
publica `/internal`.

## 3. Comunicación por eventos (asíncrona)

Todo cambio de estado se publica como evento con el sobre común (`docs/contratos/eventos/`). Los servicios
publican **después** de confirmar su transacción; los consumidores confirman el mensaje solo si lo
procesaron, y registran el `id_evento` en la misma transacción para no repetir efectos si el broker lo
entrega dos veces (S6-05).

Por qué eventos aquí: auditoría, notificaciones e historial no deben frenar ni hacer fallar la operación
del usuario. Si notification está caído, la reserva igual se hace y el aviso llega cuando vuelva.

## 4. Consistencia: el caso de la reserva (D-02)

1. fulfillment inserta la reserva; el índice único parcial decide quién gana (los demás reciben 409),
   aunque haya varias réplicas.
2. Confirma la transacción y pide a catalog pasar la donación a RESERVADA.
3. Si catalog rechaza o no responde, fulfillment **compensa**: cancela la reserva y responde 409 o 503.
4. Si el proceso muere entre el paso 2 y el 3, la conciliación encuentra la diferencia y la corrige.

## 5. Qué pasa si cae cada pieza

| Cae | Efecto para el usuario | Qué protege al sistema | Comprobado con |
| --- | --- | --- | --- |
| gateway | No hay acceso desde afuera | Los servicios siguen sanos; Kubernetes lo reinicia (liveness) | — |
| identity | No se puede iniciar sesión ni verificar; los tokens ya emitidos siguen sirviendo hasta que venzan (D-06) | Los demás servicios validan el JWT sin llamar a identity; la auditoría espera en la cola `identity.auditoria` | `test_token_de_otro_servicio_es_valido_aqui` |
| catalog-geo | No se puede publicar, buscar ni reservar | Reservar responde **503 en menos de 1 s** y no deja reservas huérfanas; con dos réplicas, una sola caída no se nota | `scripts/resiliencia.py`; réplica eliminada con 186/186 respuestas correctas |
| fulfillment | No se puede reservar ni confirmar entregas | Dos réplicas; las reservas a medias las corrige la conciliación | 20 reservas contra 2 réplicas: una 201 y 19 con 409 |
| notification | Los avisos se retrasan | Los eventos esperan en `notification.bandeja` y se procesan al volver, sin duplicados | `test_evento_repetido_no_duplica_notificaciones` |
| analytics | El historial se retrasa | Los eventos esperan en `analytics.historial`; inserción idempotente por `id_evento` | `test_guarda_sin_duplicar_y_consulta` |
| RabbitMQ | La operación sigue, pero sus eventos pueden perderse si el broker no vuelve en ~1,5 s | Mensajes y colas duraderos; 3 reintentos al publicar; los consumidores se reconectan solos | Riesgo aceptado (ver §6) |
| PostgreSQL | Todo el sistema deja de operar | `/salud` falla y Kubernetes saca los pods de servicio (readiness) sin reiniciarlos (liveness = `/vivo`) | — |

## 6. Decisiones y límites conocidos

- **Sin bandeja de salida transaccional (outbox):** un evento se publica tras el commit y se reintenta 3
  veces. Si RabbitMQ está caído más tiempo, ese evento se pierde para auditoría y notificaciones (los datos
  del negocio quedan bien y la conciliación corrige estados). Un outbox por servicio es la mejora natural.
- **Tareas automáticas:** en Kubernetes corren como CronJob (`concurrencyPolicy: Forbid`) y no dentro de
  las réplicas. Aun si coincidieran dos ejecuciones, cada efecto es una sola sentencia
  (`UPDATE … RETURNING`, `INSERT … ON CONFLICT`): se comprobó ejecutando las tareas en dos réplicas a la vez
  y cada reserva expiró una sola vez.
- **Trazabilidad entre servicios (S6-09):** el gateway asigna `X-Correlation-Id`; cada servicio lo escribe
  en sus registros, lo reenvía a catalog y lo guarda en los eventos, así una reserva se sigue en el gateway,
  fulfillment, catalog, auditoría, notificaciones e historial con el mismo identificador.
- **Un solo servidor PostgreSQL** con cinco bases: aislamiento lógico (bases y roles separados), no físico.
  El Sprint 7 (bases de datos distribuidas) discute réplicas de lectura y partición por departamento.
