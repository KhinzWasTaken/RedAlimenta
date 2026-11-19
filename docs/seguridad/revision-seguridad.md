# Revisión de seguridad y datos personales (S8-06)

Revisión hecha sobre el sistema completo (servicios, almacén, gateway, Compose y Kubernetes) frente a la
Ley 1581 de 2012 de protección de datos personales y a los riesgos del plan (sección 9). Las comprobaciones
automáticas se repiten con `python scripts/revisar_seguridad.py --bases`.

## 1. Qué datos personales trata RedAlimenta

| Dato | Dónde | Quién lo ve | Para qué |
| --- | --- | --- | --- |
| Nombre de la persona u organización | `redalimenta_identity.usuario` | El propio usuario; el administrador; la contraparte de una reserva (solo el nombre) | Coordinar la entrega |
| Correo electrónico | `usuario` | El propio usuario y el administrador | Inicio de sesión |
| Teléfono | `usuario` | El propio usuario y el administrador | Contacto para la verificación |
| Contraseña | `usuario.contrasena_hash` (PBKDF2-SHA256 con sal, 120.000 iteraciones) | Nadie (no se puede recuperar) | Autenticación |
| Dirección de referencia y coordenadas del punto de recogida | `redalimenta_catalog` | Receptores que buscan donaciones | Recoger el alimento |
| Mensajes del chat (D-12) | `redalimenta_notification.mensaje` | Solo el donante y el receptor de la conversación (ni el administrador) | Pactar la entrega; no se publican como eventos |

Ningún dato sensible (salud, origen étnico, etc.) se recoge. No hay datos de menores.

## 2. Controles verificados

| Control | Cómo se cumple | Evidencia |
| --- | --- | --- |
| Acceso solo para personas autorizadas | JWT con rol en todas las rutas salvo login, registro y salud; un usuario solo ve su perfil, sus donaciones, reservas y notificaciones | `revisar_seguridad.py` (toda operación de la API exige sesión), pruebas de 401/403 en cada servicio |
| Mínimo privilegio en las bases | Un rol por servicio, que solo puede conectarse a su base; sin DELETE; auditoría e historial de solo inserción | `test_rol_de_aplicacion_*`, `test_auditoria_inmutable_incluso_para_el_dueno` |
| Rutas internas no expuestas | `/internal` exige `X-Token-Interno` y el gateway responde 404 | `test_transicion_interna_d01`, prueba en el gateway |
| Reportes sin datos personales | El almacén solo guarda identificador y rol de cada participante; los indicadores son agregados | `revisar_seguridad.py --bases`, `test_carga_historica_repetible_y_con_conteos_iguales` |
| Lectura de las fuentes sin poder modificarlas | El ETL usa `dwh_lector` en transacciones de solo lectura | `test_las_fuentes_se_leen_en_solo_lectura` |
| Registros sin datos personales | Los servicios registran método, ruta, código y correlación; nunca cuerpos, correos ni contraseñas; uvicorn sin registro de accesos | Revisión de `redalimenta_comun/correlacion.py` |
| Secretos fuera del repositorio | `infra/.env` (ignorado por git), Secret de Kubernetes generado al desplegar, imágenes sin secretos | `revisar_seguridad.py` (archivos y Dockerfiles) |
| Claves fuertes | Los servicios no arrancan si `JWT_SECRETO` tiene menos de 32 caracteres; tokens de 60 minutos | `redalimenta_comun/seguridad.py` |
| Fuerza bruta | El gateway limita el inicio de sesión y el registro a 30 por minuto por IP (ráfaga de 20) y responde 429 | `infra/gateway/default.conf.template` |
| Cabeceras de seguridad | `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`; versión de nginx oculta | Gateway |
| Contenedores | Usuario sin privilegios (uid 10001, nginx), `allowPrivilegeEscalation: false`, capacidades eliminadas en Kubernetes | Dockerfiles, `infra/k8s/servicios.yaml` |

## 3. Hallazgos y decisiones

| Hallazgo | Riesgo | Decisión |
| --- | --- | --- |
| Las contraseñas de los usuarios de demostración (`demo123`) están en el repositorio | Bajo: son datos ficticios de demostración | Se documentan como tales; en un despliegue real no se cargan los datos semilla (`MODO_HERRAMIENTAS=migrar`) |
| `GET /api/usuarios/nombres` da el nombre de cualquier usuario a cualquier usuario autenticado | Medio: el nombre de una persona natural es dato personal | Se acepta para la finalidad de coordinar entregas y solo expone el nombre (nunca correo ni teléfono). Mejora: limitarlo a las contrapartes de reservas propias |
| El tráfico interno entre contenedores va por HTTP sin cifrar | Medio en un clúster compartido | Aceptado en el entorno local; en producción, TLS en el Ingress y malla de servicios o NetworkPolicy |
| No hay recuperación de contraseña ni borrado de cuenta a pedido | La ley da derecho a suprimir datos | Desactivar la cuenta deja de mostrarla; la supresión total requiere un procedimiento manual del administrador (ver política) |
| Los mensajes del chat no se pueden borrar (solo inserción) | Un usuario podría escribir datos personales de más | Se avisa en la política; el texto se limita a 1.000 caracteres y solo lo ven las dos partes. Mejora: borrado a pedido por el administrador |
| El almacén y la auditoría guardan identificadores de usuario para siempre | Trazabilidad frente a derecho de supresión | La auditoría es obligación del RF10; tras una supresión se conserva solo el identificador sin datos que lo vuelvan identificable |

## 4. Cómo repetir la revisión

```bash
python scripts/revisar_seguridad.py --bases
```

Sale con código 1 si encuentra un secreto versionado, una operación de la API sin sesión, una ruta interna sin
token o una columna de datos personales en el almacén.
