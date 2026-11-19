# Decisiones D-01 a D-10 (aprobadas el 5 de noviembre de 2026)

Texto completo en `docs/contexto/plan-sprints-4-8.md`, sección 2. Son reglas fijas.
La segunda columna dice cómo las aplica el **prototipo de clase**, que es una sola
aplicación (no microservicios) con módulos separados y SQLite.

| ID | Decisión | Cómo la aplica el prototipo |
| --- | --- | --- |
| D-01 | Solo catalog-geo escribe `estado_donacion`; fulfillment le pide cada transición y catalog valida que sea legal. | `catalogo/servicio.py::transicionar_donacion` es la única función que cambia `estado_donacion`. El módulo `reservas` la llama (es el "endpoint interno") y recibe un error si la transición es ilegal. |
| D-02 | Índice único parcial en `reserva(id_donacion)` cuando el estado es PENDIENTE o CONFIRMADA; se inserta la reserva primero y luego se pide a catalog pasar la donación a RESERVADA; si catalog rechaza, se cancela la reserva. | Índice `ux_reserva_activa` (SQLite admite índices parciales). La API responde 409 a la segunda solicitud. Si catalog rechaza (p. ej. donación vencida) la reserva queda CANCELADA y la API responde 409. |
| D-03 | Cada lista de estados es una enumeración del esquema; "Aprobado" se unifica a APROBADA. | Ver `docs/modelo/estados.md`; columnas con restricción CHECK. |
| D-04 | Cada cambio de estado publica un evento; identity lo guarda en `registro_auditoria` (solo inserción). | Bus de eventos en proceso (`core/eventos.py`). El módulo de identidad guarda cada evento en `registro_auditoria`; disparadores de SQLite bloquean UPDATE y DELETE sobre esa tabla. El módulo de notificaciones consume el mismo evento. |
| D-05 | La reserva cubre la donación completa; la necesidad solo alimenta búsqueda y prioridad. | La reserva no tiene cantidad; no se descuenta nada de la necesidad. |
| D-06 | Sin clave foránea física entre servicios; el JWT lleva `id_usuario`, rol y estado de verificación con vigencia corta. | Los módulos no tienen claves foráneas entre sí (`id_donante`, `id_receptor`, `id_usuario` son enteros simples). El JWT (60 min) lleva `sub`, `rol` y `verificacion`; los permisos se deciden con el token. `POST /api/auth/refresh` emite un token nuevo cuando el administrador cambia la verificación. |
| D-07 | El receptor envía lat/lon o elige una de sus necesidades abiertas como punto de referencia. | `GET /api/donaciones/disponibles?lat=&lon=` o `?id_necesidad=`. |
| D-08 | Puntaje = 0,40 urgencia + 0,35 cercanía + 0,25 proximidad del vencimiento, normalizados 0–1; pesos en configuración. | Ver `catalogo/busqueda.py`. Urgencia: mayor nivel de las necesidades abiertas del receptor en la categoría de la donación (BAJA 0,25, MEDIA 0,5, ALTA 0,75, CRITICA 1; 0 si no hay). Cercanía: `1 − min(d / radio, 1)`. Vencimiento: `1 − min(horas_restantes / 168, 1)`. Distancia con Haversine. |
| D-09 | Plazo de confirmación de reserva: 2 horas. Aviso de "por vencer": 24 horas antes. Configurables. | Variables `REDALIMENTA_PLAZO_RESERVA_HORAS` y `REDALIMENTA_AVISO_VENCER_HORAS`. Un planificador interno corre las tareas cada 60 s; el botón de demo "forzar expiración" adelanta el plazo y ejecuta la tarea. |
| D-10 | Dejar `Usuario` como está (sin `tipo_participante`). | Sin cambios. |

## Cómo se aplican desde el Sprint 4 (proyecto final, `services/`)

| ID | Aplicación en las bases PostgreSQL |
| --- | --- |
| D-01 | `catalogo.repositorio.transicionar_donacion` es el único punto que cambia `estado_donacion`, y el trigger `trg_donacion_validar` rechaza en la base cualquier transición ilegal. |
| D-02 | Índice único parcial `ux_reserva_activa` en `redalimenta_fulfillment.reserva`; prueba con 20 conexiones simultáneas. La compensación (cancelar si catalog rechaza) se implementa con la API en el Sprint 5. |
| D-03 | Tipos `ENUM` de PostgreSQL por cada lista de estados, más triggers que validan las transiciones. |
| D-04 | `registro_auditoria` con trigger que bloquea UPDATE/DELETE y REVOKE de esos permisos al rol `identity_app`. |
| D-05 | `reserva` sin cantidad; la necesidad solo entra en la búsqueda y el puntaje. |
| D-06 | Una base por servicio y sin claves foráneas entre bases; la coherencia se comprueba con `scripts/bd.py verificar`. |
| D-07 | `buscar_donaciones(lat, lon)` o `buscar_donaciones(id_necesidad=…)` con una necesidad ABIERTA del receptor. |
| D-08 | Puntaje calculado en SQL con ST_Distance; pesos por variables de entorno (`catalogo/config.py`). |
| D-09 | `PLAZO_RESERVA_HORAS` (2) y `AVISO_POR_VENCER_HORAS` (24) en `cumplimiento/config.py`. |
| D-10 | Sin cambios en `usuario`. |

## D-11 · Solicitudes de alimentos (agregada el 19 de noviembre de 2026)

**Problema:** las necesidades solo las veía su receptor; un donante no tenía forma de saber qué se pedía ni de
responder a una petición concreta.

**Decisión:** cada necesidad ABIERTA y vigente es una **solicitud** visible para los donantes
(`GET /api/necesidades/abiertas`, sin el receptor ni su dirección escrita). Un donante puede publicar una donación
**para** una solicitud (`donacion.id_necesidad`). Mientras esa necesidad siga ABIERTA, la donación queda apartada:
solo la ve en la búsqueda y solo la reserva su receptor (fulfillment lo comprueba antes de insertar y catalog lo
valida en la transición, D-01). Si el receptor cierra o cancela la necesidad, la donación queda disponible para
todos. El receptor recibe un aviso al publicarse la oferta.

**Compatibilidad con D-05:** la reserva sigue cubriendo la donación completa y no se descuenta cantidad de la
necesidad; el receptor la cierra cuando queda cubierta.

## D-12 · Chat entre donante y receptor (agregada el 19 de noviembre de 2026)

**Problema:** donante y receptor no tenían cómo pactar la hora y el lugar de entrega ni resolver dudas dentro de
la aplicación.

**Decisión:** una conversación por (donación, receptor) en notification-service (tablas `conversacion` y
`mensaje`). Se abre sola por eventos cuando hay contraparte: el receptor reserva una donación publicada
(RESERVA_CREADA) o el donante ofrece una donación para la solicitud de un receptor (DONACION_CREADA con
`id_receptor`, D-11). Se cierra cuando la reserva de ese receptor se cancela o expira, o cuando la donación se
entrega, se cancela o vence; cerrada queda de solo lectura y se reabre si el mismo receptor vuelve a reservar.

**Reglas:** solo escriben y leen los dos participantes (el administrador no lee los chats); los mensajes son de
solo inserción (trigger + permisos), de 1 a 1.000 caracteres, para que lo pactado quede como se dijo. Los mensajes
**no se publican como eventos**: no llegan a la auditoría ni al almacén, para no copiar conversaciones privadas.
El frontend consulta cada 3 segundos (sin WebSocket), suficiente para coordinar una entrega.
