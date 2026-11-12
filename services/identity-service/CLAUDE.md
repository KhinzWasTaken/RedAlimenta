# identity-service

Requerimientos: RF1, RF10. Base propia: `redalimenta_identity` (sin claves foráneas hacia otras bases, D-06).

## Contenido
- `identidad/modelos.py`: tablas rol, usuario, verificacion_usuario, registro_auditoria. Estados: estado_cuenta (ACTIVA, DESACTIVADA), estado_verificacion (PENDIENTE, APROBADA, RECHAZADA).
- `identidad/repositorio.py`: consultas y transacciones; quien llama hace `db.commit()`.
- `identidad/semilla.py`: datos semilla con identificadores fijos (ver `docs/modelo/datos-semilla.md`).
- `migrations/`: migraciones Alembic; el esquema de la base debe coincidir con `modelos.py` (lo prueba `tests/test_esquema.py`).

## Reglas que no se cambian
- Una verificación resuelta no cambia (trigger `trg_verificacion_validar`); solo un ADMINISTRADOR resuelve.
- `registro_auditoria` es de solo inserción: trigger + REVOKE UPDATE/DELETE al rol de aplicación (D-04).
- Correo único sin distinguir mayúsculas; desactivar no borra la fila.
- Contraseñas con PBKDF2-SHA256; nunca en claro ni en logs.
- Solo las transiciones de `docs/modelo/estados.md`; decisiones D-01 a D-10 en `docs/decisiones/`.

## Cómo ejecutar
```bash
# desde la raíz del repositorio, con infra/docker-compose.yml levantado
python scripts/bd.py migrar
python scripts/probar.py identity
```
Las pruebas crean y borran una base temporal (PRUEBAS_ADMIN_URL, superusuario); nunca usan las bases reales.
