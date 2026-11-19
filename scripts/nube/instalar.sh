#!/usr/bin/env bash
# Instala o actualiza RedAlimenta en un servidor Ubuntu (22.04 o 24.04) con HTTPS. Se ejecuta como root.
#
#   curl -fsSL https://raw.githubusercontent.com/KhinzWasTaken/RedAlimenta/main/scripts/nube/instalar.sh | sudo bash
#
# Variables opcionales:
#   RAMA        rama del repositorio (main)
#   DOMINIO     nombre público; por defecto <ip-publica>.sslip.io (no hay que comprar dominio)
#   CLAVE_DEMO  contraseña de los usuarios de demostración; por defecto una al azar
#   GITHUB_TOKEN  token de solo lectura si el repositorio es privado (no se guarda en el servidor)
#
# Es idempotente: si se vuelve a ejecutar, trae la última versión y reconstruye sin borrar los datos.
set -euo pipefail

REPO="https://github.com/KhinzWasTaken/RedAlimenta.git"
RAMA="${RAMA:-main}"
DIR=/opt/redalimenta
ENV="$DIR/infra/.env"
paso() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "Ejecuta como root (sudo)."; exit 1; }
export DEBIAN_FRONTEND=noninteractive

paso "Memoria de intercambio (2 GB) para que la compilación no se quede sin RAM"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

paso "Docker"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq ca-certificates curl git openssl >/dev/null
  curl -fsSL https://get.docker.com | sh >/dev/null
fi
systemctl enable --now docker >/dev/null
command -v git >/dev/null || apt-get install -y -qq git >/dev/null

paso "Código ($RAMA)"
GIT=(git)
if [ -n "${GITHUB_TOKEN:-}" ]; then  # la cabecera solo vale para este comando; el token no queda en .git/config
  GIT=(git -c "http.extraHeader=Authorization: Basic $(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w0)")
fi
if [ -d "$DIR/.git" ]; then
  "${GIT[@]}" -C "$DIR" fetch -q origin "$RAMA" && git -C "$DIR" checkout -q "$RAMA" \
    && git -C "$DIR" reset -q --hard "origin/$RAMA"
else
  "${GIT[@]}" clone -q --branch "$RAMA" "$REPO" "$DIR" \
    || { echo "No se pudo clonar $REPO: si es privado, define GITHUB_TOKEN."; exit 1; }
fi

paso "Configuración (infra/.env)"
if [ -z "${DOMINIO:-}" ]; then
  IP=$(curl -fsS --max-time 5 -H Metadata:true \
    "http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/publicIpAddress?api-version=2021-02-01&format=text" || true)
  [ -n "$IP" ] || IP=$(curl -fsS --max-time 10 https://api.ipify.org)
  DOMINIO="${IP//./-}.sslip.io"
fi
fijar() {  # fijar CLAVE VALOR: reemplaza o agrega la línea en infra/.env
  if grep -q "^$1=" "$ENV"; then sed -i "s|^$1=.*|$1=$2|" "$ENV"; else echo "$1=$2" >> "$ENV"; fi
}
if [ ! -f "$ENV" ]; then
  cp "$DIR/infra/.env.example" "$ENV"
  for clave in POSTGRES_PASSWORD APP_DB_PASSWORD RABBITMQ_PASSWORD; do fijar "$clave" "$(openssl rand -hex 16)"; done
  for clave in JWT_SECRETO TOKEN_INTERNO; do fijar "$clave" "$(openssl rand -hex 32)"; done
  fijar CLAVE_DEMO "${CLAVE_DEMO:-$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 10)}"
fi
[ -n "${CLAVE_DEMO:-}" ] && fijar CLAVE_DEMO "$CLAVE_DEMO"
fijar DOMINIO "$DOMINIO"
fijar GATEWAY_PORT "127.0.0.1:8080"
chmod 600 "$ENV"

paso "Construir y levantar (la primera vez tarda entre 5 y 15 minutos)"
cd "$DIR"
docker compose -f infra/docker-compose.yml -f infra/docker-compose.nube.yml --env-file infra/.env \
  --profile app up -d --build --wait --remove-orphans

paso "Comprobar HTTPS"
for _ in $(seq 1 30); do
  curl -fsS --max-time 5 "https://$DOMINIO/salud" >/dev/null 2>&1 && break
  sleep 4
done
if curl -fsS --max-time 5 "https://$DOMINIO/salud" >/dev/null 2>&1; then ESTADO="en línea"; else
  ESTADO="aún sin certificado (revisa que los puertos 80 y 443 estén abiertos y vuelve a probar en un minuto)"; fi

CLAVE=$(grep '^CLAVE_DEMO=' "$ENV" | cut -d= -f2)
cat <<FIN

==============================================================
 RedAlimenta $ESTADO
 Enlace:      https://$DOMINIO
 Usuarios:    admin@redalimenta.co, donante@redalimenta.co,
              receptor.medellin@redalimenta.co ... (docs/guion-demo.md)
 Contraseña:  $CLAVE
==============================================================
FIN
