# RedAlimenta

Trabajo de Bases de Datos Avanzadas. El repositorio tiene dos partes:

- **Proyecto final (Sprints 4–8)**, en construcción: microservicios con PostgreSQL + PostGIS y RabbitMQ
  (`services/`, `infra/`, `scripts/`). Plan en `docs/contexto/plan-sprints-4-8.md`.
- **Prototipo de clase** (más abajo): una sola aplicación con SQLite (`backend/`, `frontend/`).
  Queda como referencia; el sistema vigente son los servicios (`python scripts/levantar.py`).

## Proyecto final · estado

| Sprint | Tema | Estado |
| --- | --- | --- |
| 4 | Base transaccional: DDL, DML, CRUD, OLTP | ✅ Listo |
| 5 | Aplicación: API REST por servicio, eventos, frontend | ✅ Listo |
| 6 | Docker, gateway, Kubernetes | Pendiente |
| 7 | Almacén de datos y ETL | Pendiente |
| 8 | Indicadores, tablero y documentación final | Pendiente |

### Ejecutar el sistema completo (Sprint 5)

Requisitos: Docker Desktop, Python 3.11+ y Node.js 18+. Una vez:

```bash
copy infra\.env.example infra\.env
```

(en macOS/Linux: `cp infra/.env.example infra/.env`; luego cambia todas las claves del archivo)

```bash
pip install -r requirements-dev.txt
```

Para levantar todo (PostgreSQL, RabbitMQ, migraciones, los 5 servicios y el frontend):

```bash
python scripts/levantar.py --reiniciar
```

Abre **http://localhost:5173**. Sin `--reiniciar` conserva los datos. Ctrl+C detiene todo.

| Servicio | Puerto | Documentación de la API | Responsabilidad |
| --- | --- | --- | --- |
| identity-service | 8001 | http://localhost:8001/docs | Cuentas, JWT, verificación, auditoría (RF1, RF10) |
| catalog-geo-service | 8002 | http://localhost:8002/docs | Donaciones, necesidades, búsqueda geoespacial (RF2–RF4) |
| fulfillment-service | 8003 | http://localhost:8003/docs | Reservas, entregas, tareas automáticas (RF5, RF6, RF8) |
| notification-service | 8004 | http://localhost:8004/docs | Notificaciones in-app (RF7) |
| analytics-service | 8005 | http://localhost:8005/docs | Historial de eventos (RF10); indicadores en Sprints 7–8 |
| RabbitMQ | 15672 | consola web (usuario y clave de `infra/.env`) | Eventos entre servicios |

Cómo encajan: cada servicio tiene su base y su rol de base de datos; los cambios de estado viajan como
eventos por RabbitMQ (auditoría, notificaciones e historial los consumen); la única llamada directa es
fulfillment → catalog-geo para cambiar el estado de una donación (D-01). En desarrollo, Vite reparte cada
prefijo de `/api` al servicio que lo atiende según `infra/rutas.json` (en el Sprint 6 lo hará el gateway).

Comprobaciones:

| Comando | Qué hace |
| --- | --- |
| `python scripts/probar.py` | Pruebas de los 5 servicios contra PostgreSQL real (83 pruebas) |
| `python scripts/e2e.py` | Con el sistema levantado y recién sembrado: flujo completo con eventos reales (S5-21) |
| `python scripts/contratos.py --revisar` | Falla si el código cambió y los contratos OpenAPI guardados no |

Contratos: `docs/contratos/openapi/*.yaml` (uno por servicio, más la API interna de catalog) y
`docs/contratos/eventos/` (catálogo de eventos y esquema JSON del sobre común).

### Sprint 4 · Base transaccional

Cuatro bases separadas, una por servicio, en un servidor PostgreSQL 16 con PostGIS:

| Servicio | Base | Tablas |
| --- | --- | --- |
| `services/identity-service` | `redalimenta_identity` | rol, usuario, verificacion_usuario, registro_auditoria |
| `services/catalog-geo-service` | `redalimenta_catalog` | categoria_alimento, ubicacion_geografica (PostGIS), donacion, necesidad_alimentaria |
| `services/fulfillment-service` | `redalimenta_fulfillment` | reserva, entrega, confirmacion_entrega |
| `services/notification-service` | `redalimenta_notification` | notificacion |

Requisitos: Docker Desktop y Python 3.11+.

1. Crear el archivo de contraseñas locales (no se sube al repositorio) y editarlo:

   ```bash
   copy infra\.env.example infra\.env
   ```

   (en macOS/Linux: `cp infra/.env.example infra/.env`)

2. Levantar PostgreSQL con las cuatro bases:

   ```bash
   docker compose -f infra/docker-compose.yml --env-file infra/.env up -d
   ```

3. Instalar dependencias:

   ```bash
   pip install -r requirements-dev.txt
   ```

4. Crear el esquema y cargar los datos semilla (Bogotá, Medellín y Cali), y comprobar la coherencia entre bases:

   ```bash
   python scripts/bd.py reiniciar
   ```

Otros comandos:

