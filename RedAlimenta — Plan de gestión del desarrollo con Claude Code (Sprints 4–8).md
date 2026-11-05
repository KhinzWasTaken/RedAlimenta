# RedAlimenta — Plan de gestión del desarrollo con Claude Code (Sprints 4–8)

Nov 5, 2026 · @KhinZ

## 1. Resumen

RedAlimenta ya tiene análisis y modelo de datos completos (Sprints 0–3). Faltan cinco sprints que convierten ese modelo en base de datos, cinco microservicios con frontend, contenedores en Kubernetes, un almacén analítico y un tablero. Este plan define cómo repartir y ejecutar ese trabajo con Claude Code, partiendo solo de lo que dice el documento de los Sprints 2 y 3. El método es exprés: lotes grandes, tres personas en paralelo y pocas barreras, porque es una entrega universitaria.

**Lo que ya existe:** 4 actores (donante, receptor, administrador, sistema), 10 requerimientos funcionales, 12 entidades, 5 servicios (identity, catalog-geo, fulfillment, notification, analytics), el ER y el modelo relacional.

**Lo que falta**, según la tabla de sprints del documento:

| Sprint | Tema | Resultado esperado |
| --- | --- | --- |
| 4 | Base transaccional | DDL, DBMS, DML, CRUD y OLTP |
| 5 | Aplicación | Backend, framework, API REST y frontend |
| 6 | Arquitectura distribuida | SOA, microservicios, Docker y Kubernetes |
| 7 | Datos analíticos | BD distribuidas, ETL/ELT y Data Warehouse |
| 8 | Analítica y presentación | Indicadores, dashboard y documentación (el texto de la tabla está cortado en el documento) |

**Decisión de fondo:** desde el Sprint 4 cada servicio tiene su propia base de datos y su propio código, aunque todavía corran en una sola máquina. Así el Sprint 6 es empaquetar y orquestar, no reescribir un monolito. Los sprints siguen cubriendo los temas del curso en el mismo orden.

## 2. Decisiones que el modelo deja abiertas

Antes de programar hay diez puntos que el documento deja sin definir o asigna a dos servicios a la vez. Cada uno lleva su decisión, ya aprobada; como cambian código y esquema, Claude las trata como reglas fijas.

**Estado:** D-01 a D-10 aprobadas el 5 de noviembre de 2026; D-10 se aprueba dejando el modelo como está. Siguen abiertos solo el stack (sección 3), las fechas de cada sprint y el contenido del Sprint 8.

| ID | Tema | Qué dice o falta en el documento | Decisión aprobada |
| --- | --- | --- | --- |
| D-01 | Dueño del estado de la donación | La donación vive en catalog-geo-service, pero fulfillment-service debe marcarla Reservada, Disponible o Vencida (RF5, RF8). | Solo catalog-geo escribe `estado_donacion`. fulfillment le pide cada transición mediante un endpoint interno y catalog valida que sea legal. |
| D-02 | Reserva concurrente | "Solo una reserva activa por donación", pero la reserva y la donación están en bases distintas. | Índice único parcial en la tabla `reserva` sobre `id_donacion` cuando el estado es PENDIENTE o CONFIRMADA. La reserva se inserta primero (gana quien llega antes) y después se pide a catalog pasar la donación a RESERVADA; si catalog rechaza, se cancela la reserva. |
| D-03 | Estados sin lista cerrada | Solo están definidos los de donación, reserva y verificación. Faltan cuenta, necesidad, entrega, confirmación y notificación. | Definir cada lista como enumeración en el esquema (ver tabla de estados abajo). Unificar "Aprobado" a APROBADA para que concuerde con "Pendiente" y "Rechazada". |
| D-04 | Auditoría en dos servicios | El Registro de Auditoría está en identity-service (RF10), pero analytics-service también "guarda eventos de auditoría". | Cada servicio publica un evento por cambio de estado. identity-service lo guarda en `registro_auditoria` (solo inserción). analytics-service recibe el mismo evento para historial y reportes. Se revocan UPDATE y DELETE sobre esa tabla. |
| D-05 | Reserva total o parcial | La reserva no tiene cantidad, y necesidad y donación no se enlazan. | La reserva cubre la donación completa. La necesidad solo alimenta la búsqueda y la prioridad; no se descuenta cantidad. |
| D-06 | Referencias entre servicios | `id_donante`, `id_receptor` e `id_usuario` apuntan a Usuario, que está en otro servicio. | Sin clave foránea física entre bases. El token JWT lleva `id_usuario`, rol y estado de verificación con vigencia corta; cada servicio confía en el token. |
| D-07 | Punto de búsqueda | La búsqueda usa coordenadas, pero el usuario no tiene ubicación. | El receptor envía lat/lon, o elige una de sus necesidades abiertas como punto de referencia. |
| D-08 | Fórmula de prioridad | "Combinación de urgencia, cercanía y vencimiento", sin pesos. | Puntaje = 0,40 urgencia + 0,35 cercanía + 0,25 proximidad del vencimiento, cada término normalizado entre 0 y 1. Pesos en configuración. |
| D-09 | Plazos automáticos | "Fecha de expiración de la reserva" y "donación por vencer" no tienen duración. | Plazo de confirmación de reserva: 2 horas. Aviso de "por vencer": 24 horas antes. Ambos configurables. |
| D-10 | Tipo de participante | El Sprint 1 distingue empresa, restaurante, fundación o persona natural, pero Usuario solo tiene `nombre` y `id_rol`. | Dejar el modelo como está. Si el docente lo pide, agregar un campo `tipo_participante` a Usuario. |

