# Diccionario de datos

Generado con `python scripts/bd.py diccionario` a partir del catálogo de PostgreSQL de cada base;
no se edita a mano. Las descripciones salen de los `COMMENT ON` de las migraciones.
La justificación de la normalización está en `docs/modelo/normalizacion.md`.

## Base `redalimenta_identity` (identity-service)

**Tipos enumerados (D-03)**

| Tipo | Valores |
| --- | --- |
| `estado_cuenta` | ACTIVA, DESACTIVADA |
| `estado_verificacion` | PENDIENTE, APROBADA, RECHAZADA |

### `rol`

Tipos de usuario y sus permisos: DONANTE, RECEPTOR, ADMINISTRADOR.

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_rol` | smallint | no | nextval('rol_id_rol_seq'::regclass) | Identificador del rol. |
| `nombre_rol` | character varying(30) | no |  | Nombre único del rol. |
| `descripcion` | character varying(200) | sí |  | Qué puede hacer el rol. |

Restricciones:

- **PK** `pk_rol`: `PRIMARY KEY (id_rol)`
- **UNIQUE** `uq_rol_nombre_rol`: `UNIQUE (nombre_rol)`

### `usuario`

Personas y organizaciones registradas (donantes, receptores, administradores).

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_usuario` | bigint | no | nextval('usuario_id_usuario_seq'::regclass) | Identificador del usuario. |
| `id_rol` | smallint | no |  | Rol del usuario. |
| `nombre` | character varying(120) | no |  | Nombre de la persona u organización. |
| `correo_electronico` | character varying(254) | no |  | Correo de inicio de sesión; único sin distinguir mayúsculas. |
| `contrasena_hash` | character varying(255) | no |  | Hash PBKDF2-SHA256 de la contraseña; nunca la contraseña en claro. |
| `telefono` | character varying(30) | sí |  | Teléfono de contacto (dato personal). |
| `estado_cuenta` | estado_cuenta | no | 'ACTIVA'::estado_cuenta | ACTIVA o DESACTIVADA; desactivar no borra la fila. |
| `fecha_registro` | timestamp with time zone | no | now() | Fecha de creación de la cuenta. |

Restricciones:

- **CHECK** `ck_usuario_correo_valido`: `CHECK (((correo_electronico)::text ~~ '%_@_%'::text))`
- **FK** `fk_usuario_id_rol_rol`: `FOREIGN KEY (id_rol) REFERENCES rol(id_rol)`
- **PK** `pk_usuario`: `PRIMARY KEY (id_usuario)`

Índices:

- `ix_usuario_id_rol`: `btree (id_rol)`
- `ux_usuario_correo`: `btree (lower((correo_electronico)::text))`

### `verificacion_usuario`

