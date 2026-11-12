# catalog-geo-service

Requerimientos: RF2, RF3, RF4. Base propia: `redalimenta_catalog` (sin claves foráneas hacia otras bases, D-06).

## Contenido
- `catalogo/modelos.py`: tablas categoria_alimento, ubicacion_geografica, donacion, necesidad_alimentaria. Estados: estado_donacion, estado_necesidad, nivel_urgencia (docs/modelo/estados.md).
- `catalogo/repositorio.py`: consultas y transacciones; quien llama hace `db.commit()`.
- `catalogo/semilla.py`: datos semilla con identificadores fijos (ver `docs/modelo/datos-semilla.md`).
- `migrations/`: migraciones Alembic; el esquema de la base debe coincidir con `modelos.py` (lo prueba `tests/test_esquema.py`).

## Reglas que no se cambian
- D-01: solo este servicio cambia `estado_donacion`, siempre con `repositorio.transicionar_donacion`; la base también valida (`trg_donacion_validar`).
- Una donación solo se modifica DISPONIBLE; una necesidad, ABIERTA y por su receptor.
- Ubicación como `geography(Point, 4326)` con índice GIST; distancias en metros con ST_Distance/ST_DWithin.
- Puntaje D-08 en SQL (`repositorio.buscar_donaciones`), pesos en `catalogo/config.py`.
- Solo las transiciones de `docs/modelo/estados.md`; decisiones D-01 a D-10 en `docs/decisiones/`.

## Cómo ejecutar
```bash
# desde la raíz del repositorio, con infra/docker-compose.yml levantado
python scripts/bd.py migrar
python scripts/probar.py catalog
```
Las pruebas crean y borran una base temporal (PRUEBAS_ADMIN_URL, superusuario); nunca usan las bases reales.