**Estados propuestos para D-03** (los marcados con \* ya están en el documento):

| Entidad | Estados |
| --- | --- |
| Cuenta de usuario | ACTIVA, DESACTIVADA |
| Verificación\* | PENDIENTE, APROBADA, RECHAZADA |
| Donación\* | DISPONIBLE, RESERVADA, ENTREGADA, CANCELADA, VENCIDA |
| Necesidad | ABIERTA, CERRADA, CANCELADA |
| Reserva\* | PENDIENTE, CONFIRMADA, EXPIRADA, COMPLETADA, CANCELADA |
| Entrega | PROGRAMADA, COMPLETADA, CON\_INCIDENCIA, CANCELADA |
| Confirmación de entrega | CONFIRMADA, CON\_INCIDENCIA |
| Notificación | NO\_LEIDA, LEIDA, ARCHIVADA |
| Nivel de urgencia | BAJA, MEDIA, ALTA, CRITICA |

## 3. Arquitectura y stack propuestos

La arquitectura sale del documento: cinco servicios, cada uno con su base de datos, que se hablan por eventos y por una única llamada directa (fulfillment pide a catalog cambiar el estado de una donación, D-01). El documento solo fija PostGIS, JWT/OAuth2, Docker y Kubernetes; el resto de la tabla es propuesta y debe confirmarse con el docente antes del Sprint 4.

&#91;embedded content: arquitectura · 5 servicios, 5 bases, 1 broker\]

Los usuarios entran por el gateway (que llega en el Sprint 6); cada servicio escribe solo en su base y publica sus cambios al broker. La llamada de fulfillment a catalog es la única directa entre servicios.

| Capa | Propuesta | Por qué |
| --- | --- | --- |
| Base de datos | PostgreSQL con PostGIS, una base por servicio | PostGIS lo exige el modelo; una base por servicio evita acoplamientos y hace real el Sprint 6. |
| Backend | Python con FastAPI, SQLAlchemy y GeoAlchemy2, migraciones con Alembic | Genera el OpenAPI a partir del código y comparte lenguaje con el ETL del Sprint 7. Alternativa si el curso lo exige: Java con Spring Boot. |
| Autenticación | JWT firmado por identity-service; los demás servicios lo validan | Cumple "JWT/OAuth2" del documento sin una llamada a identity en cada petición. |
| Mensajería | RabbitMQ | Eventos del documento (RESERVA\_CREADA, ENTREGA\_CONFIRMADA, DONACION\_POR\_VENCER) con colas por consumidor. |
| Tareas programadas | Planificador interno en desarrollo; CronJob de Kubernetes desde el Sprint 6 | Con varias réplicas un planificador interno duplicaría las ejecuciones. |
| Frontend | React con Vite y Leaflet sobre OpenStreetMap, diseñado primero para celular | El sistema se usará en emergencias desde el teléfono; OpenStreetMap no pide clave. |
| Contenedores | Docker, Docker Compose y Kubernetes local (kind o minikube) | Lo pide el Sprint 6. |
| Pruebas | pytest con PostgreSQL y PostGIS reales en contenedor | Las consultas geoespaciales y la concurrencia no se pueden probar con una base simulada. |
| Almacén de datos | PostgreSQL separado, carga con SQL y Python | Sprint 7; mantiene una sola tecnología de base de datos. |

## 4. Repositorio y fuentes de verdad

Un solo repositorio (monorepo) con una carpeta `docs/` que manda sobre el código: si el código y `docs/` discrepan, se corrige el código o se acuerda el cambio entre las tres personas para cambiar `docs/`. Tener el contrato escrito antes del código permite que tres personas (y sus sesiones de Claude Code) trabajen servicios distintos sin pisarse.

```
redalimenta/
  CLAUDE.md                  contexto general y reglas que Claude Code lee siempre
  docs/
    contexto/                documento de Sprints 0-3 y diagramas
    modelo/                  entidades, relaciones, estados.md, reglas-negocio.md
    decisiones/              una nota por decisión (D-01, D-02...)
    contratos/
      openapi/               un .yaml por servicio
      eventos/               catálogo y esquemas JSON de eventos
    lotes/                   un archivo por lote y servicio
  services/
    identity-service/        CLAUDE.md, app/, migrations/, tests/, Dockerfile
    catalog-geo-service/
    fulfillment-service/
    notification-service/
    analytics-service/
  frontend/
  infra/                     docker-compose.yml, manifiestos k8s, scripts
  dwh/                       Sprint 7: modelo dimensional y ETL
```

