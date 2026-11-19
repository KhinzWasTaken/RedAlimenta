# Estados y transiciones (D-03)

Fuente: plan de Sprints 4–8, sección 2 (marcados con \* vienen del documento de Sprints 2 y 3).
Cada lista se guarda como enumeración con restricción CHECK en el esquema.
El prototipo solo permite las transiciones de esta tabla; cada una publica un evento
que genera una fila de auditoría y una notificación in-app.

| Entidad | Estados |
| --- | --- |
| Cuenta de usuario | ACTIVA, DESACTIVADA |
| Verificación\* | PENDIENTE, APROBADA, RECHAZADA |
| Donación\* | DISPONIBLE, RESERVADA, ENTREGADA, CANCELADA, VENCIDA |
| Necesidad | ABIERTA, CERRADA, CANCELADA |
| Reserva\* | PENDIENTE, CONFIRMADA, EXPIRADA, COMPLETADA, CANCELADA |
| Entrega | PROGRAMADA, COMPLETADA, CON_INCIDENCIA, CANCELADA |
| Confirmación de entrega | CONFIRMADA, CON_INCIDENCIA |
| Notificación | NO_LEIDA, LEIDA, ARCHIVADA |
| Conversación (D-12) | ABIERTA, CERRADA |
| Nivel de urgencia | BAJA, MEDIA, ALTA, CRITICA |

## Transiciones permitidas

### Verificación
- PENDIENTE → APROBADA | RECHAZADA (solo administrador). Una verificación resuelta no vuelve a PENDIENTE.

### Donación (solo el módulo de catálogo la escribe, D-01)
- DISPONIBLE → RESERVADA (al crearse una reserva)
- DISPONIBLE → CANCELADA (el donante la retira)
- DISPONIBLE → VENCIDA (tarea automática: pasó `fecha_vencimiento`)
- RESERVADA → DISPONIBLE (reserva expirada o cancelada y donación vigente)
- RESERVADA → VENCIDA (reserva liberada con la donación ya vencida)
- RESERVADA → ENTREGADA (donante y receptor confirmaron la entrega)
- ENTREGADA, CANCELADA y VENCIDA son finales.

### Reserva
- PENDIENTE → CONFIRMADA (el donante acepta)
- PENDIENTE → EXPIRADA (pasó `fecha_expiracion`, D-09)
- PENDIENTE → CANCELADA (receptor o donante; o compensación si catálogo rechaza, D-02)
- CONFIRMADA → COMPLETADA (entrega completada)
- CONFIRMADA → CANCELADA (receptor o donante)

### Entrega
- PROGRAMADA → COMPLETADA (dos confirmaciones CONFIRMADA)
- PROGRAMADA → CON_INCIDENCIA (una confirmación reporta incidencia)
- PROGRAMADA | CON_INCIDENCIA → CANCELADA (se cancela la reserva)

### Necesidad
- ABIERTA → CERRADA | CANCELADA (solo su receptor)

### Notificación
- NO_LEIDA → LEIDA | ARCHIVADA; LEIDA → ARCHIVADA

### Conversación (D-12)
- Nace ABIERTA con RESERVA_CREADA o con DONACION_CREADA ofrecida para una solicitud (D-11).
- ABIERTA → CERRADA con RESERVA_CANCELADA o RESERVA_EXPIRADA de ese receptor (salvo si nació de una oferta) y con
  DONACION_ENTREGADA, DONACION_CANCELADA o DONACION_VENCIDA (todas las de la donación).
- CERRADA → ABIERTA si el mismo receptor vuelve a reservar. Cerrada solo se lee; los mensajes nunca cambian.