| Comando | Qué hace |
| --- | --- |
| `python scripts/bd.py migrar` / `revertir` | Aplica o revierte todas las migraciones Alembic |
| `python scripts/bd.py sembrar` | Inserta los datos semilla si las tablas están vacías |
| `python scripts/bd.py verificar` | Conciliación entre bases (referencias y estados coherentes) |
| `python scripts/bd.py diccionario` | Regenera `docs/modelo/diccionario-datos.md` desde las bases |
| `python scripts/probar.py` | Pruebas de los servicios contra PostgreSQL real |

Qué demuestran las pruebas: restricciones e integridad, transiciones de estado validadas por la base
(triggers), permisos del rol de aplicación (sin DELETE; auditoría solo inserción), búsqueda geoespacial
ordenada por metros con el puntaje D-08 verificado a mano, **20 conexiones reservando la misma donación
con una sola reserva activa** (D-02), expiración en lote idempotente y migraciones que se aplican y
revierten desde cero.

Documentación del sprint: `docs/modelo/diccionario-datos.md`, `docs/modelo/normalizacion.md`,
`docs/modelo/datos-semilla.md`, `docs/modelo/estados.md` y `docs/decisiones/README.md`.

---

# Prototipo de clase

Primera versión, presentada antes del proyecto final. **Desde el Sprint 5 el frontend (`frontend/`) habla con
los microservicios**, así que `demo.py` ya no muestra todas las pantallas. Para ver el prototipo exactamente como
se presentó: `git checkout 1e6fec5` (y `git checkout -` para volver). Aplicación web geoespacial que conecta donantes de
alimentos con receptores según ubicación, disponibilidad y urgencia, con trazabilidad de
cada entrega.

Es **una sola aplicación** (no microservicios) con módulos separados en el backend:

| Módulo | Carpeta | Qué hace |
| --- | --- | --- |
| Identidad | `backend/app/identidad` | Usuarios, inicio de sesión con JWT, verificación por el administrador, auditoría |
| Catálogo | `backend/app/catalogo` | Donaciones, necesidades, búsqueda por distancia (Haversine) y prioridad (D-08) |
| Reservas y entregas | `backend/app/reservas` | Reserva con control de concurrencia, confirmaciones, tareas automáticas |
| Notificaciones | `backend/app/notificaciones` | Bandeja in-app generada a partir de los eventos |

Tecnologías: Python + FastAPI + SQLAlchemy + SQLite en el backend; React + Vite +
react-leaflet sobre OpenStreetMap en el frontend.

Las reglas de negocio están en `docs/`: modelo (`docs/modelo/`), estados y transiciones
(`docs/modelo/estados.md`) y decisiones D-01 a D-10 (`docs/decisiones/README.md`).

## Requisitos

- Python 3.11 o superior
- Node.js 18 o superior (solo para compilar el frontend)
- Conexión a internet en el navegador para ver las teselas del mapa de OpenStreetMap

Instalación de dependencias de Python (una vez):

```bash
pip install -r backend/requirements.txt
```

## Demostración: un solo comando

```bash
python demo.py --reiniciar
```

Compila el frontend si hace falta, borra y vuelve a sembrar la base, y levanta todo en
**http://localhost:8000** (el backend sirve el frontend compilado). Desde un celular en la
misma red Wi-Fi: `http://IP-DEL-COMPUTADOR:8000`. Sin `--reiniciar` conserva los datos.

## Desarrollo

```bash
python dev.py
```