Cada servicio tiene su propio `CLAUDE.md` con lo que únicamente él necesita: sus entidades, sus estados, sus endpoints, sus eventos y cómo ejecutar sus pruebas. Así una sesión sobre fulfillment no carga el contexto de los otros cuatro servicios.

**Catálogo de eventos.** Tres salen del documento (RESERVA\_CREADA, ENTREGA\_CONFIRMADA, DONACION\_POR\_VENCER); el resto es propuesto. Todos viajan con un sobre común: `id_evento`, `tipo`, `version`, `fecha`, `id_actor`, `entidad`, `id_entidad`, `estado_anterior`, `estado_nuevo` y `datos`.

| Evento | Lo publica | Lo consumen |
| --- | --- | --- |
| USUARIO\_VERIFICADO | identity | notification, analytics |
| DONACION\_CREADA | catalog-geo | analytics |
| DONACION\_CANCELADA | catalog-geo | notification, analytics |
| DONACION\_VENCIDA | catalog-geo | notification, analytics |
| DONACION\_POR\_VENCER | fulfillment | notification |
| RESERVA\_CREADA | fulfillment | notification, analytics |
| RESERVA\_CONFIRMADA | fulfillment | notification, analytics |
| RESERVA\_EXPIRADA | fulfillment | notification, analytics |
| ENTREGA\_CONFIRMADA | fulfillment | notification, analytics |
| Todos los anteriores | cada servicio | identity (auditoría), analytics |

## 5. Método exprés de trabajo con Claude Code

Se construye por lotes grandes: un lote es todo lo que un servicio (o el frontend) debe entregar en un sprint, y lo hace una sesión larga de Claude Code mientras las otras dos personas hacen lo mismo en sus servicios. Se revisa una vez por lote, no por cada pieza. La prioridad es que el flujo completo (donar, buscar, reservar, entregar) funcione cuanto antes y mejorarlo después.

**Cómo se ejecuta un lote**

1. La persona abre Claude Code en la carpeta del servicio y pega el prompt de lote (sección 10) con el sprint y el servicio.
2. Claude lee los `CLAUDE.md`, las decisiones de la sección 2 y los contratos, y dice en cinco líneas en qué orden lo va a construir. No espera aprobación, salvo que encuentre una contradicción con el modelo.
3. Claude construye todo de corrido: esquema, lógica, API, eventos y pruebas. Ejecuta las pruebas y corrige hasta que pasen, sin pedir permiso por cada archivo o comando dentro de la carpeta del servicio, y hace un commit al terminar cada parte grande.
4. Claude entrega un reporte corto: qué quedó listo, qué quedó pendiente o dudoso y qué supuestos tomó.
5. La persona levanta el servicio, corre el recorrido de humo y mira solo los archivos críticos (lista de la sección 8). Si todo pasa, fusiona a la rama principal; si no, devuelve el fallo a Claude.

**Las únicas barreras**

1. **Contratos mínimos primero (Lote 0).** La lista de endpoints y eventos que cruzan de un servicio a otro. Claude la redacta desde el documento, las tres personas la leen una vez y queda congelada. Todo lo interno de un servicio queda libre.
2. **Las decisiones D-01 a D-10 y los estados de la sección 2 son reglas fijas.** Claude no las cambia; si cree que hay un error, lo dice en el reporte.
3. **Pruebas obligatorias solo en lo crítico:** concurrencia de reservas, transiciones de estado, permisos por rol y dueño, y el flujo completo. Lo demás lo prueba Claude como le parezca, sin exigir cobertura.
4. **Sin secretos en el repositorio.**
5. **Un commit por parte grande terminada**, para volver atrás si un lote sale mal.

**Orden de lotes**

| Lote | Sprint | Qué contiene | Filas de la sección 6 | Quién |
| --- | --- | --- | --- | --- |
| L0 Fundación | 4 | Repositorio, `docs/`, Compose con bases y broker, contratos mínimos, plantilla de servicio | S4-01, S4-02, S5-01, S5-02 | Santiago; los otros dos leen los contratos |
| L1 Datos | 4 | Por servicio: DDL, migraciones, semillas, consultas y prueba de concurrencia | S4-03 a S4-12 | Cada dueño, en paralelo |
| L2 Servicios | 5 | Por servicio: lógica, API y eventos completos, y el recorrido de humo | S5-03 a S5-15 y S5-21 | Cada dueño, en paralelo |
| L3 Frontend | 5 | Todas las pantallas de los cuatro actores, usables desde celular | S5-16 a S5-20 | Carlos y Kevin, cada uno sus pantallas |
| L4 Contenedores y Kubernetes | 6 | Dockerfiles, Compose completo, gateway, resiliencia y manifiestos | S6-01 a S6-10 | Santiago |
| L5 Almacén de datos | 7 | Modelo en estrella, ETL, datos sintéticos y calidad | S7-01 a S7-08 | Kevin |
| L6 Analítica y cierre | 8 | Indicadores, tablero, auditoría, seguridad, matriz de trazabilidad y documentación | S8-01 a S8-09 | Carlos |

Si el calendario aprieta, L1 y L2 se hacen en la misma sesión por servicio: el Sprint 4 se entrega con el DDL y las consultas ya hechos y Claude sigue con la API sin parar.

