const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, LevelFormat, HeadingLevel, PageBreak,
} = require("docx");

const FUENTE = "Calibri";
const ANCHO = 9360;
const borde = { style: BorderStyle.SINGLE, size: 4, color: "999999" };
const bordes = { top: borde, bottom: borde, left: borde, right: borde };

// Texto con **negrita** y `código` en línea
function runs(texto, base = {}) {
  const partes = texto.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return partes.map((t) => {
    if (t.startsWith("**")) return new TextRun({ text: t.slice(2, -2), bold: true, font: FUENTE, ...base });
    if (t.startsWith("`")) return new TextRun({ text: t.slice(1, -1), font: "Consolas", size: 20, ...base });
    return new TextRun({ text: t, font: FUENTE, ...base });
  });
}
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: t, font: FUENTE })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: t, font: FUENTE })] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun({ text: t, font: FUENTE })] });
const P = (t) => new Paragraph({ spacing: { after: 120, line: 276 }, alignment: AlignmentType.JUSTIFIED, children: runs(t) });
const R = (t) => new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: t, italics: true, font: FUENTE })] });
const B = (t) => new Paragraph({ numbering: { reference: "vinetas", level: 0 }, spacing: { after: 60 }, children: runs(t) });
const N = (t, ref = "numeros") => new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60 }, children: runs(t) });
const salto = () => new Paragraph({ children: [new PageBreak()] });

function codigo(lineas) {
  return lineas.map((l, i) => new Paragraph({
    shading: { type: ShadingType.CLEAR, fill: "F2F2F2", color: "auto" },
    spacing: { before: i === 0 ? 80 : 0, after: i === lineas.length - 1 ? 160 : 0 },
    indent: { left: 200, right: 200 },
    children: [new TextRun({ text: l || " ", font: "Consolas", size: 17 })],
  }));
}

function tabla(encabezado, filas, pesos) {
  const total = pesos.reduce((a, b) => a + b, 0);
  const anchos = pesos.map((p) => Math.floor((p / total) * ANCHO));
  anchos[anchos.length - 1] += ANCHO - anchos.reduce((a, b) => a + b, 0);
  const celda = (t, i, cab) => new TableCell({
    borders: bordes,
    width: { size: anchos[i], type: WidthType.DXA },
    shading: cab ? { type: ShadingType.CLEAR, fill: "D9E2F3", color: "auto" } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ children: runs(t, { size: 19, ...(cab ? { bold: true } : {}) }) })],
  });
  return [
    new Table({
      width: { size: ANCHO, type: WidthType.DXA },
      columnWidths: anchos,
      rows: [
        new TableRow({ tableHeader: true, children: encabezado.map((t, i) => celda(t, i, true)) }),
        ...filas.map((f) => new TableRow({ cantSplit: true, children: f.map((t, i) => celda(t, i, false)) })),
      ],
    }),
    new Paragraph({ spacing: { after: 120 }, children: [] }),
  ];
}