Levanta el backend con recarga automática en :8000 (documentación de la API en
http://localhost:8000/docs) y Vite en **http://localhost:5173**, que reenvía `/api` al backend.

## Pruebas

```bash
cd backend && python -m pytest -q
```

Cubren lo crítico: reserva concurrente (20 receptores a la vez, índice único parcial y
compensación), transiciones de estado y el flujo completo de principio a fin.

## Usuarios semilla (contraseña `demo123`)

| Rol | Correo | Estado inicial |
| --- | --- | --- |
| Donante — Supermercado La Cosecha | donante@redalimenta.co | APROBADA |
| Receptor — Comedor Comunitario Esperanza | receptor@redalimenta.co | **PENDIENTE** (el administrador lo verifica en la demo) |
| Administrador | admin@redalimenta.co | APROBADA |

Datos semilla: 7 categorías, 10 donaciones en distintas localidades de Bogotá y 4
necesidades del receptor (Ciudad Bolívar, Bosa y Kennedy) con urgencias de BAJA a CRÍTICA.
En la pantalla de inicio de sesión hay botones que llenan el correo y la contraseña.

## Guion de demostración (5 minutos)

Antes: `python demo.py --reiniciar` y abrir http://localhost:8000 en vista de celular
(F12 → modo dispositivo) o en un teléfono.

1. **Verificación (0:00–0:45).** Entrar como **Receptor**: aparece el aviso "PENDIENTE de
   verificación"; puede mirar el mapa pero no reservar. Salir, entrar como **Administrador**
   → *Cuentas* → aprobar al Comedor Comunitario Esperanza. *Mensaje: solo los verificados operan;
   la verificación es un flujo de estados, no un campo editable.*
2. **Publicar (0:45–1:45).** Entrar como **Donante** → *Publicar*. Tocar el mapa en el sur de
   Bogotá (cerca de Ciudad Bolívar), alimento "Lentejas", categoría *Granos y enlatados*,
   50 kg, vence en dos días → *Publicar donación*. Queda DISPONIBLE en *Mis donaciones*.
3. **Buscar (1:45–2:45).** Entrar como **Receptor** → *Buscar*. El punto de búsqueda es su
   necesidad más urgente (D-07). Ver el mapa (verde = mayor prioridad) y la *Lista*: cada
   tarjeta muestra la distancia y el puntaje D-08 desglosado
   (0,40·urgencia + 0,35·cercanía + 0,25·vencimiento). Cambiar a *Ordenar por distancia* y
   filtrar por categoría.
4. **Reservar y expirar (2:45–3:30).** *Reservar* las Lentejas: se muestra el plazo de 2 horas
   (D-09). En *Mis reservas* pulsar **⏱ Forzar expiración**: la reserva pasa a EXPIRADA y la
   donación vuelve a DISPONIBLE. Reservar otra vez. *Mencionar la concurrencia: si otro receptor
   reserva lo mismo, la API responde 409; la prueba `test_20_receptores_reservando_a_la_vez`
   lanza 20 solicitudes simultáneas y solo una gana.*
5. **Confirmar y entregar (3:30–4:30).** **Donante** → *Mis donaciones* → *Confirmar reserva*.
   *Entregas* → *Confirmar entrega*: la donación sigue RESERVADA ("falta la otra parte").
   **Receptor** → *Entregas* → *Confirmar entrega*: ahora queda **ENTREGADA**.
6. **Trazabilidad (4:30–5:00).** *Avisos* del receptor: una notificación por cada cambio.
   **Administrador** → *Auditoría*, filtrar por *donacion*: DISPONIBLE → RESERVADA →
   DISPONIBLE → RESERVADA → ENTREGADA, con quién y cuándo. *La tabla es de solo inserción.*

Para repetir la demo desde cero: detener con Ctrl+C y volver a ejecutar `python demo.py --reiniciar`.

## API principal

| Método y ruta | Quién | Qué hace |
| --- | --- | --- |
| `POST /api/auth/login`, `POST /api/auth/refresh` | todos | Token JWT con rol y verificación |
| `GET /api/admin/usuarios`, `POST /api/admin/verificaciones/{id}` | administrador | Verificar cuentas |
| `GET /api/admin/auditoria?entidad=&id_registro=` | administrador | Registro de auditoría |
| `POST /api/donaciones`, `GET /api/donaciones/mias`, `POST /api/donaciones/{id}/cancelar` | donante | Publicar y gestionar |
| `GET /api/donaciones/disponibles?lat=&lon=` o `?id_necesidad=` `&id_categoria=&orden=` | receptor | Búsqueda con distancia y prioridad |
| `POST /api/reservas` (201 / 409), `POST /api/reservas/{id}/confirmar` · `/cancelar` · `/forzar-expiracion` | receptor / donante | Ciclo de la reserva |
| `POST /api/entregas/{id}/confirmar` | donante y receptor | Confirmación bilateral |
| `GET /api/notificaciones`, `GET /api/notificaciones/no-leidas` | todos | Bandeja in-app |
| `POST /api/admin/tareas/ejecutar` | administrador | Corre vencimientos, expiraciones y avisos |

## Configuración (variables de entorno opcionales)

| Variable | Defecto | Uso |
| --- | --- | --- |
| `REDALIMENTA_JWT_SECRETO` | aleatorio por proceso | Clave del JWT (sin secretos en el repositorio) |
| `REDALIMENTA_PLAZO_RESERVA_HORAS` | 2 | Plazo de confirmación (D-09) |
| `REDALIMENTA_AVISO_VENCER_HORAS` | 24 | Aviso de "por vencer" (D-09) |
| `REDALIMENTA_PESO_URGENCIA` / `_CERCANIA` / `_VENCIMIENTO` | 0,40 / 0,35 / 0,25 | Pesos D-08 |
| `REDALIMENTA_RADIO_KM` | 20 | Distancia que normaliza la cercanía |
| `REDALIMENTA_PLANIFICADOR_SEGUNDOS` | 60 | Frecuencia de las tareas automáticas |
| `REDALIMENTA_MODO_DEMO` | 1 | Habilita el botón "forzar expiración" |
| `REDALIMENTA_DB_URL` | `sqlite:///backend/redalimenta.db` | Base de datos |

## Fuera de alcance del prototipo

Gateway, broker de mensajes, Docker/Kubernetes, correo electrónico y almacén de datos
(Sprints 6 a 8 del plan en `docs/contexto/plan-sprints-4-8.md`). El broker se reemplaza por
un bus de eventos en proceso (`backend/app/core/eventos.py`) con el mismo sobre de evento.