**Qué se sacrifica a cambio de velocidad:** la aprobación del plan y la revisión por cada pieza, y la cobertura amplia de pruebas. Se compensa con el recorrido de humo antes de cada fusión, las pruebas críticas y los commits frecuentes.

## 6. Plan por sprint

Cada sprint tiene un entregable y una tabla de alcance. En el método exprés la tabla no es una cola de tarjetas sino la lista de un lote: Claude construye de corrido todas las filas de su servicio y la persona comprueba al final que cada criterio se cumple. Las fechas las fija el calendario académico, por eso aquí solo se ordena el trabajo. Si un sprint no alcanza, se recorta por la parte baja de la tabla, nunca por las pruebas críticas.

### Sprint 4 — Base transaccional

**Entregable:** cuatro bases PostgreSQL (identity, catalog-geo, fulfillment, notification) con DDL versionado, datos semilla, consultas CRUD probadas y una prueba de concurrencia de reservas. La base analítica de analytics-service se crea en el Sprint 7.

| ID | Alcance | Servicio | RF | Criterio de aceptación |
| --- | --- | --- | --- | --- |
| S4-01 | Entorno de base de datos con Docker Compose (PostgreSQL con PostGIS, cuatro bases separadas) | infra | — | `docker compose up` deja las cuatro bases creadas y accesibles; la extensión PostGIS está activa en catalog. |
| S4-02 | Estados y enumeraciones aprobados (D-03) | docs | — | `docs/modelo/estados.md` aprobado por las tres personas; cada lista queda como tipo ENUM o restricción CHECK. |
| S4-03 | DDL de identity: rol, usuario, verificación, auditoría | identity | RF1, RF10 | Correo único; claves foráneas y estados válidos; el rol de la aplicación no puede hacer UPDATE ni DELETE sobre `registro_auditoria` (prueba lo demuestra). |
| S4-04 | DDL de catalog-geo: categoría, ubicación, donación, necesidad | catalog-geo | RF2, RF3 | Ubicación como punto geográfico (SRID 4326) con índice espacial; cantidad mayor que cero; vencimiento posterior a la publicación. |
| S4-05 | DDL de fulfillment: reserva, entrega, confirmación | fulfillment | RF5, RF6 | Índice único parcial de reserva activa (D-02); una entrega por reserva; máximo una confirmación por usuario y entrega. |
| S4-06 | DDL de notification | notification | RF7 | Índice por usuario y estado; no se puede insertar una notificación sin usuario. |
| S4-07 | Migraciones versionadas | todos | — | Un comando aplica todas las migraciones desde cero y otro las revierte; el resultado coincide con el modelo relacional del documento. |
| S4-08 | Datos semilla | todos | — | Roles, categorías, usuarios de cada rol, y donaciones, necesidades y reservas en al menos tres ciudades colombianas. |
| S4-09 | Consultas de identity: crear, consultar, actualizar, desactivar usuario; resolver verificación | identity | RF1 | Cada consulta tiene prueba; desactivar no borra la fila; una verificación resuelta no vuelve a PENDIENTE. |
| S4-10 | Consultas de catalog: CRUD y búsqueda por distancia con filtros y puntaje de prioridad | catalog-geo | RF2–RF4 | Resultados ordenados por distancia en metros; filtros por categoría, cantidad y vencimiento; el puntaje sigue D-08 y se verifica con un caso calculado a mano. |
| S4-11 | Transacciones de fulfillment: reservar, confirmar, expirar, vencer | fulfillment | RF5, RF8 | Con 20 conexiones simultáneas reservando la misma donación, exactamente una reserva queda activa; la expiración en lote libera solo las vencidas. |
| S4-12 | Diccionario de datos y revisión de normalización | docs | — | Cada tabla y columna descritas; cada tabla con su forma normal justificada (objetivo: 3FN). |

### Sprint 5 — Aplicación

**Entregable:** los cinco servicios con API REST documentada, el frontend web usable desde celular y el flujo completo funcionando en una sola máquina: donar, buscar, reservar, confirmar y entregar. Es el sprint más grande; si el calendario lo permite, se parte en 5A (contratos y backend) y 5B (frontend e integración).