Procesos de verificación de identidad; solo un administrador los resuelve.

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_verificacion` | bigint | no | nextval('verificacion_usuario_id_verificacion_seq'::regclass) | Identificador. |
| `id_usuario` | bigint | no |  | Usuario que se verifica. |
| `id_administrador` | bigint | sí |  | Administrador que resolvió; NULL mientras está PENDIENTE. |
| `estado_verificacion` | estado_verificacion | no | 'PENDIENTE'::estado_verificacion | PENDIENTE, APROBADA o RECHAZADA. |
| `fecha_solicitud` | timestamp with time zone | no | now() | Cuándo se solicitó. |
| `fecha_resolucion` | timestamp with time zone | sí |  | Cuándo se resolvió; NULL mientras está PENDIENTE. |
| `observaciones` | text | sí |  | Motivo de la decisión. |

Restricciones:

- **CHECK** `ck_verificacion_usuario_resolucion_con_administrador`: `CHECK (((estado_verificacion = 'PENDIENTE'::estado_verificacion) OR (id_administrador IS NOT NULL)))`
- **CHECK** `ck_verificacion_usuario_resolucion_fechada`: `CHECK (((estado_verificacion = 'PENDIENTE'::estado_verificacion) = (fecha_resolucion IS NULL)))`
- **FK** `fk_verificacion_usuario_id_administrador_usuario`: `FOREIGN KEY (id_administrador) REFERENCES usuario(id_usuario)`
- **FK** `fk_verificacion_usuario_id_usuario_usuario`: `FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)`
- **PK** `pk_verificacion_usuario`: `PRIMARY KEY (id_verificacion)`

Índices:

- `ix_verificacion_usuario_id_usuario`: `btree (id_usuario)`
- `ux_verificacion_pendiente`: `btree (id_usuario) WHERE (estado_verificacion = 'PENDIENTE'::estado_verificacion)`

Triggers:

- `trg_verificacion_validar` → `fn_verificacion_validar()`

### `registro_auditoria`

Historial de operaciones y cambios de estado de todos los servicios (D-04). Solo inserción.

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_auditoria` | bigint | no | nextval('registro_auditoria_id_auditoria_seq'::regclass) | Identificador. |
| `id_usuario` | bigint | sí |  | Quién hizo la operación; NULL = sistema. |
| `entidad_afectada` | character varying(40) | no |  | Entidad: donacion, reserva, entrega... |
| `id_registro_afectado` | bigint | no |  | Identificador del registro afectado. |
| `accion_realizada` | character varying(60) | no |  | Acción o tipo de evento. |
| `valor_anterior` | text | sí |  | Estado o valor antes del cambio. |
| `valor_nuevo` | text | sí |  | Estado o valor después del cambio. |
| `fecha_operacion` | timestamp with time zone | no | now() | Cuándo ocurrió. |

Restricciones:

- **FK** `fk_registro_auditoria_id_usuario_usuario`: `FOREIGN KEY (id_usuario) REFERENCES usuario(id_usuario)`
- **PK** `pk_registro_auditoria`: `PRIMARY KEY (id_auditoria)`

Índices:

- `ix_auditoria_entidad`: `btree (entidad_afectada, id_registro_afectado)`
- `ix_registro_auditoria_id_usuario`: `btree (id_usuario)`

Triggers:

- `trg_auditoria_solo_insercion` → `fn_auditoria_solo_insercion()`

## Base `redalimenta_catalog` (catalog-geo-service)

**Tipos enumerados (D-03)**

| Tipo | Valores |
| --- | --- |
| `estado_donacion` | DISPONIBLE, RESERVADA, ENTREGADA, CANCELADA, VENCIDA |
| `estado_necesidad` | ABIERTA, CERRADA, CANCELADA |
| `nivel_urgencia` | BAJA, MEDIA, ALTA, CRITICA |

### `categoria_alimento`

Clasificación de los alimentos de donaciones y necesidades.

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_categoria` | smallint | no | nextval('categoria_alimento_id_categoria_seq'::regclass) | Identificador. |
| `nombre_categoria` | character varying(60) | no |  | Nombre único de la categoría. |
| `descripcion` | character varying(200) | sí |  | Qué alimentos incluye. |

Restricciones:

- **PK** `pk_categoria_alimento`: `PRIMARY KEY (id_categoria)`
- **UNIQUE** `uq_categoria_alimento_nombre_categoria`: `UNIQUE (nombre_categoria)`

### `ubicacion_geografica`

Puntos de recogida (donaciones) y de entrega (necesidades).

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_ubicacion` | bigint | no | nextval('ubicacion_geografica_id_ubicacion_seq'::regclass) | Identificador. |
| `direccion_referencia` | character varying(200) | sí |  | Dirección escrita como referencia; el punto manda. |
| `ciudad` | character varying(80) | no |  | Ciudad o municipio. |
| `departamento` | character varying(80) | no |  | Departamento de Colombia. |
| `coordenada_geografica` | geography(Point,4326) | no |  | Punto WGS84 (SRID 4326); distancias en metros. |

