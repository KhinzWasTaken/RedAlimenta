# Datos semilla (S4-08)

Las cuatro bases usan identificadores fijos para que las referencias lógicas entre ellas (D-06) coincidan.
`python scripts/bd.py verificar` comprueba que todo cuadra. Contraseña de todos los usuarios: `demo123`.

## Usuarios (identity)

| id | Nombre | Correo | Rol | Ciudad | Verificación |
| --- | --- | --- | --- | --- | --- |
| 1 | Administración RedAlimenta | admin@redalimenta.co | ADMINISTRADOR | — | APROBADA |
| 2 | Supermercado La Cosecha | donante@redalimenta.co | DONANTE | Bogotá | APROBADA |
| 3 | Comedor Comunitario Esperanza | receptor@redalimenta.co | RECEPTOR | Bogotá | **PENDIENTE** (para la demo) |
| 4 | Restaurante El Fogón Paisa | donante.medellin@redalimenta.co | DONANTE | Medellín | APROBADA |
| 5 | Fundación Manos Unidas | receptor.medellin@redalimenta.co | RECEPTOR | Medellín | APROBADA |
| 6 | Banco de Alimentos del Valle | donante.cali@redalimenta.co | DONANTE | Cali | APROBADA |
| 7 | Albergue Temporal Siloé | receptor.cali@redalimenta.co | RECEPTOR | Cali | APROBADA |
| 8 | Panadería Don Julio | donante.nuevo@redalimenta.co | DONANTE | — | **PENDIENTE** |

## Donaciones (catalog) y reservas (fulfillment)

| Donación | Ciudad | Donante | Estado | Reserva |
| --- | --- | --- | --- | --- |
| 1–10 | Bogotá | 2 | DISPONIBLE (la 9, agua, sin fecha de vencimiento) | — |
| 11 Bandejas paisas | Medellín | 4 | RESERVADA | 1 · receptor 5 · PENDIENTE |
| 12 Arepas de maíz | Medellín | 4 | ENTREGADA | 3 · receptor 5 · COMPLETADA, entrega 2 con dos confirmaciones |
| 13 Fríjol cargamanto | Medellín | 4 | DISPONIBLE | 5 · receptor 5 · CANCELADA |
| 14 Leche deslactosada | Medellín | 4 | CANCELADA | — |
| 15 Mercados familiares | Cali | 6 | RESERVADA | 2 · receptor 7 · CONFIRMADA, entrega 1 PROGRAMADA |
| 16 Plátano y yuca | Cali | 6 | DISPONIBLE | 4 · receptor 7 · EXPIRADA |
| 17 Pollo despresado | Cali | 6 | DISPONIBLE | — |
| 18 Mango y guayaba | Cali | 6 | VENCIDA | — |

## Necesidades (catalog)

| id | Receptor | Ciudad | Categoría | Urgencia | Estado |
| --- | --- | --- | --- | --- | --- |
| 1 | 3 | Bogotá (Ciudad Bolívar) | Granos y enlatados | CRITICA | ABIERTA |
| 2 | 3 | Bogotá (Ciudad Bolívar) | Lácteos y huevos | ALTA | ABIERTA |
| 3 | 3 | Bogotá (Bosa) | Frutas y verduras | MEDIA | ABIERTA |
| 4 | 3 | Bogotá (Kennedy) | Panadería | BAJA | ABIERTA |
| 5 | 5 | Medellín (Manrique) | Comidas preparadas | ALTA | ABIERTA |
| 6 | 5 | Medellín (Moravia) | Granos y enlatados | MEDIA | ABIERTA |
| 7 | 7 | Cali (Siloé) | Carnes y proteínas | CRITICA | ABIERTA |
| 8 | 7 | Cali (Aguablanca) | Frutas y verduras | BAJA | ABIERTA |
| 9 | 7 | Cali (Siloé) | Panadería | MEDIA | CERRADA |

Las fechas (vencimientos, plazos de reserva, entregas) se calculan relativas al momento de sembrar,
para que la demo siempre tenga donaciones vigentes y por vencer.

## Notificaciones (notification)

Ocho avisos para los usuarios 2, 4, 5, 6 y 7, coherentes con las reservas de arriba, en los estados
NO_LEIDA, LEIDA y ARCHIVADA.