| ID | Alcance | Servicio | RF | Criterio de aceptación |
| --- | --- | --- | --- | --- |
| S5-01 | Contratos OpenAPI y esquemas de eventos aprobados | docs | todos | Un `.yaml` por servicio y el catálogo de eventos; las tres personas los aprueban antes de implementar. |
| S5-02 | Plantilla base de servicio y mensajería (RabbitMQ en Compose) | todos | — | Configuración por variables de entorno, ruta de salud, errores con formato único y publicador de eventos con una implementación real. Se copia a los cinco servicios. |
| S5-03 | Registro, inicio de sesión y JWT con rol y estado de verificación | identity | RF1 | Contraseña guardada con hash; el token vence; una ruta de administrador responde 403 a un donante. |
| S5-04 | Perfil: consultar, actualizar datos permitidos, desactivar cuenta | identity | RF1 | Un usuario solo ve y edita su perfil; un administrador ve todos. |
| S5-05 | Verificación por el administrador y registro de auditoría | identity | RF1, RF10 | Solo un administrador cambia el estado; cada cambio genera un registro con usuario, valor anterior y nuevo; el consumidor de eventos guarda los de otros servicios. |
| S5-06 | Donaciones: crear, consultar, modificar, cancelar | catalog-geo | RF2 | Solo usuarios verificados con rol donante publican; cancelar cambia el estado y no borra; no se modifica una donación reservada. |
| S5-07 | Necesidades: crear, consultar, ajustar, cerrar | catalog-geo | RF3 | Un receptor solo modifica las suyas. |
| S5-08 | Búsqueda geoespacial con priorización | catalog-geo | RF4 | Devuelve distancia y puntaje; excluye no disponibles y vencidas; respuesta lista para pintar en un mapa. |
| S5-09 | Endpoint interno de transición de estado de donación (D-01) | catalog-geo | RF5, RF8 | Solo acepta llamadas de otros servicios; rechaza transiciones ilegales como VENCIDA a DISPONIBLE. |
| S5-10 | Reservar donación con control de concurrencia (D-02) | fulfillment | RF5 | Dos solicitudes simultáneas: una responde 201 y la otra 409; si catalog rechaza, la reserva queda cancelada. |
| S5-11 | Confirmar y cancelar reserva | fulfillment | RF5 | Solo el donante confirma; cancelar devuelve la donación a DISPONIBLE. |
| S5-12 | Entrega y confirmación bilateral | fulfillment | RF6 | La donación pasa a ENTREGADA solo cuando donante y receptor confirmaron; una incidencia queda registrada. |
| S5-13 | Tareas programadas: vencer donaciones, expirar reservas, avisar por vencer | fulfillment | RF8 | Ejecutar la tarea dos veces seguidas no duplica efectos ni eventos; cada acción publica su evento. |
| S5-14 | Bandeja de notificaciones y consumo de eventos | notification | RF7 | Cada evento del catálogo crea la notificación del destinatario correcto; marcar como leída y archivar. |
| S5-15 | Historial de eventos y consulta de trazabilidad | analytics | RF10 | Guarda cada evento sin permitir modificarlo; consulta por entidad y por usuario. |
| S5-16 | Frontend base: inicio de sesión, rutas por rol, diseño para celular | frontend | RF1 | Un usuario sin sesión no ve pantallas protegidas; la interfaz es usable en pantalla de 360 px. |
| S5-17 | Frontend donante: publicar y gestionar donaciones | frontend | RF2 | Formulario con ubicación en mapa y validación de fecha y cantidad. |
| S5-18 | Frontend receptor: necesidades, mapa de búsqueda y reserva | frontend | RF3–RF5 | Resultados ordenados por distancia y prioridad; reservar muestra el plazo de confirmación. |
| S5-19 | Frontend: confirmaciones de entrega y bandeja de notificaciones | frontend | RF6, RF7 | Donante y receptor confirman desde su lista; el contador de no leídas se actualiza. |
| S5-20 | Frontend administrador: verificación de cuentas y categorías | frontend | RF1 | Aprobar o rechazar con observación. |
| S5-21 | Prueba de extremo a extremo del flujo principal | todos | RF2–RF7 | Un script recorre donar, buscar, reservar, confirmar y entregar, y comprueba estados y notificaciones. |

### Sprint 6 — Arquitectura distribuida

**Entregable:** los cinco servicios y el frontend empaquetados en contenedores, desplegados en un clúster local de Kubernetes tras una única puerta de entrada, con el flujo principal funcionando y una prueba de reserva concurrente contra dos réplicas.

| ID | Alcance | Servicio | RF | Criterio de aceptación |
| --- | --- | --- | --- | --- |
| S6-01 | Dockerfile por servicio y frontend | todos | — | Imagen que arranca sin usuario administrador, con ruta de salud y sin secretos dentro. |
| S6-02 | Docker Compose completo | infra | — | Un solo comando levanta servicios, bases, broker y frontend, y pasa la prueba extremo a extremo. |
| S6-03 | Puerta de entrada (gateway) | infra | RF1 | Una sola dirección pública; las rutas internas de servicio a servicio no quedan expuestas. |
| S6-04 | Resiliencia entre servicios | fulfillment, catalog-geo | RF5 | Tiempo límite y reintentos limitados en las llamadas; si catalog está caído, reservar responde un error claro y no deja reservas huérfanas. |
| S6-05 | Eventos idempotentes | notification, analytics, identity | RF7, RF10 | Entregar dos veces el mismo `id_evento` no crea dos notificaciones ni dos registros. |
| S6-06 | Manifiestos de Kubernetes | infra | — | Deployment y Service por servicio, Ingress, ConfigMap y Secret; todo se aplica en un clúster local (kind o minikube). |
| S6-07 | Tareas programadas como CronJob | fulfillment | RF8 | Con dos réplicas activas, cada vencimiento y expiración se procesa una sola vez. |
| S6-08 | Sondas de salud y dos réplicas de catalog y fulfillment | infra | RF5 | Al borrar un pod, el servicio sigue respondiendo; la prueba de 20 reservas simultáneas deja una sola activa. |
| S6-09 | Registro con identificador de correlación | todos | RF10 | Una operación se sigue a través de los servicios con un mismo identificador. |
| S6-10 | Documento de arquitectura SOA | docs | — | Qué llamadas son síncronas y cuáles por eventos, por qué, y qué pasa si cada servicio cae. |