Restricciones:

- **PK** `pk_ubicacion_geografica`: `PRIMARY KEY (id_ubicacion)`

Índices:

- `ix_ubicacion_coordenada`: `gist (coordenada_geografica)`

### `donacion`

Alimentos ofrecidos por los donantes. Solo este servicio cambia estado_donacion (D-01).

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_donacion` | bigint | no | nextval('donacion_id_donacion_seq'::regclass) | Identificador. |
| `id_donante` | bigint | no |  | Usuario donante (identity-service; sin FK entre bases, D-06). |
| `id_categoria` | smallint | no |  | Categoría del alimento. |
| `id_ubicacion` | bigint | no |  | Punto de recogida. |
| `nombre_alimento` | character varying(120) | no |  | Qué se dona. |
| `descripcion` | text | sí |  | Detalle del alimento. |
| `cantidad` | numeric(12,2) | no |  | Cantidad ofrecida; mayor que cero. |
| `unidad_medida` | character varying(30) | no |  | kg, litros, unidades, porciones... |
| `fecha_vencimiento` | timestamp with time zone | sí |  | Hasta cuándo es apto; NULL si no aplica (p. ej. agua embotellada). |
| `fecha_publicacion` | timestamp with time zone | no | now() | Cuándo se publicó. |
| `condiciones_recogida` | text | sí |  | Horario, cadena de frío, acceso... |
| `estado_donacion` | estado_donacion | no | 'DISPONIBLE'::estado_donacion | DISPONIBLE, RESERVADA, ENTREGADA, CANCELADA o VENCIDA. |

Restricciones:

- **CHECK** `ck_donacion_cantidad_positiva`: `CHECK ((cantidad > (0)::numeric))`
- **CHECK** `ck_donacion_vence_despues_de_publicar`: `CHECK (((fecha_vencimiento IS NULL) OR (fecha_vencimiento > fecha_publicacion)))`
- **FK** `fk_donacion_id_categoria_categoria_alimento`: `FOREIGN KEY (id_categoria) REFERENCES categoria_alimento(id_categoria)`
- **FK** `fk_donacion_id_ubicacion_ubicacion_geografica`: `FOREIGN KEY (id_ubicacion) REFERENCES ubicacion_geografica(id_ubicacion)`
- **PK** `pk_donacion`: `PRIMARY KEY (id_donacion)`

Índices:

- `ix_donacion_estado_donacion`: `btree (estado_donacion)`
- `ix_donacion_id_categoria`: `btree (id_categoria)`
- `ix_donacion_id_donante`: `btree (id_donante)`
- `ix_donacion_id_ubicacion`: `btree (id_ubicacion)`

Triggers:

- `trg_donacion_validar` → `fn_donacion_validar()`

### `necesidad_alimentaria`

Lo que necesitan los receptores; alimenta la búsqueda y la prioridad (D-05).

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_necesidad` | bigint | no | nextval('necesidad_alimentaria_id_necesidad_seq'::regclass) | Identificador. |
| `id_receptor` | bigint | no |  | Usuario receptor (identity-service; sin FK entre bases, D-06). |
| `id_categoria` | smallint | no |  | Tipo de alimento requerido. |
| `id_ubicacion` | bigint | no |  | Dónde se atiende a la población. |
| `descripcion` | text | no |  | Qué se necesita y para quién. |
| `cantidad_requerida` | numeric(12,2) | no |  | Cantidad requerida; mayor que cero. |
| `unidad_medida` | character varying(30) | no |  | kg, litros, unidades, porciones... |
| `nivel_urgencia` | nivel_urgencia | no |  | BAJA, MEDIA, ALTA o CRITICA. |
| `fecha_limite` | timestamp with time zone | sí |  | Hasta cuándo se necesita. |
| `estado_necesidad` | estado_necesidad | no | 'ABIERTA'::estado_necesidad | ABIERTA, CERRADA o CANCELADA. |

