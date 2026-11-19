#!/usr/bin/env bash
# Crea en Azure la máquina de RedAlimenta y la deja publicada con HTTPS. Se ejecuta en Azure Cloud Shell (Bash):
#
#   curl -fsSL https://raw.githubusercontent.com/KhinzWasTaken/RedAlimenta/main/scripts/nube/azure.sh | bash
#
# Si el repositorio es privado, primero `export GITHUB_TOKEN=...` (token de solo lectura del repositorio) y
# descarga el script con la API (ver docs/manuales/despliegue-azure.md).
#
# Variables opcionales: GRUPO (redalimenta), VM (redalimenta-vm), REGIONES, TAMANOS, CLAVE_DEMO, RAMA (main),
# GITHUB_TOKEN (repositorio privado).
# Al final muestra el enlace y la contraseña de los usuarios de demostración.
set -euo pipefail

GRUPO="${GRUPO:-redalimenta}"
VM="${VM:-redalimenta-vm}"
RAMA="${RAMA:-main}"
# Azure for Students solo permite algunas regiones y tamaños; se prueban en orden hasta que uno funcione
REGIONES="${REGIONES:-eastus eastus2 southcentralus westus2 westus3 centralus brazilsouth canadacentral}"
TAMANOS="${TAMANOS:-Standard_B2s Standard_B2als_v2 Standard_B2as_v2 Standard_D2as_v5}"
IMAGEN="Canonical:ubuntu-24_04-lts:server:latest"
TOKEN="${GITHUB_TOKEN:-}"
if [ -n "$TOKEN" ]; then  # repositorio privado: se descarga por la API con el token
  DESCARGA="curl -fsSL -H 'Authorization: Bearer $TOKEN' -H 'Accept: application/vnd.github.raw' 'https://api.github.com/repos/KhinzWasTaken/RedAlimenta/contents/scripts/nube/instalar.sh?ref=$RAMA'"
else
  DESCARGA="curl -fsSL 'https://raw.githubusercontent.com/KhinzWasTaken/RedAlimenta/$RAMA/scripts/nube/instalar.sh'"
fi
paso() { printf '\n== %s\n' "$*"; }

az account show --query "{suscripcion:name, usuario:user.name}" -o tsv >/dev/null \
  || { echo "Inicia sesión primero (en Cloud Shell ya estás dentro)."; exit 1; }
az provider register -n Microsoft.Compute --wait >/dev/null 2>&1 || true
az provider register -n Microsoft.Network --wait >/dev/null 2>&1 || true

if az vm show -g "$GRUPO" -n "$VM" >/dev/null 2>&1; then
  paso "La máquina $VM ya existe: se actualiza la aplicación"
  az vm start -g "$GRUPO" -n "$VM" >/dev/null
else
  creada=""
  for region in $REGIONES; do
    for tamano in $TAMANOS; do
      paso "Creando $VM ($tamano) en $region"
      az group create -n "$GRUPO" -l "$region" -o none 2>/dev/null || { echo "  región no permitida"; break; }
      if az vm create -g "$GRUPO" -n "$VM" -l "$region" --image "$IMAGEN" --size "$tamano" \
          --admin-username azureuser --generate-ssh-keys --public-ip-sku Standard \
          --os-disk-size-gb 30 -o none 2> /tmp/error-vm.txt; then
        creada="$region/$tamano"; break 2
      fi
      echo "  no disponible: $(grep -m1 -oE '(SkuNotAvailable|RequestDisallowedByPolicy|QuotaExceeded|[A-Za-z]+Error)' /tmp/error-vm.txt || echo error)"
      az group delete -n "$GRUPO" --yes -o none 2>/dev/null || true
    done
  done
  [ -n "$creada" ] || { echo "No se pudo crear la máquina en ninguna región o tamaño permitido."; cat /tmp/error-vm.txt; exit 1; }
  echo "  creada en $creada"
  paso "Abriendo los puertos 80 y 443"
  az vm open-port -g "$GRUPO" -n "$VM" --port 80,443 --priority 900 -o none
fi

IP=$(az vm show -d -g "$GRUPO" -n "$VM" --query publicIps -o tsv)
DOMINIO="${IP//./-}.sslip.io"
paso "Instalando RedAlimenta en $IP"
# Corre como servicio en la máquina: sigue aunque Cloud Shell se desconecte
VARIABLES="RAMA=$RAMA DOMINIO=$DOMINIO"
[ -n "${CLAVE_DEMO:-}" ] && VARIABLES="$VARIABLES CLAVE_DEMO=$CLAVE_DEMO"
[ -n "$TOKEN" ] && VARIABLES="$VARIABLES GITHUB_TOKEN=$TOKEN"
az vm run-command invoke -g "$GRUPO" -n "$VM" --command-id RunShellScript -o none --scripts "
  $DESCARGA -o /root/instalar.sh || { echo 'No se pudo descargar instalar.sh (¿repositorio privado sin GITHUB_TOKEN?)'; exit 1; }
  systemctl reset-failed redalimenta-instalacion 2>/dev/null || true
  systemd-run --unit redalimenta-instalacion --collect \
    bash -c '$VARIABLES bash /root/instalar.sh > /var/log/redalimenta-instalacion.log 2>&1'"

echo "Construyendo (la primera vez tarda entre 10 y 20 minutos). Esperando a https://$DOMINIO ..."
listo=""
for _ in $(seq 1 90); do
  if curl -fsS --max-time 5 "https://$DOMINIO/salud" >/dev/null 2>&1; then listo=1; break; fi
  printf '.'; sleep 20
done
echo
CLAVE=$(az vm run-command invoke -g "$GRUPO" -n "$VM" --command-id RunShellScript \
  --scripts "grep '^CLAVE_DEMO=' /opt/redalimenta/infra/.env | cut -d= -f2" --query "value[0].message" -o tsv \
  | sed -n '/\[stdout\]/{n;p;}' | head -1)
if [ -n "$listo" ]; then
  cat <<LISTO

==============================================================
 RedAlimenta en línea
 Enlace:      https://$DOMINIO
 Contraseña de los usuarios de demostración: $CLAVE
 (admin@redalimenta.co, donante@redalimenta.co, receptor.medellin@redalimenta.co ...)
==============================================================
LISTO
else
  cat <<ESPERA

Aún no responde. La instalación sigue en la máquina; para ver cómo va:
  az vm run-command invoke -g $GRUPO -n $VM --command-id RunShellScript --scripts "tail -n 30 /var/log/redalimenta-instalacion.log" --query "value[0].message" -o tsv
Cuando termine, el enlace será https://$DOMINIO (contraseña: $CLAVE)
ESPERA
fi

cat <<FIN

Para apagar la máquina después de la presentación (deja de cobrar el cómputo):
  az vm deallocate -g $GRUPO -n $VM
Para encenderla otra vez:
  az vm start -g $GRUPO -n $VM
Para borrarlo todo:
  az group delete -n $GRUPO --yes
FIN