### Sprint 7 — Datos analíticos

**Entregable:** un almacén de datos (Data Warehouse) en PostgreSQL con modelo en estrella, alimentado por un proceso ETL/ELT repetible, con pruebas de calidad y un documento sobre bases de datos distribuidas aplicado a RedAlimenta.

| ID | Alcance | Servicio | RF | Criterio de aceptación |
| --- | --- | --- | --- | --- |
| S7-01 | Diseño dimensional | dwh | RF9 | Hechos de donación, reserva y entrega con su granularidad escrita; dimensiones de tiempo, categoría, ubicación (departamento y ciudad), usuario y estado; cada indicador del RF9 se puede calcular con una consulta. |
| S7-02 | DDL del almacén y área de paso (staging) | dwh | RF9 | Base separada de las transaccionales; claves sustitutas; migraciones versionadas. |
| S7-03 | Generador de datos sintéticos | dwh | RF9 | Al menos 50.000 donaciones con reservas y entregas coherentes entre sí y distribuidas en el tiempo y el territorio; marcados como sintéticos en el informe. |
| S7-04 | Carga histórica desde las bases transaccionales (solo lectura) | dwh | RF9 | Conteos origen y destino coinciden; la carga se puede repetir sin duplicar filas. |
| S7-05 | Carga continua desde eventos | analytics | RF9, RF10 | Cada evento llega crudo a staging y se transforma con SQL a hechos; un evento repetido no duplica. |
| S7-06 | Pruebas de calidad de datos | dwh | RF9 | Sin claves huérfanas, sin duplicados, sin cantidades negativas; el informe de calidad se genera en cada carga. |
| S7-07 | Programación de la carga | infra | RF8 | CronJob con registro de la última ejecución y reintento tras fallo. |
| S7-08 | Documento de bases de datos distribuidas | docs | — | Qué datos viven en qué servicio, consistencia eventual entre ellos, opciones de réplica de lectura y partición por departamento, y la que RedAlimenta adopta. |

### Sprint 8 — Analítica y presentación

**Entregable:** tablero del administrador sobre el almacén de datos, trazabilidad consultable, matriz que enlaza cada requerimiento con su prueba, y la documentación final. El texto de la tabla de sprints se corta después de "documentación y"; hay que confirmar con el docente qué más se entrega (por ejemplo, la sustentación).

| ID | Alcance | Servicio | RF | Criterio de aceptación |
| --- | --- | --- | --- | --- |
| S8-01 | API de indicadores | analytics | RF9 | Donaciones registradas, reservas, entregas, volumen distribuido y proporción de canceladas y vencidas; cifras iguales a las de una consulta manual sobre el almacén. |
| S8-02 | Reportes filtrables y exportación | analytics | RF9 | Filtros por día, mes o año, zona y categoría; exporta CSV con los mismos totales que la pantalla. |
| S8-03 | Cobertura por región | analytics | RF9 | Indicadores por departamento y ciudad; los datos listos para pintarlos en un mapa. |
| S8-04 | Tablero del administrador | frontend | RF9 | Tarjetas de totales, serie en el tiempo, mapa de cobertura y tabla; accesible solo con rol administrador. |
| S8-05 | Consulta de historial y auditoría | frontend, identity | RF10 | El administrador reconstruye quién cambió qué y cuándo en una donación, reserva o entrega. |
| S8-06 | Revisión de seguridad y datos personales (Ley 1581 de 2012) | todos | RF1 | Datos personales visibles solo para personas autorizadas; reportes sin datos personales; contraseñas y secretos fuera del repositorio; política de tratamiento de datos redactada. |
| S8-07 | Matriz de trazabilidad y pruebas de aceptación | docs | RF1–RF10 | Cada requerimiento y cada regla de negocio apunta a la fila de la sección 6 que lo implementa y a una prueba que pasa. |
| S8-08 | Documentación final | docs | — | Manual de usuario por rol, manual técnico, guía de despliegue en Kubernetes y README del repositorio, verificados siguiendo los pasos en un equipo limpio. |
| S8-09 | Guion y datos para la demostración | docs | — | Recorrido de cinco a diez minutos con los cuatro actores, ensayado de principio a fin. |

## 7. Equipo y ceremonias

Cada persona es dueña de uno o dos servicios: decide sobre su esquema y su contrato, y es quien aprueba los cambios que otros propongan. El reparto es una propuesta equilibrada por carga; se ajusta según lo que cada quien domine.