Restricciones:

- **CHECK** `ck_necesidad_alimentaria_cantidad_positiva`: `CHECK ((cantidad_requerida > (0)::numeric))`
- **FK** `fk_necesidad_alimentaria_id_categoria_categoria_alimento`: `FOREIGN KEY (id_categoria) REFERENCES categoria_alimento(id_categoria)`
- **FK** `fk_necesidad_alimentaria_id_ubicacion_ubicacion_geografica`: `FOREIGN KEY (id_ubicacion) REFERENCES ubicacion_geografica(id_ubicacion)`
- **PK** `pk_necesidad_alimentaria`: `PRIMARY KEY (id_necesidad)`

Índices:

- `ix_necesidad_alimentaria_id_categoria`: `btree (id_categoria)`
- `ix_necesidad_alimentaria_id_receptor`: `btree (id_receptor)`
- `ix_necesidad_alimentaria_id_ubicacion`: `btree (id_ubicacion)`

Triggers:

- `trg_necesidad_validar` → `fn_necesidad_validar()`

## Base `redalimenta_fulfillment` (fulfillment-service)

**Tipos enumerados (D-03)**

| Tipo | Valores |
| --- | --- |
| `estado_confirmacion` | CONFIRMADA, CON_INCIDENCIA |
| `estado_entrega` | PROGRAMADA, COMPLETADA, CON_INCIDENCIA, CANCELADA |
| `estado_reserva` | PENDIENTE, CONFIRMADA, EXPIRADA, COMPLETADA, CANCELADA |

### `reserva`

Solicitudes de reserva; cubren la donación completa (D-05).

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_reserva` | bigint | no | nextval('reserva_id_reserva_seq'::regclass) | Identificador. |
| `id_donacion` | bigint | no |  | Donación reservada (catalog-geo-service; sin FK entre bases, D-06). |
| `id_receptor` | bigint | no |  | Usuario receptor (identity-service; sin FK entre bases, D-06). |
| `fecha_reserva` | timestamp with time zone | no | now() | Cuándo se reservó. |
| `fecha_expiracion` | timestamp with time zone | no |  | Plazo para que el donante confirme (D-09: 2 horas por defecto). |
| `estado_reserva` | estado_reserva | no | 'PENDIENTE'::estado_reserva | PENDIENTE, CONFIRMADA, EXPIRADA, COMPLETADA o CANCELADA. |

Restricciones:

- **CHECK** `ck_reserva_expira_despues_de_reservar`: `CHECK ((fecha_expiracion > fecha_reserva))`
- **PK** `pk_reserva`: `PRIMARY KEY (id_reserva)`

Índices:

- `ix_reserva_id_donacion`: `btree (id_donacion)`
- `ix_reserva_id_receptor`: `btree (id_receptor)`
- `ix_reserva_pendiente_expiracion`: `btree (fecha_expiracion) WHERE (estado_reserva = 'PENDIENTE'::estado_reserva)`
- `ux_reserva_activa`: `btree (id_donacion) WHERE (estado_reserva = ANY (ARRAY['PENDIENTE'::estado_reserva, 'CONFIRMADA'::estado_reserva]))`

Triggers:

- `trg_reserva_validar` → `fn_reserva_validar()`

### `entrega`

Entrega de una reserva confirmada; una por reserva.

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_entrega` | bigint | no | nextval('entrega_id_entrega_seq'::regclass) | Identificador. |
| `id_reserva` | bigint | no |  | Reserva que se entrega (una entrega por reserva). |
| `fecha_programada` | timestamp with time zone | sí |  | Cuándo se acordó entregar. |
| `fecha_entrega` | timestamp with time zone | sí |  | Cuándo se completó la entrega. |
| `estado_entrega` | estado_entrega | no | 'PROGRAMADA'::estado_entrega | PROGRAMADA, COMPLETADA, CON_INCIDENCIA o CANCELADA. |
| `observaciones` | text | sí |  | Notas o descripción de la incidencia. |

