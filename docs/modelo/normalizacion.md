# Revisión de normalización (S4-12)

Objetivo: cada tabla en tercera forma normal (3FN). Las columnas, tipos y restricciones exactas
están en `docs/modelo/diccionario-datos.md`, generado desde las bases.

## Criterios

- **1FN:** todos los atributos son atómicos (sin listas ni grupos repetidos) y cada tabla tiene clave primaria.
- **2FN:** 1FN y ningún atributo no clave depende de una parte de la clave. Todas las claves primarias son
  simples (`id_*`), así que 2FN se cumple siempre que haya 1FN.
- **3FN:** 2FN y ningún atributo no clave depende de otro atributo no clave (sin dependencias transitivas).

## Tabla por tabla

| Tabla | Dependencias funcionales (clave → atributos) | Forma normal | Justificación |
| --- | --- | --- | --- |
| `rol` | `id_rol → nombre_rol, descripcion`; `nombre_rol → id_rol` | 3FN (FNBC) | `nombre_rol` es clave candidata (UNIQUE); no hay otras dependencias. |
| `usuario` | `id_usuario → id_rol, nombre, correo_electronico, contrasena_hash, telefono, estado_cuenta, fecha_registro`; `lower(correo) → id_usuario` | 3FN (FNBC) | El nombre del rol no se repite aquí: se obtiene por `id_rol`. El estado de verificación tampoco se guarda en `usuario` (sería transitivo y se desactualizaría): se deriva de la verificación más reciente. |
| `verificacion_usuario` | `id_verificacion → id_usuario, id_administrador, estado_verificacion, fecha_solicitud, fecha_resolucion, observaciones` | 3FN | Un usuario puede tener varias verificaciones (historial tras un rechazo); por eso es tabla aparte y no un campo de `usuario`. |
| `registro_auditoria` | `id_auditoria → id_usuario, entidad_afectada, id_registro_afectado, accion_realizada, valor_anterior, valor_nuevo, fecha_operacion` | 3FN | Cada fila es un hecho inmutable. `valor_anterior`/`valor_nuevo` son texto atómico (el estado), no listas. |
| `categoria_alimento` | `id_categoria → nombre_categoria, descripcion`; `nombre_categoria → id_categoria` | 3FN (FNBC) | Catálogo independiente compartido por donaciones y necesidades. |
| `ubicacion_geografica` | `id_ubicacion → direccion_referencia, ciudad, departamento, coordenada_geografica` | 3FN (ver nota 1) | Se separa de donación y necesidad para no repetir la ubicación y para indexar el punto una sola vez (GIST). |
| `donacion` | `id_donacion → id_donante, id_categoria, id_ubicacion, nombre_alimento, descripcion, cantidad, unidad_medida, fecha_vencimiento, fecha_publicacion, condiciones_recogida, estado_donacion` | 3FN | El nombre de la categoría y la dirección no se repiten: se obtienen por clave foránea. |
| `necesidad_alimentaria` | `id_necesidad → id_receptor, id_categoria, id_ubicacion, descripcion, cantidad_requerida, unidad_medida, nivel_urgencia, fecha_limite, estado_necesidad` | 3FN | Igual que `donacion`. |
| `reserva` | `id_reserva → id_donacion, id_receptor, fecha_reserva, fecha_expiracion, estado_reserva` | 3FN | `fecha_expiracion` no se deriva solo de `fecha_reserva`: depende del plazo vigente al reservar (D-09 es configurable), por eso se guarda. |
| `entrega` | `id_entrega → id_reserva, fecha_programada, fecha_entrega, estado_entrega, observaciones`; `id_reserva → id_entrega` | 3FN (FNBC) | `id_reserva` es clave candidata (una entrega por reserva). |
| `confirmacion_entrega` | `id_confirmacion → id_entrega, id_usuario, fecha_confirmacion, estado_confirmacion, observaciones`; `(id_entrega, id_usuario) → id_confirmacion` | 3FN (FNBC) | La clave compuesta candidata garantiza una confirmación por usuario y entrega. |
| `notificacion` | `id_notificacion → id_usuario, tipo_notificacion, mensaje, fecha_creacion, fecha_lectura, estado_notificacion` | 3FN | `mensaje` se guarda redactado (no se recalcula) porque es lo que el usuario recibió en ese momento. |

## Notas y decisiones conscientes

1. **Ciudad y departamento en `ubicacion_geografica`.** Estrictamente, `ciudad → departamento` es una
   dependencia transitiva. Se deja así a propósito: el modelo del documento de los Sprints 2 y 3 define
   ambos atributos en la ubicación, una ciudad puede repetir nombre en dos departamentos, y el almacén de
   datos del Sprint 7 construye la dimensión geográfica (departamento → ciudad) a partir de estos valores.
   Llevarla a una tabla `ciudad` es el siguiente paso si el docente lo pide.
2. **Valores derivados que no se guardan:** la distancia y el puntaje de prioridad (D-08) se calculan en la
   consulta; el estado de verificación vigente de un usuario se deriva de su última verificación; el
   contador de no leídas se cuenta con el índice `(id_usuario, estado_notificacion)`.
3. **Estados como `ENUM` y no como tablas de catálogo (D-03):** son listas cerradas que la base debe hacer
   cumplir junto con sus transiciones (triggers); los roles y las categorías sí son tablas porque tienen
   descripción y pueden crecer.
4. **Referencias entre bases sin clave foránea (D-06):** `id_donante`, `id_receptor`, `id_donacion` e
   `id_usuario` apuntan a otra base. La integridad se comprueba con `python scripts/bd.py verificar`
   (conciliación entre bases) y, desde el Sprint 5, con los eventos y la API.
