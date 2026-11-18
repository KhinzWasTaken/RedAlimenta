# Manual técnico de RedAlimenta

## 1. Arquitectura

Cinco servicios Python (FastAPI + SQLAlchemy), cada uno con su base PostgreSQL, comunicados por eventos en
RabbitMQ y una llamada síncrona (fulfillment → catalog-geo, D-01); un gateway nginx que sirve el frontend
React y reparte `/api`; y un almacén de datos con su ETL. Detalle: `docs/arquitectura/soa.md` y
`docs/arquitectura/bases-distribuidas.md`.

| Componente | Carpeta | Base | Puerto (desarrollo) |
| --- | --- | --- | --- |
| identity-service | `services/identity-service` (`identidad/`) | `redalimenta_identity` | 8001 |
| catalog-geo-service | `services/catalog-geo-service` (`catalogo/`) | `redalimenta_catalog` (PostGIS) | 8002 |
| fulfillment-service | `services/fulfillment-service` (`cumplimiento/`) | `redalimenta_fulfillment` | 8003 |
| notification-service | `services/notification-service` (`notificaciones/`) | `redalimenta_notification` | 8004 |
| analytics-service | `services/analytics-service` (`analitica/`) | `redalimenta_analytics` + lectura de `redalimenta_dwh` | 8005 |
| Plantilla común | `services/comun` (`redalimenta_comun`) | — | — |
| Almacén y ETL | `dwh/` (`almacen/`) | `redalimenta_dwh` (`stg`, `dw`, `etl`) | — |
| Frontend y gateway | `frontend/`, `infra/gateway/` | — | 5173 (Vite) / 8080 (gateway) |

Cada servicio tiene un `CLAUDE.md` con sus tablas, reglas y eventos.

## 2. Estructura de un servicio

```
<servicio>/
  <paquete>/modelos.py       tablas (SQLAlchemy) con comentarios para el diccionario de datos
  <paquete>/repositorio.py   consultas y transacciones (quien llama hace commit)
  <paquete>/servicio.py      casos de uso: repositorio + eventos (se publican tras el commit)
  <paquete>/rutas.py         API REST (pydantic para validar)
  <paquete>/consumidor.py    consumo de eventos (si aplica), idempotente
  <paquete>/semilla.py       datos de demostración con identificadores fijos
  <paquete>/app.py           crear_app(): errores, /salud, /vivo, correlación, hilos
  migrations/                Alembic; el esquema debe coincidir con modelos.py
  tests/                     pytest contra PostgreSQL real (base temporal por sesión)
  Dockerfile
```

## 3. Configuración

Todo por variables de entorno; los secretos nunca en el código.

| Variable | Dónde | Uso |
| --- | --- | --- |
| `DATABASE_URL` | cada servicio | Su base, con su rol de mínimo privilegio |
| `DWH_DATABASE_URL` | analytics | Lectura del almacén |
| `RABBITMQ_URL` | servicios | Broker de eventos |
| `JWT_SECRETO` (≥ 32 caracteres), `JWT_MINUTOS` | todos | Firma y vigencia del token (D-06) |
| `TOKEN_INTERNO` | catalog y fulfillment | Autoriza `/internal` |
| `CATALOG_URL` | fulfillment | API interna de catalog |
| `PLAZO_RESERVA_HORAS`, `AVISO_POR_VENCER_HORAS` | fulfillment | D-09 |
| `PESO_URGENCIA`, `PESO_CERCANIA`, `PESO_VENCIMIENTO`, `RADIO_BUSQUEDA_M` | catalog | D-08 |
| `TAREAS_SEGUNDOS` | fulfillment | Planificador interno (0 = lo hace el CronJob) |
| `MODO_DEMO` | fulfillment | Habilita "forzar expiración" |
| `CONSUMIR_EVENTOS`, `EVENTOS_BACKEND` | servicios | Activar consumidores; `memoria` en pruebas |

En desarrollo y Compose se leen de `infra/.env` (copia de `infra/.env.example`).

## 4. Operación

| Tarea | Comando |
| --- | --- |
| Levantar todo en desarrollo (servicios locales + Vite) | `python scripts/levantar.py [--reiniciar]` |
| Levantar todo en contenedores | `docker compose -f infra/docker-compose.yml --env-file infra/.env --profile app up -d --build` |
| Migrar, revertir, sembrar, verificar coherencia | `python scripts/bd.py migrar|revertir|sembrar|reiniciar|verificar` |
| Regenerar el diccionario de datos | `python scripts/bd.py diccionario` |
| Cargar el almacén / ver indicadores / informe de calidad | `python scripts/etl.py cargar <tipo>`, `indicadores`, `informe` |
| Pruebas de todos los servicios y del almacén | `python scripts/probar.py` |
| Pruebas de la matriz de trazabilidad | `python scripts/trazabilidad.py --ejecutar` |
| Flujo completo, resiliencia, carga concurrente | `python scripts/e2e.py`, `resiliencia.py`, `carga_reservas.py` |
| Contratos y gateway al día | `python scripts/contratos.py --revisar`, `python scripts/gateway.py --revisar` |
| Revisión de seguridad | `python scripts/revisar_seguridad.py --bases` |
| Kubernetes | `python scripts/k8s.py imagenes|desplegar|probar|borrar` |

## 5. Cómo agregar algo sin romper las reglas

- **Una columna o tabla:** cámbiala en `modelos.py`, crea una migración nueva (`alembic revision`), nunca edites
  una migración ya desplegada; `tests/test_esquema.py` falla si el modelo y la base difieren.
- **Una ruta de API:** agrégala en `rutas.py` con la dependencia de seguridad adecuada; luego
  `python scripts/contratos.py` y, si es un prefijo nuevo, agrégalo a `infra/rutas.json` y corre
  `python scripts/gateway.py`.
- **Un evento:** publícalo con `Lote.agregar(...)` en el caso de uso, documéntalo en
  `docs/contratos/eventos/README.md` y, si avisa a alguien, agrega su caso en
  `notificaciones/consumidor.py::destinatarios`.
- **Un estado o transición:** primero en `docs/modelo/estados.md` (decisión del equipo), luego ENUM,
  trigger y repositorio.

## 6. Diagnóstico

- Cada respuesta trae `X-Correlation-Id`; con `docker compose ... logs | grep <id>` se ve la operación en todos
  los servicios y consumidores.
- `GET /salud` (base) y `GET /vivo` (proceso) en cada servicio; `GET /salud` en el gateway.
- Consola de RabbitMQ: `http://localhost:15672` (colas `identity.auditoria`, `notification.bandeja`,
  `analytics.historial`).
- Estado de las cargas del almacén: `SELECT * FROM etl.ejecucion ORDER BY id_ejecucion DESC`.