| Persona | Dueña de | También |
| --- | --- | --- |
| Carlos Alfonso Niño Perdomo | identity-service, notification-service, analytics-service | Pantallas de inicio de sesión y administrador; tablero del Sprint 8 |
| Kevin Camilo Lozano Castellanos | catalog-geo-service | Pantallas de donante y receptor (mapa y búsqueda); almacén de datos del Sprint 7 |
| Santiago Aguirre Guayara | fulfillment-service | Docker, Compose, Kubernetes y gateway (Sprint 6) |

Las filas del frontend se reparten por pantalla según la tabla de arriba, y las de documentación se rotan para que nadie cargue con todas.

**Ceremonias** (al estilo Scrum, como indica el documento):

- **Planeación al inicio del sprint:** se asigna un lote por persona y se confirma que los contratos mínimos están congelados.
- **Seguimiento corto cada dos o tres días, por escrito:** qué terminé, qué sigue, qué me bloquea.
- **Revisión al final del sprint:** se ejecuta el entregable ante el docente o el equipo, no se muestran capturas.
- **Retrospectiva:** qué lotes salieron mal por estar mal definidos y qué reglas faltan en los `CLAUDE.md`; se actualizan en el mismo momento.

Cada lote se fusiona a la rama principal al pasar el recorrido de humo, sin esperar otra revisión; quien fusiona avisa al equipo qué entró, porque los otros dos servicios dependen de ello.

## 8. Definición de hecho, pruebas y revisión

Un lote está hecho cuando se cumple esta lista corta; es corta a propósito.

- [ ] El servicio arranca desde cero con un comando (bases, migraciones y semillas incluidas).
- [ ] Pasan las pruebas críticas del servicio.
- [ ] El recorrido de humo pasa de principio a fin.
- [ ] Los endpoints y eventos entre servicios coinciden con los contratos mínimos.
- [ ] No hay secretos en el repositorio.
- [ ] Leí el reporte de Claude y anoté sus pendientes y supuestos.

**Estrategia de pruebas.** Son obligatorias solo las críticas: concurrencia de reservas, transiciones de estado, permisos y flujo completo. Las demás las escribe Claude sin exigir cobertura.

| Nivel | Qué cubre | Detalle |
| --- | --- | --- |
| Unitaria | Reglas puras: puntaje de prioridad, transiciones de estado permitidas, cálculo de plazos | Rápidas, sin base de datos |
| Integración con base real | Restricciones, consultas geoespaciales y concurrencia | PostgreSQL con PostGIS en contenedor; no se simula la base, porque lo que se prueba es su comportamiento |
| Contrato | Respuestas y eventos contra OpenAPI y esquemas JSON | Falla si un servicio cambia su forma sin cambiar el contrato |
| Concurrencia | Reserva simultánea de la misma donación | S4-11 sobre la base, S5-10 sobre la API y S6-08 sobre dos réplicas |
| Extremo a extremo | Flujo principal con los cinco servicios | S5-21, y se repite en Compose y en Kubernetes |

**Lista para revisar un lote (basta mirar reservas, estados, autenticación y permisos).** El código que genera Claude suele compilar y pasar; los errores están en lo que no se ve a primera vista:

- El diff toca solo el servicio del lote.
- Las pruebas verifican el criterio de verdad: sin afirmaciones vacías ni mocks que esconden la lógica.
- La autorización comprueba el rol y que el recurso es del usuario (un receptor solo edita sus necesidades).
- Solo existen las transiciones de estado permitidas, y cada una publica su evento.
- Las consultas SQL son parametrizadas.
- Ninguna respuesta ni registro de log expone datos personales.
- Nada inventado fuera del contrato: campos, rutas o estados que no estén en `docs/`.

## 9. Riesgos

Los tres riesgos que más pueden romper el proyecto son los contratos que cambian a mitad de sprint, la inconsistencia entre servicios que no comparten base de datos y un Sprint 5 que no cabe en su plazo.

| Riesgo | Efecto | Mitigación |
| --- | --- | --- |
| Contratos o estados cambian a mitad del sprint | Tres servicios dejan de entenderse | Contratos congelados durante el sprint; cualquier cambio se acuerda entre las tres personas antes de tocar código. |
| Una donación queda RESERVADA sin reserva activa (o al revés) porque falló una llamada entre servicios | Alimento bloqueado para todos | Compensación en S5-10 y S6-04, y una tarea de conciliación que detecta y corrige esas diferencias. |
| Código que funciona pero rompe una regla de negocio | Defecto que aparece en la demostración | Una prueba por regla del Sprint 1 y la lista de revisión de la sección 8. |
| Sprint 5 no cabe en su plazo | Entregas incompletas | Partirlo en 5A y 5B; recortar por la parte baja de la tabla (pantallas de administrador, bandeja) antes que pruebas. |
| El docente espera un stack distinto al propuesto | Retrabajo al inicio del Sprint 5 | Confirmar la sección 3 antes de empezar el Sprint 4. |
| Pocos datos reales para el almacén de datos | Indicadores sin sentido en el Sprint 8 | Generador de datos sintéticos (S7-03), declarado como tal en la documentación. |
| Geocodificación o mapas dependen de un servicio externo con clave o límites | El registro de donaciones se bloquea | Mapa con OpenStreetMap; el usuario marca el punto en el mapa y la dirección queda como texto de referencia. |
| Datos personales mal protegidos (Ley 1581 de 2012) | Incumplimiento y pérdida de confianza | S8-06, y desde el inicio: sin datos personales en logs, reportes ni datos semilla reales. |
| Un lote grande se desvía o rompe lo ya construido | Retrabajo de varios días | Un commit por parte grande y recorrido de humo antes de cada fusión; si un lote sale mal se vuelve al último commit y se repite con un prompt corregido. |

