# analytics-service

Requerimientos: RF10 (historial y trazabilidad); RF9 (indicadores) en los Sprints 7 y 8.
Base propia: `redalimenta_analytics`.

## Contenido
- `analitica/modelos.py`: `historial_evento`, copia fiel de cada evento publicado. No es una entidad del Sprint 3:
  es el registro de eventos que el documento asigna a analytics y la fuente de la carga continua del almacén (S7-05).
- `analitica/consumidor.py`: consume `#` en la cola `analytics.historial`; idempotente por `id_evento`.
- `analitica/rutas.py` (puerto 8005): `/api/historial/entidades/{entidad}` y `/api/historial/usuarios/{id}`, solo administrador.

## Reglas que no se cambian
- `historial_evento` es de solo inserción (trigger + REVOKE UPDATE/DELETE al rol `analytics_app`).
- Un evento repetido (mismo `id_evento`) no crea otra fila.

## Cómo ejecutar
```bash
python scripts/levantar.py
python scripts/probar.py analytics
```
