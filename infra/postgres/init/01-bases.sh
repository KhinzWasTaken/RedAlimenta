#!/bin/bash
# Crea las cuatro bases (una por servicio) y su rol de aplicación.
# Docker lo ejecuta una sola vez, cuando el volumen de datos está vacío.
set -euo pipefail

crear() {
  local base="$1" rol="$2"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE ${rol} LOGIN PASSWORD '${APP_DB_PASSWORD}';
CREATE DATABASE ${base};
REVOKE ALL ON DATABASE ${base} FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE ${base} TO ${rol};
SQL
}

crear redalimenta_identity     identity_app
crear redalimenta_catalog      catalog_app
crear redalimenta_fulfillment  fulfillment_app
crear redalimenta_notification notification_app

# PostGIS solo en la base del catálogo (las demás no manejan geografía)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname redalimenta_catalog \
  -c "CREATE EXTENSION IF NOT EXISTS postgis;"