## 10. Plantillas

Tres plantillas listas para copiar al repositorio. Las rutas y los nombres salen del documento de los Sprints 2 y 3; lo que depende del stack (cómo ejecutar) se completa cuando se confirme la sección 3.

**`CLAUDE.md` de la raíz**

```markdown
# RedAlimenta

Aplicación web geoespacial que conecta donantes de alimentos con receptores
según ubicación, disponibilidad y urgencia, con trazabilidad de cada entrega.
Actores: donante, receptor, administrador y sistema.

## Fuente de verdad
- `docs/` manda sobre el código.
- Contratos: `docs/contratos/openapi/*.yaml` y `docs/contratos/eventos/`.
- Modelo y estados: `docs/modelo/`. Decisiones: `docs/decisiones/`.

## Servicios
- identity-service: usuarios, autenticación, verificación, auditoría (RF1, RF10)
- catalog-geo-service: donaciones, necesidades, búsqueda geoespacial (RF2, RF3, RF4)
- fulfillment-service: reservas, entregas, tareas automáticas (RF5, RF6, RF8)
- notification-service: notificaciones (RF7)
- analytics-service: indicadores e historial (RF9, RF10)

## Reglas de trabajo
- Trabaja solo en el servicio que nombra el lote.
- No cambies contratos entre servicios, estados ni las decisiones D-01 a D-10;
  si crees que hace falta, dilo en tu reporte.
- Escribe pruebas para lo crítico: concurrencia de reservas, transiciones de estado, permisos y flujo completo.
- Solo las transiciones de estado de `docs/modelo/estados.md`; cada una publica su evento.
- Nunca guardes secretos en el repositorio; usa variables de entorno.
- No agregues dependencias sin mencionarlas en el reporte.
- Construye el lote completo sin pedir confirmación por cada paso y detente solo ante una contradicción con el modelo. Haz un commit por parte grande; la fusión a la rama principal la hace la persona.

## Convenciones
- Nombres de tablas y columnas como en el modelo (`id_donacion`, `estado_reserva`).
- Mensajes de error al usuario en español.

## Cómo ejecutar
(se completa al confirmar el stack)
```

**Plantilla de lote** (`docs/lotes/L2-fulfillment.md`)

```markdown
# Lote L2 · fulfillment-service · Sprint 5
Responsable: ___

## Alcance
Filas de la tabla del Sprint 5 (sección 6) que le tocan a este servicio:
S5-10, S5-11, S5-12, S5-13.

## Reglas y decisiones que aplican
Solo una reserva activa por donación; solo usuarios verificados reservan;
una donación se entrega solo con las dos confirmaciones. D-01, D-02, D-09.

## Contratos
Endpoints y eventos entre servicios: `docs/contratos/` (congelados).

## Listo cuando
- El servicio arranca desde cero con un comando.
- Pasan las pruebas críticas (concurrencia, estados, permisos).
- El recorrido de humo pasa.
```

**Prompt de arranque de un lote**

```markdown
Vas a construir el lote docs/lotes/L2-fulfillment.md en este servicio,
completo y de corrido.

1. Lee el CLAUDE.md de la raíz, el de este servicio, el lote y los contratos
   de docs/contratos/.
2. Dime en cinco líneas en qué orden lo vas a construir y sigue; no esperes mi
   aprobación salvo que encuentres una contradicción con el modelo o con las
   decisiones D-01 a D-10.
3. Construye todo: esquema, lógica, API, eventos y pruebas. Ejecuta las pruebas
   y corrige hasta que pasen. No pidas permiso por cada archivo o comando
   dentro de este servicio.
4. Haz un commit al terminar cada parte grande.

Al final reporta: qué quedó listo, qué quedó pendiente o dudoso y qué
supuestos tomaste.
```

## 11. Siguientes pasos

Antes de abrir la primera sesión de Claude Code hay que cerrar cuatro cosas; ninguna toma más de una reunión.

- [ ] Llevar al docente las fechas de entrega de cada sprint y qué se entrega en el Sprint 8 (las decisiones D-01 a D-10 ya están aprobadas).
- [ ] Confirmar el stack de la sección 3 con el docente, o cambiarlo por el que exija el curso.
- [ ] Crear el repositorio con la estructura de la sección 4, copiar el documento de los Sprints 0–3 a `docs/contexto/` y pegar las plantillas de la sección 10.
- [ ] Crear un tablero simple con un lote por sprint y servicio (sección 5), usando la tabla de la sección 6 como lista de cada lote.

Con eso hecho, el Lote 0 arranca solo y deja listos los contratos mínimos; desde ahí las tres personas construyen sus servicios en paralelo.