// ------------------------------------------------------------------------------------------------
const s4 = [
  H1("SPRINT 4 – Base Transaccional"),
  R("Resultado esperado: DDL, DBMS, DML, CRUD y OLTP"),
  P("En este sprint el modelo lógico del Sprint 3 se convirtió en bases de datos reales. Siguiendo la arquitectura de microservicios, cada servicio tiene su propia base de datos y solo él escribe en ella; las referencias a datos de otro servicio (por ejemplo, el donante de una donación) se guardan como identificadores, sin claves foráneas entre bases (decisión D-06)."),

  H2("1. Sistema gestor de bases de datos (DBMS)"),
  P("Se eligió **PostgreSQL 16** con la extensión **PostGIS 3.4**, ejecutado en un contenedor de Docker. Las razones de la elección son:"),
  B("**Transacciones ACID**, necesarias para que dos receptores no reserven la misma donación."),
  B("**PostGIS**: tipo `geography` para guardar puntos en el mapa y funciones para medir distancias reales en metros (`ST_Distance`, `ST_DWithin`) con índices espaciales GIST."),
  B("**Índices únicos parciales, restricciones CHECK, tipos ENUM y triggers**, que permiten que la propia base haga cumplir las reglas del negocio, no solo la aplicación."),
  B("**Roles y permisos** por base, para aplicar mínimo privilegio y hacer que la auditoría sea de solo inserción."),
  B("Es software libre, sin costo de licencia, y funciona igual en el equipo de desarrollo, en Docker y en Kubernetes."),
  P("Se crean bases separadas en la misma instancia, cada una con un rol de aplicación propio que solo puede leer y escribir lo que su servicio necesita:"),
  ...tabla(["Base de datos", "Microservicio", "Rol de la aplicación", "Tablas"], [
    ["`redalimenta_identity`", "identity-service", "`identity_app`", "rol, usuario, verificacion_usuario, registro_auditoria"],
    ["`redalimenta_catalog`", "catalog-geo-service (PostGIS)", "`catalog_app`", "categoria_alimento, ubicacion_geografica, donacion, necesidad_alimentaria"],
    ["`redalimenta_fulfillment`", "fulfillment-service", "`fulfillment_app`", "reserva, entrega, confirmacion_entrega"],
    ["`redalimenta_notification`", "notification-service", "`notification_app`", "notificacion"],
    ["`redalimenta_analytics`", "analytics-service", "`analytics_app`", "historial_evento"],
  ], [2.3, 2.2, 1.7, 3.8]),
  P("El entorno se levanta con un solo comando (`docker compose up`), que crea las bases, los roles y activa PostGIS en la base de catálogo."),

  H2("2. Lenguaje de definición de datos (DDL)"),
  P("El esquema se escribe como **migraciones versionadas con Alembic**: cada cambio queda en un archivo numerado (`0001_esquema_inicial`, `0002_…`) que se puede aplicar o revertir. `python scripts/bd.py migrar` crea todas las bases desde cero y `python scripts/bd.py revertir` las deshace. Una prueba automática verifica que el esquema de la base coincide exactamente con el modelo del código."),
  H3("Reglas de negocio llevadas al DDL"),
  ...tabla(["Elemento DDL", "Dónde", "Regla que garantiza"], [
    ["Tipos `ENUM` para cada estado", "Todas las bases", "Solo existen los estados aprobados (D-03): por ejemplo, DISPONIBLE, RESERVADA, ENTREGADA, CANCELADA y VENCIDA para la donación."],
    ["`CHECK (cantidad > 0)`", "donacion, necesidad_alimentaria", "No se publican cantidades nulas ni negativas."],
    ["`CHECK (fecha_vencimiento > fecha_publicacion)`", "donacion", "No se publica un alimento ya vencido."],
    ["Índice único `ux_usuario_correo` sobre `lower(correo_electronico)`", "usuario", "Un correo por cuenta, sin importar mayúsculas."],
    ["`geography(Point, 4326)` + índice GIST", "ubicacion_geografica", "Ubicación real en el mapa y búsqueda por distancia rápida."],
    ["Índice único parcial `ux_reserva_activa`", "reserva", "Solo una reserva activa (PENDIENTE o CONFIRMADA) por donación (D-02)."],
    ["`UNIQUE (id_reserva)`", "entrega", "Una sola entrega por reserva."],
    ["`UNIQUE (id_entrega, id_usuario)`", "confirmacion_entrega", "Cada parte confirma la entrega una sola vez."],
    ["Triggers de transición (`trg_donacion_validar`, `trg_reserva_validar`…)", "Todas las tablas con estado", "La base rechaza transiciones ilegales, como VENCIDA → DISPONIBLE, y cambios a registros cerrados."],
    ["Trigger + `REVOKE UPDATE, DELETE`", "registro_auditoria, historial_evento", "La auditoría es de solo inserción: nadie puede alterarla, ni siquiera la aplicación."],
  ], [3.2, 2.4, 4.4]),
  H3("Ejemplos de DDL"),
  P("Tabla de donaciones (catalog-geo-service):"),
  ...codigo([
    "CREATE TYPE estado_donacion AS ENUM ('DISPONIBLE','RESERVADA','ENTREGADA','CANCELADA','VENCIDA');",
    "",
    "CREATE TABLE donacion (",
    "  id_donacion          BIGSERIAL PRIMARY KEY,",
    "  id_donante           BIGINT        NOT NULL,          -- usuario de identity (sin FK, D-06)",
    "  id_categoria         SMALLINT      NOT NULL REFERENCES categoria_alimento,",
    "  id_ubicacion         BIGINT        NOT NULL REFERENCES ubicacion_geografica,",
    "  nombre_alimento      VARCHAR(120)  NOT NULL,",
    "  descripcion          TEXT,",
    "  cantidad             NUMERIC(12,2) NOT NULL,",
    "  unidad_medida        VARCHAR(30)   NOT NULL,",
    "  fecha_vencimiento    TIMESTAMPTZ,",
    "  fecha_publicacion    TIMESTAMPTZ   NOT NULL DEFAULT now(),",
    "  condiciones_recogida TEXT,",
    "  estado_donacion      estado_donacion NOT NULL DEFAULT 'DISPONIBLE',",
    "  CONSTRAINT ck_donacion_cantidad_positiva CHECK (cantidad > 0),",
    "  CONSTRAINT ck_donacion_vence_despues_de_publicar",
    "    CHECK (fecha_vencimiento IS NULL OR fecha_vencimiento > fecha_publicacion)",
    ");",
    "CREATE INDEX ix_ubicacion_coordenada ON ubicacion_geografica USING gist (coordenada_geografica);",
  ]),
  P("Una sola reserva activa por donación, resuelta por la base de datos:"),
  ...codigo([
    "CREATE UNIQUE INDEX ux_reserva_activa ON reserva (id_donacion)",
    "  WHERE estado_reserva IN ('PENDIENTE', 'CONFIRMADA');",
  ]),
  P("Transiciones de estado permitidas, validadas con un trigger:"),
  ...codigo([
    "CREATE FUNCTION fn_donacion_validar() RETURNS trigger AS $$",
    "BEGIN",
    "  IF NEW.estado_donacion IS DISTINCT FROM OLD.estado_donacion AND NOT (",
    "       (OLD.estado_donacion = 'DISPONIBLE' AND NEW.estado_donacion IN ('RESERVADA','CANCELADA','VENCIDA'))",
    "    OR (OLD.estado_donacion = 'RESERVADA'  AND NEW.estado_donacion IN ('DISPONIBLE','VENCIDA','ENTREGADA'))",
    "  ) THEN",
    "    RAISE EXCEPTION 'Transición de donación no permitida: % → %', OLD.estado_donacion, NEW.estado_donacion;",
    "  END IF;",
    "  RETURN NEW;",
    "END $$ LANGUAGE plpgsql;",
    "CREATE TRIGGER trg_donacion_validar BEFORE UPDATE ON donacion",
    "  FOR EACH ROW EXECUTE FUNCTION fn_donacion_validar();",
  ]),
  P("Auditoría de solo inserción:"),
  ...codigo([
    "REVOKE UPDATE, DELETE, TRUNCATE ON registro_auditoria FROM identity_app;",
    "CREATE TRIGGER trg_auditoria_solo_insercion BEFORE UPDATE OR DELETE ON registro_auditoria",
    "  FOR EACH ROW EXECUTE FUNCTION fn_auditoria_solo_insercion();",
  ]),
  H3("Normalización y diccionario de datos"),
  P("Las doce tablas del modelo están en **tercera forma normal**: los atributos son atómicos, todas las claves primarias son simples y no hay dependencias transitivas (el nombre de la categoría o la dirección no se repiten en la donación; se obtienen por clave foránea). Los valores derivados, como la distancia, el puntaje de prioridad o el estado de verificación vigente, no se guardan sino que se calculan en la consulta. La justificación tabla por tabla está en `docs/modelo/normalizacion.md` y el diccionario de datos, generado directamente desde las bases, en `docs/modelo/diccionario-datos.md`."),

  H2("3. Lenguaje de manipulación de datos (DML)"),
  H3("Datos semilla"),
  P("`python scripts/bd.py sembrar` inserta datos de prueba con identificadores fijos: los tres roles, siete categorías de alimentos, usuarios de cada rol (administrador, donantes y receptores, verificados y pendientes) y donaciones, necesidades y reservas en **Bogotá, Medellín y Cali**, con coordenadas reales."),
  H3("Búsqueda geoespacial con prioridad"),
  P("La consulta más importante del sistema encuentra las donaciones disponibles cerca del receptor y calcula en SQL el **puntaje de prioridad** de la decisión D-08: 0,40 × urgencia + 0,35 × cercanía + 0,25 × proximidad del vencimiento, cada término entre 0 y 1. La urgencia sale de las necesidades abiertas del propio receptor."),
  ...codigo([
    "WITH punto AS (",
    "  SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS g",
    "), urgencia AS (",
    "  SELECT id_categoria, max(CASE nivel_urgencia WHEN 'BAJA' THEN 0.25 WHEN 'MEDIA' THEN 0.5",
    "                                 WHEN 'ALTA' THEN 0.75 WHEN 'CRITICA' THEN 1.0 END) AS valor",
    "  FROM necesidad_alimentaria",
    "  WHERE id_receptor = :id_receptor AND estado_necesidad = 'ABIERTA'",
    "  GROUP BY id_categoria",
    "), candidatas AS (",
    "  SELECT d.*, ST_Distance(u.coordenada_geografica, p.g) AS distancia_m,",
    "         coalesce(ur.valor, 0) AS urgencia,",
    "         greatest(0, 1 - ST_Distance(u.coordenada_geografica, p.g) / :radio_m) AS cercania,",
    "         CASE WHEN d.fecha_vencimiento IS NULL THEN 0",
    "              ELSE greatest(0, 1 - extract(epoch FROM d.fecha_vencimiento - now()) / 3600 / 168)  -- ventana de 7 días",
    "         END AS vencimiento",
    "  FROM donacion d",
    "  JOIN ubicacion_geografica u USING (id_ubicacion)",
    "  CROSS JOIN punto p",
    "  LEFT JOIN urgencia ur ON ur.id_categoria = d.id_categoria",
    "  WHERE d.estado_donacion = 'DISPONIBLE'",
    "    AND (d.fecha_vencimiento IS NULL OR d.fecha_vencimiento > now())",
    "    AND ST_DWithin(u.coordenada_geografica, p.g, :radio_m)    -- usa el índice GIST",
    ")",
    "SELECT *, round(0.40 * urgencia + 0.35 * cercania + 0.25 * vencimiento, 4) AS puntaje",
    "FROM candidatas",
    "ORDER BY distancia_m, puntaje DESC;",
  ]),
  P("La consulta admite filtros por categoría, cantidad mínima y fecha de vencimiento, y se puede ordenar por distancia o por prioridad. Una prueba compara el puntaje con un caso calculado a mano."),
  H3("Otras operaciones DML"),
  ...codigo([
    "-- Reservar: gana quien inserta primero; los demás chocan con ux_reserva_activa",
    "INSERT INTO reserva (id_donacion, id_receptor, fecha_expiracion, estado_reserva)",
    "VALUES (:id_donacion, :id_receptor, now() + interval '2 hours', 'PENDIENTE');",
    "",
    "-- Expiración en lote (D-09): libera solo las reservas pendientes vencidas",
    "UPDATE reserva SET estado_reserva = 'EXPIRADA'",
    "WHERE estado_reserva = 'PENDIENTE' AND fecha_expiracion <= now()",
    "RETURNING id_reserva, id_donacion;",
    "",
    "-- Bandeja de notificaciones no leídas (índice por usuario y estado)",
    "SELECT * FROM notificacion WHERE id_usuario = :id AND estado_notificacion = 'NO_LEIDA'",
    "ORDER BY fecha_creacion DESC;",
  ]),

  H2("4. Operaciones CRUD"),
  P("Cada entidad tiene sus operaciones de creación, consulta, actualización y eliminación. Por la trazabilidad exigida (RF10), **ninguna eliminación borra filas**: se hace como un cambio de estado y el rol de la aplicación ni siquiera tiene permiso DELETE."),
  ...tabla(["Entidad", "Crear", "Consultar", "Actualizar", "Eliminar (como estado)"], [
    ["Usuario", "Registro", "Perfil propio; el administrador ve todos", "Nombre y teléfono", "Desactivar → DESACTIVADA"],
    ["Verificación", "Al registrarse o volver a pedirla", "Por usuario", "El administrador la resuelve", "No aplica (una resuelta no vuelve a PENDIENTE)"],
    ["Categoría", "Administrador", "Todos", "Administrador corrige el nombre", "No se borra (la usan donaciones)"],
    ["Donación", "Donante verificado", "Propias, disponibles y por distancia", "Solo mientras está DISPONIBLE", "Cancelar → CANCELADA"],
    ["Necesidad", "Receptor verificado", "Propias", "Solo mientras está ABIERTA", "Cerrar → CERRADA o CANCELADA"],
    ["Reserva", "Receptor verificado", "Propias (receptor o donante)", "Donante confirma", "Cancelar → CANCELADA; el sistema → EXPIRADA"],
    ["Entrega y confirmación", "Al confirmar la reserva", "Propias", "Cada parte confirma o reporta incidencia", "Cancelar → CANCELADA"],
    ["Notificación", "Por evento", "Bandeja propia", "Marcar como leída", "Archivar → ARCHIVADA"],
    ["Auditoría", "Por cada cambio de estado", "Administrador", "Prohibido", "Prohibido"],
  ], [1.7, 1.8, 2.2, 2.1, 2.2]),

  H2("5. Procesamiento transaccional en línea (OLTP)"),
  P("RedAlimenta es un sistema OLTP: muchas transacciones cortas y concurrentes (registrar, reservar, confirmar) que deben quedar consistentes al instante. Las decisiones que lo garantizan son:"),
  B("**Transacciones cortas**: cada caso de uso abre una transacción, hace sus cambios y confirma (`COMMIT`); si algo falla, se revierte completa (`ROLLBACK`)."),
  B("**Concurrencia resuelta por la base**: el índice único parcial `ux_reserva_activa` hace que, si dos receptores reservan a la vez, la segunda inserción falle con violación de unicidad. La aplicación la traduce a un **409 Conflict**."),
  B("**Consistencia entre bases sin transacción distribuida**: la reserva se inserta primero en fulfillment y después se pide a catalog cambiar la donación a RESERVADA. Si catalog la rechaza o no responde, la reserva se cancela (transacción de compensación, D-02)."),
  B("**Procesos en lote idempotentes**: expirar reservas, vencer donaciones y avisar donaciones por vencer se pueden ejecutar varias veces seguidas sin duplicar efectos."),
  B("**Índices para las consultas frecuentes**: por estado, por usuario, por fecha de expiración (índice parcial solo para reservas pendientes) y espacial GIST."),
  H3("Pruebas del Sprint 4"),
  ...tabla(["Prueba", "Resultado"], [
    ["20 conexiones reservan la misma donación al mismo tiempo", "Exactamente una reserva queda activa; las otras 19 reciben conflicto."],
    ["Transición ilegal (VENCIDA → DISPONIBLE)", "La base la rechaza con el trigger."],
    ["UPDATE o DELETE sobre registro_auditoria con el rol de la aplicación", "Permiso denegado."],
    ["Búsqueda por distancia", "Resultados ordenados en metros; filtros y puntaje D-08 verificados contra un cálculo manual."],
    ["Expiración en lote ejecutada dos veces", "Solo libera las reservas vencidas y la segunda vez no hace nada."],
    ["Migrar desde cero y revertir", "El esquema resultante coincide con el modelo."],
  ], [5, 5]),
  P("Las pruebas se ejecutan con `python scripts/probar.py` contra PostgreSQL real, en bases temporales que se crean y se borran en cada ejecución."),
];

