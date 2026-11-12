# notification-service

Requerimientos: RF7. Base propia: `redalimenta_notification` (sin claves foráneas hacia otras bases, D-06).

## Contenido
- `notificaciones/modelos.py`: tablas notificacion. Estados: estado_notificacion (NO_LEIDA, LEIDA, ARCHIVADA).
- `notificaciones/repositorio.py`: consultas y transacciones; quien llama hace `db.commit()`.
- `notificaciones/semilla.py`: datos semilla con identificadores fijos (ver `docs/modelo/datos-semilla.md`).
- `migrations/`: migraciones Alembic; el esquema de la base debe coincidir con `modelos.py` (lo prueba `tests/test_esquema.py`).

## Reglas que no se cambian
- No hay notificación sin usuario ni mensaje; el contenido no cambia después de creada.
- El rol de aplicación solo puede actualizar `estado_notificacion` y `fecha_lectura`.
- Un usuario solo ve y modifica sus propias notificaciones.
- Solo las transiciones de `docs/modelo/estados.md`; decisiones D-01 a D-10 en `docs/decisiones/`.

## Cómo ejecutar
```bash
# desde la raíz del repositorio, con infra/docker-compose.yml levantado
python scripts/bd.py migrar
python scripts/probar.py notification
```
Las pruebas crean y borran una base temporal (PRUEBAS_ADMIN_URL, superusuario); nunca usan las bases reales.
