# Imagen de herramientas: migraciones de las seis bases, datos semilla y ETL del almacén (Sprint 7).
# En Compose corre una vez antes de los servicios; en Kubernetes es un Job (y los CronJob del ETL).
#   docker build -f infra/herramientas/Dockerfile -t redalimenta/herramientas .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY services/comun /app/services/comun
RUN pip install /app/services/comun "SQLAlchemy>=2.0" "alembic>=1.13" "psycopg[binary]>=3.2" "GeoAlchemy2>=0.15"
COPY services /app/services
COPY scripts /app/scripts
COPY dwh /app/dwh
COPY infra/rutas.json /app/infra/rutas.json

USER app
# MODO: "migrar" (solo esquema) o "migrar-y-sembrar" (esquema + datos semilla si las tablas están vacías)
ENV MODO=migrar-y-sembrar
CMD ["sh", "-c", "python scripts/bd.py migrar && if [ \"$MODO\" = migrar-y-sembrar ]; then python scripts/bd.py sembrar; fi"]