Restricciones:

- **CHECK** `ck_entrega_completada_fechada`: `CHECK (((estado_entrega <> 'COMPLETADA'::estado_entrega) OR (fecha_entrega IS NOT NULL)))`
- **FK** `fk_entrega_id_reserva_reserva`: `FOREIGN KEY (id_reserva) REFERENCES reserva(id_reserva)`
- **PK** `pk_entrega`: `PRIMARY KEY (id_entrega)`
- **UNIQUE** `uq_entrega_id_reserva`: `UNIQUE (id_reserva)`

Triggers:

- `trg_entrega_validar` → `fn_entrega_validar()`

### `confirmacion_entrega`

Confirmación bilateral: la donación queda ENTREGADA con la del donante y la del receptor.

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_confirmacion` | bigint | no | nextval('confirmacion_entrega_id_confirmacion_seq'::regclass) | Identificador. |
| `id_entrega` | bigint | no |  | Entrega que se confirma. |
| `id_usuario` | bigint | no |  | Donante o receptor que confirma (identity-service; sin FK entre bases, D-06). |
| `fecha_confirmacion` | timestamp with time zone | no | now() | Cuándo confirmó. |
| `estado_confirmacion` | estado_confirmacion | no |  | CONFIRMADA o CON_INCIDENCIA. |
| `observaciones` | text | sí |  | Comentario o detalle de la incidencia. |

Restricciones:

- **FK** `fk_confirmacion_entrega_id_entrega_entrega`: `FOREIGN KEY (id_entrega) REFERENCES entrega(id_entrega)`
- **PK** `pk_confirmacion_entrega`: `PRIMARY KEY (id_confirmacion)`
- **UNIQUE** `uq_confirmacion_entrega_id_entrega_id_usuario`: `UNIQUE (id_entrega, id_usuario)`

Índices:

- `ix_confirmacion_entrega_id_entrega`: `btree (id_entrega)`

## Base `redalimenta_notification` (notification-service)

**Tipos enumerados (D-03)**

| Tipo | Valores |
| --- | --- |
| `estado_notificacion` | NO_LEIDA, LEIDA, ARCHIVADA |

### `notificacion`

Avisos in-app generados por los eventos de los demás servicios.

| Columna | Tipo | Nulo | Por defecto | Descripción |
| --- | --- | --- | --- | --- |
| `id_notificacion` | bigint | no | nextval('notificacion_id_notificacion_seq'::regclass) | Identificador. |
| `id_usuario` | bigint | no |  | Destinatario (identity-service; sin FK entre bases, D-06). Obligatorio. |
| `tipo_notificacion` | character varying(60) | no |  | Evento que la originó: RESERVA_CREADA, ENTREGA_CONFIRMADA... |
| `mensaje` | text | no |  | Texto para el usuario. |
| `fecha_creacion` | timestamp with time zone | no | now() | Cuándo se generó. |
| `fecha_lectura` | timestamp with time zone | sí |  | Cuándo la leyó el usuario. |
| `estado_notificacion` | estado_notificacion | no | 'NO_LEIDA'::estado_notificacion | NO_LEIDA, LEIDA o ARCHIVADA. |

Restricciones:

- **CHECK** `ck_notificacion_leida_fechada`: `CHECK (((estado_notificacion <> 'LEIDA'::estado_notificacion) OR (fecha_lectura IS NOT NULL)))`
- **CHECK** `ck_notificacion_mensaje_no_vacio`: `CHECK ((length(TRIM(BOTH FROM mensaje)) > 0))`
- **PK** `pk_notificacion`: `PRIMARY KEY (id_notificacion)`

Índices:

- `ix_notificacion_usuario_estado`: `btree (id_usuario, estado_notificacion)`

Triggers:

- `trg_notificacion_validar` → `fn_notificacion_validar()`
