#!/usr/bin/env bash
# Crea en Azure la máquina de RedAlimenta y la deja publicada con HTTPS. Se ejecuta en Azure Cloud Shell (Bash):
#
#   curl -fsSL https://raw.githubusercontent.com/KhinzWasTaken/RedAlimenta/main/scripts/nube/azure.sh | bash
#
# Si el repositorio es privado, primero `export GITHUB_TOKEN=...` (token de solo lectura del repositorio) y
# descarga el script con la API (ver docs/manuales/despliegue-azure.md).
#
# Variables opcionales: GRUPO (redalimenta), VM (redalimenta-vm), REGIONES (+ REGIONES_FIJAS=1 para no
# consultar las permitidas), TAMANOS, CLAVE_DEMO, RAMA (main),
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

# Regiones permitidas por la directiva de la suscripción (Azure for Students limita a unas pocas)
permitidas=$(az policy assignment list --query "[].parameters.listOfAllowedLocations.value[]" -o tsv 2>/dev/null \
  | tr '[:upper:]' '[:lower:]' | sort -u | tr '\n' ' ')
if [ -z "${REGIONES_FIJAS:-}" ] && [ -n "$permitidas" ]; then
  echo "Regiones permitidas por tu suscripción: $permitidas"
  orden=""
  for r in $REGIONES; do case " $permitidas " in *" $r "*) orden="$orden $r";; esac; done
  for r in $permitidas; do case " $orden " in *" $r "*) ;; *) orden="$orden $r";; esac; done
  REGIONES="$orden"
fi

mostrar_error() {  # el mensaje real de Azure, sin la traza
  grep -vE '^\s*$|Traceback|File "|^\s+' /tmp/error-vm.txt | head -n 6 | sed 's/^/    /'
}

if az vm show -g "$GRUPO" -n "$VM" >/dev/null 2>&1; then
  paso "La máquina $VM ya existe: se actualiza la aplicación"
  az vm start -g "$GRUPO" -n "$VM" >/dev/null
else
  if az group show -n "$GRUPO" >/dev/null 2>&1; then
    paso "Borrando restos de un intento anterior (grupo $GRUPO sin máquina)"
    az group delete -n "$GRUPO" --yes -o none
  fi
  creada=""
  for region in $REGIONES; do
    # Tamaños sin restricciones para esta suscripción en la región (evita intentos que fallarán)
    disponibles=$(az vm list-skus -l "$region" --resource-type virtualMachines \
      --query "[?length(restrictions)==\`0\`].name" -o tsv 2>/dev/null | tr '\n' ' ')
    tamano=""
    for t in $TAMANOS; do case " $disponibles " in *" $t "*) tamano=$t; break;; esac; done
    if [ -z "$tamano" ]; then echo "  $region: ninguno de los tamaños ($TAMANOS) está disponible"; continue; fi
    paso "Creando $VM ($tamano) en $region"
    az group create -n "$GRUPO" -l "$region" -o none 2> /tmp/error-vm.txt || { echo "  región no permitida:"; mostrar_error; continue; }
    if az vm create -g "$GRUPO" -n "$VM" -l "$region" --image "$IMAGEN" --size "$tamano" \
        --admin-username azureuser --generate-ssh-keys --public-ip-sku Standard \
        --os-disk-size-gb 30 -o none 2> /tmp/error-vm.txt; then
      creada="$region/$tamano"; break
    fi
    echo "  falló:"; mostrar_error
    if grep -q "already consumed" /tmp/error-vm.txt; then
      # Error de la propia CLI que tapa el mensaje de Azure: se lee del despliegue fallido
      az deployment group list -g "$GRUPO" --query "[?properties.provisioningState=='Failed'].properties.error" \
        -o json 2>/dev/null | tee -a /tmp/error-vm.txt | grep -E '"(code|message)"' | head -n 6 | sed 's/^ */    /'
    fi
    az group delete -n "$GRUPO" --yes -o none 2>/dev/null || true
    # Si no es un problema de capacidad o de región, probar otras regiones no ayuda
    if ! grep -qE 'SkuNotAvailable|AllocationFailed|ZonalAllocationFailed|OverconstrainedAllocationRequest|RequestDisallowedByPolicy|QuotaExceeded|NotAvailableForSubscription|already consumed' /tmp/error-vm.txt; then
      echo; echo "Error no relacionado con la región; se detiene. Copia el mensaje de arriba (completo en /tmp/error-vm.txt)."
      exit 1
    fi
  done
  [ -n "$creada" ] || { echo "No se pudo crear la máquina en ninguna región permitida."; exit 1; }
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