// ------------------------------------------------------------------------------------------------
const s5 = [
  H1("SPRINT 5 – Aplicación"),
  R("Resultado esperado: Backend, Framework, API REST y Frontend"),
  P("En este sprint se construyó la aplicación completa sobre las bases del Sprint 4: cinco servicios de backend con su API REST, comunicación por eventos y un frontend web pensado para usarse desde el celular. Al final del sprint funciona el flujo completo: donar, buscar, reservar, confirmar y entregar."),

  H2("1. Backend"),
  P("El backend está dividido en **cinco microservicios**. Cada uno es una aplicación independiente con su propia base de datos, y se comunican de dos formas: **eventos** a través de un intermediario de mensajes (RabbitMQ) y **una única llamada directa**, cuando fulfillment pide a catalog cambiar el estado de una donación (D-01)."),
  ...tabla(["Microservicio", "Puerto", "Responsabilidad", "Requerimientos"], [
    ["identity-service", "8001", "Registro, inicio de sesión, perfiles, verificación de cuentas y auditoría", "RF1, RF10"],
    ["catalog-geo-service", "8002", "Categorías, donaciones, necesidades, búsqueda geoespacial y priorización. Único dueño del estado de la donación", "RF2, RF3, RF4"],
    ["fulfillment-service", "8003", "Reservas, entregas, confirmación bilateral y tareas automáticas (expirar, vencer, avisar)", "RF5, RF6, RF8"],
    ["notification-service", "8004", "Bandeja de notificaciones a partir de los eventos", "RF7"],
    ["analytics-service", "8005", "Historial de eventos para trazabilidad (y, en el Sprint 8, indicadores)", "RF9, RF10"],
  ], [2.2, 1, 5, 1.8]),
  H3("Organización interna de cada servicio"),
  P("Todos los servicios siguen la misma estructura por capas, así un integrante que conoce uno conoce todos:"),
  ...tabla(["Capa", "Archivo", "Qué hace"], [
    ["Modelo", "`modelos.py`", "Tablas mapeadas con SQLAlchemy (coinciden con las migraciones)."],
    ["Acceso a datos", "`repositorio.py`", "Consultas y transacciones SQL."],
    ["Lógica de negocio", "`servicio.py`", "Casos de uso: valida permisos y reglas, llama al repositorio y publica eventos después del COMMIT."],
    ["API", "`rutas.py`", "Rutas REST, validación de entrada con Pydantic y respuesta en JSON."],
    ["Eventos", "`consumidor.py`", "Recibe eventos de otros servicios; procesa cada uno una sola vez (idempotente)."],
    ["Arranque", "`app.py`", "Crea la aplicación, maneja errores y expone `/salud` y `/vivo`."],
  ], [2, 2, 6]),
  P("El código común a todos (seguridad JWT, formato de errores, publicador de eventos, identificador de correlación para seguir una operación entre servicios) está en una plantilla compartida, `services/comun`."),
  H3("Comunicación por eventos"),
  P("Cada cambio de estado publica un evento en RabbitMQ (intercambio de tipo *topic* `redalimenta.eventos`). Hay 23 tipos de evento, por ejemplo `DONACION_CREADA`, `RESERVA_CREADA`, `RESERVA_EXPIRADA`, `ENTREGA_COMPLETADA` o `DONACION_POR_VENCER`. Tres colas los consumen:"),
  B("`identity.auditoria`: identity guarda cada evento en el registro de auditoría (RF10)."),
  B("`notification.bandeja`: notification crea el aviso para el usuario que corresponde (RF7)."),
  B("`analytics.historial`: analytics guarda el historial para trazabilidad y reportes."),
  P("Los eventos se publican solo después de confirmar la transacción, y cada consumidor registra los eventos ya procesados para no duplicar efectos si un mensaje llega dos veces."),
  H3("Seguridad"),
  B("Contraseñas guardadas con resumen criptográfico **PBKDF2** (nunca en texto plano)."),
  B("Sesión con **token JWT** de vigencia corta que lleva el identificador del usuario, su rol y su estado de verificación (D-06). Cada servicio valida el token por su cuenta."),
  B("Autorización por rol: una ruta de administrador responde **403** a un donante, y solo los usuarios verificados pueden publicar o reservar."),
  B("Las rutas internas entre servicios (`/internal`) exigen un token interno y no son accesibles desde fuera."),

  H2("2. Framework y tecnologías"),
  ...tabla(["Capa", "Tecnología", "Uso en RedAlimenta"], [
    ["Lenguaje del backend", "Python 3.12", "Los cinco servicios."],
    ["Framework web", "**FastAPI**", "Rutas REST, validación automática con Pydantic y documentación OpenAPI generada sola en `/docs`."],
    ["Servidor", "Uvicorn", "Ejecuta cada servicio."],
    ["Acceso a datos (ORM)", "SQLAlchemy 2 + GeoAlchemy2", "Modelos y consultas, incluidas las espaciales de PostGIS."],
    ["Controlador de PostgreSQL", "psycopg 3", "Conexión a las bases."],
    ["Migraciones", "Alembic", "DDL versionado (Sprint 4)."],
    ["Mensajería", "RabbitMQ + pika", "Publicación y consumo de eventos."],
    ["Autenticación", "PyJWT", "Emisión y validación de tokens."],
    ["Frontend", "**React 19 + Vite 6**", "Interfaz web de una sola página."],
    ["Mapas", "Leaflet + react-leaflet sobre OpenStreetMap", "Mapas sin clave ni costo para marcar y ver ubicaciones."],
    ["Pruebas", "pytest", "Pruebas contra PostgreSQL real."],
  ], [2.4, 2.8, 4.8]),
  P("Se eligió FastAPI porque genera la documentación de la API automáticamente, valida los datos de entrada sin código adicional y es ligero, lo que conviene a una arquitectura de varios servicios pequeños."),

  H2("3. API REST"),
  P("Cada servicio expone una API REST bajo el prefijo `/api`, con estas convenciones:"),
  B("Recursos en plural y verbos HTTP estándar: `GET` consulta, `POST` crea o ejecuta una acción, `PATCH` actualiza parcialmente."),
  B("Las acciones que cambian un estado son rutas propias (`POST /api/reservas/{id}/confirmar`), nunca un `DELETE`."),
  B("Cuerpos y respuestas en **JSON**; fechas en ISO 8601 con zona horaria."),
  B("Autenticación con la cabecera `Authorization: Bearer <token>`."),
  B("Errores con un formato único `{\"detalle\": \"…\"}` y códigos coherentes: 400 datos inválidos, 401 sin sesión, 403 sin permiso, 404 no existe, **409 conflicto** (por ejemplo, la donación ya tiene una reserva activa) y 503 si otro servicio no responde."),
  B("Contrato **OpenAPI** de cada servicio guardado en `docs/contratos/openapi/` y consultable en `/docs`."),
  H3("Rutas principales"),
  ...tabla(["Servicio", "Método y ruta", "Qué hace"], [
    ["identity", "`POST /api/auth/registro`", "Crea una cuenta (queda pendiente de verificación)."],
    ["identity", "`POST /api/auth/login`", "Inicia sesión y devuelve el token JWT."],
    ["identity", "`GET / PATCH /api/usuarios/me`", "Consulta y actualiza el perfil propio."],
    ["identity", "`POST /api/admin/verificaciones/{id}`", "El administrador aprueba o rechaza una cuenta."],
    ["identity", "`GET /api/admin/auditoria`", "Registro de auditoría."],
    ["catalog-geo", "`POST /api/donaciones`", "Publica una donación con su punto en el mapa."],
    ["catalog-geo", "`PATCH /api/donaciones/{id}` · `POST …/cancelar`", "Modifica o cancela una donación disponible."],
    ["catalog-geo", "`GET /api/donaciones/disponibles`", "Búsqueda por distancia con filtros y puntaje de prioridad."],
    ["catalog-geo", "`POST /api/necesidades` · `PATCH …/{id}`", "Registra y ajusta necesidades."],
    ["fulfillment", "`POST /api/reservas`", "Reserva una donación (201, o 409 si ya está reservada)."],
    ["fulfillment", "`POST /api/reservas/{id}/confirmar` · `…/cancelar`", "El donante confirma; cualquiera de las partes cancela."],
    ["fulfillment", "`POST /api/entregas/{id}/confirmar`", "Confirmación bilateral o reporte de incidencia."],
    ["notification", "`GET /api/notificaciones` · `POST …/{id}/leer`", "Bandeja de avisos y marcar como leído."],
    ["analytics", "`GET /api/historial/entidades/{entidad}`", "Historial completo de una donación, reserva o entrega."],
  ], [1.6, 4.2, 4.2]),
  P("En total la API tiene más de 60 operaciones documentadas."),

  H2("4. Frontend"),
  P("El frontend es una aplicación **React** construida con **Vite**, diseñada primero para celular (usable desde 360 px de ancho) y adaptada también a pantallas de escritorio. Al iniciar sesión muestra solo las pantallas del rol del usuario; sin sesión no se ve ninguna pantalla protegida."),
  ...tabla(["Rol", "Pantallas", "Funcionalidad"], [
    ["Todos", "Inicio de sesión y registro; Avisos", "Entrar o crear cuenta; bandeja de notificaciones con contador de no leídas."],
    ["Donante", "Publicar, Mis donaciones, Entregas", "Publicar marcando el punto de recogida en el mapa, con validación de cantidad y fecha; confirmar o rechazar reservas; confirmar la entrega."],
    ["Receptor", "Buscar, Necesidades, Mis reservas, Entregas", "Mapa con las donaciones cercanas ordenadas por distancia o prioridad; reservar viendo el plazo de 2 horas; registrar necesidades; confirmar la entrega."],
    ["Administrador", "Cuentas, Categorías, Auditoría", "Aprobar o rechazar cuentas con observación; mantener categorías; consultar la auditoría."],
  ], [1.6, 3, 5.4]),
  P("Los mapas usan Leaflet con teselas de OpenStreetMap: el usuario toca el mapa para marcar la ubicación y la dirección escrita queda solo como referencia, sin depender de un servicio de geocodificación con clave."),

  H2("5. Flujo completo y pruebas"),
  P("El script `python scripts/e2e.py` recorre el flujo principal contra el sistema en marcha y comprueba cada paso:"),
  N("El donante publica una donación."),
  N("El receptor la encuentra en la búsqueda, con su distancia y puntaje."),
  N("El receptor la reserva y la donación pasa a RESERVADA."),
  N("El donante confirma la reserva y se programa la entrega."),
  N("Donante y receptor confirman la entrega y la donación queda ENTREGADA."),
  N("Cada cambio generó su notificación, su registro de auditoría y su historial."),
  ...tabla(["Pruebas automáticas", "Cantidad"], [
    ["identity-service", "23"], ["catalog-geo-service", "25"], ["fulfillment-service", "23"],
    ["notification-service", "13"], ["analytics-service (historial)", "3"],
  ], [7, 3]),
  P("Entre ellas: registro y token, 403 para un rol no autorizado, reserva concurrente (una 201 y la otra 409), compensación cuando catalog rechaza, confirmación bilateral de la entrega, idempotencia de las tareas automáticas y de los consumidores de eventos."),
];

const doc = new Document({
  creator: "RedAlimenta",
  title: "RedAlimenta – Sprints 4 y 5",
  styles: {
    default: { document: { run: { font: FUENTE, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FUENTE, size: 24, bold: true }, paragraph: { spacing: { before: 240, after: 80 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FUENTE, size: 22, bold: true }, paragraph: { spacing: { before: 240, after: 100 }, keepNext: true, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FUENTE, size: 22, bold: true, italics: true }, paragraph: { spacing: { before: 160, after: 80 }, keepNext: true, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "vinetas", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numeros", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    children: [...s4, salto(), ...s5],
  }],
});

Packer.toBuffer(doc).then((b) => fs.writeFileSync(process.argv[2], b));
