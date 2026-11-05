# Entidades (Sprint 3) y módulo del prototipo que las posee

Nombres de tablas y columnas como en el modelo del documento de Sprints 2 y 3
(`docs/contexto/sprint-2-y-3.docx`).

| Entidad | Tabla | Módulo del prototipo | Atributos |
| --- | --- | --- | --- |
| Rol | `rol` | identidad | id_rol, nombre_rol, descripcion |
| Usuario | `usuario` | identidad | id_usuario, id_rol, nombre, correo_electronico, contrasena_hash, telefono, estado_cuenta, fecha_registro |
| Verificación de usuario | `verificacion_usuario` | identidad | id_verificacion, id_usuario, id_administrador, estado_verificacion, fecha_solicitud, fecha_resolucion, observaciones |
| Registro de auditoría | `registro_auditoria` | identidad | id_auditoria, id_usuario, entidad_afectada, id_registro_afectado, accion_realizada, valor_anterior, valor_nuevo, fecha_operacion |
| Categoría de alimento | `categoria_alimento` | catalogo | id_categoria, nombre_categoria, descripcion |
| Ubicación geográfica | `ubicacion_geografica` | catalogo | id_ubicacion, direccion_referencia, ciudad, departamento, latitud, longitud |
| Donación | `donacion` | catalogo | id_donacion, id_donante, id_categoria, id_ubicacion, nombre_alimento, descripcion, cantidad, unidad_medida, fecha_vencimiento, fecha_publicacion, condiciones_recogida, estado_donacion |
| Necesidad alimentaria | `necesidad_alimentaria` | catalogo | id_necesidad, id_receptor, id_categoria, id_ubicacion, descripcion, cantidad_requerida, unidad_medida, nivel_urgencia, fecha_limite, estado_necesidad |
| Reserva | `reserva` | reservas | id_reserva, id_donacion, id_receptor, fecha_reserva, fecha_expiracion, estado_reserva |
| Entrega | `entrega` | reservas | id_entrega, id_reserva, fecha_programada, fecha_entrega, estado_entrega, observaciones |
| Confirmación de entrega | `confirmacion_entrega` | reservas | id_confirmacion, id_entrega, id_usuario, fecha_confirmacion, estado_confirmacion, observaciones |
| Notificación | `notificacion` | notificaciones | id_notificacion, id_usuario, tipo_notificacion, mensaje, fecha_creacion, fecha_lectura, estado_notificacion |

## Diferencias del prototipo frente al modelo (por usar SQLite)

- `coordenada_geografica` (PostGIS) se guarda como dos columnas `latitud` y `longitud`;
  la distancia se calcula con la fórmula de Haversine en Python.
- `contraseña_hash` se llama `contrasena_hash` (sin ñ en el identificador).
- Restricciones: correo único; cantidad > 0; índice único parcial de reserva activa (D-02);
  una entrega por reserva; una confirmación por usuario y entrega;
  `registro_auditoria` solo admite INSERT (disparadores).
- Siguiendo D-06 no hay claves foráneas entre módulos, solo dentro de cada módulo.
