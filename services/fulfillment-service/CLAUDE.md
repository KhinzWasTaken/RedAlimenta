# fulfillment-service

Requerimientos: RF5, RF6, RF8. Base propia: `redalimenta_fulfillment` (sin claves foráneas hacia otras bases, D-06).

## Contenido
- `cumplimiento/modelos.py`: tablas reserva, entrega, confirmacion_entrega. Estados: estado_reserva, estado_entrega, estado_confirmacion (docs/modelo/estados.md).
- `cumplimiento/repositorio.py`: consultas y transacciones; quien llama hace `db.commit()`.
- `cumplimiento/semilla.py`: datos semilla con identificadores fijos (ver `docs/modelo/datos-semilla.md`).
- `migrations/`: migraciones Alembic; el esquema de la base debe coincidir con `modelos.py` (lo prueba `tests/test_esquema.py`).

## Reglas que no se cambian
- D-02: índice único parcial `ux_reserva_activa`; se inserta primero y el perdedor recibe Conflicto (409).
- El estado de la donación no se toca aquí (D-01): las funciones devuelven lo que hay que pedirle a catalog.
- La entrega se completa solo con la confirmación del donante y del receptor.
- `expirar_reservas` es una sola sentencia UPDATE … RETURNING: idempotente (D-09: plazo 2 h).
- Solo las transiciones de `docs/modelo/estados.md`; decisiones D-01 a D-10 en `docs/decisiones/`.

## Cómo ejecutar
```bash
# desde la raíz del repositorio, con infra/docker-compose.yml levantado
python scripts/bd.py migrar
python scripts/probar.py fulfillment
```
Las pruebas crean y borran una base temporal (PRUEBAS_ADMIN_URL, superusuario); nunca usan las bases reales.
