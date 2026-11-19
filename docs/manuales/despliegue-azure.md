# Publicar RedAlimenta en Azure for Students

Deja la aplicación en un enlace público con HTTPS (por ejemplo `https://20-30-40-50.sslip.io`) que funciona
aunque tu computador esté apagado. Todo se hace desde el navegador, sin instalar nada.

**Qué se crea:** una máquina virtual Ubuntu 24.04 (2 CPU y 4 GB de RAM, tamaño `Standard_B2s` o equivalente) en
el grupo de recursos `redalimenta`, con el mismo `docker compose` del proyecto más Caddy, que obtiene el
certificado HTTPS automáticamente. Solo quedan abiertos los puertos 22 (SSH), 80 y 443; la base de datos y
RabbitMQ no se exponen.

## 1. Crear y publicar (una sola vez, 15–25 minutos)

1. Entra a [portal.azure.com](https://portal.azure.com) con tu cuenta de Azure for Students.
2. Abre **Cloud Shell**: el icono `>_` de la barra superior. Elige **Bash**. Si pregunta por almacenamiento,
   elige **No se requiere cuenta de almacenamiento** (o la opción que crea uno por defecto).
3. Pega este comando y pulsa Enter:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/KhinzWasTaken/RedAlimenta/main/scripts/nube/azure.sh | bash
   ```

   Para elegir tú la contraseña de los usuarios de demostración en vez de una al azar:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/KhinzWasTaken/RedAlimenta/main/scripts/nube/azure.sh | CLAVE_DEMO='TuClave2026' bash
   ```

4. El script prueba regiones y tamaños permitidos para estudiantes hasta crear la máquina, abre los puertos,
   lanza la instalación en la máquina y espera a que el enlace responda. Al final muestra:

   ```
   RedAlimenta en línea
   Enlace:      https://20-30-40-50.sslip.io
   Contraseña de los usuarios de demostración: ...
   ```

   Si Cloud Shell se desconecta mientras espera, la instalación **sigue** en la máquina. Vuelve a pegar el
   mismo comando: detecta que la máquina existe y te muestra el enlace y la contraseña.

5. Abre el enlace. Los usuarios son los de siempre (`admin@redalimenta.co`, `donante@redalimenta.co`,
   `receptor.medellin@redalimenta.co`, … ver `docs/guion-demo.md`) con la contraseña que mostró el script.
   El tablero del administrador tiene datos unos 30 segundos después de cada arranque.

## 2. Antes y después de la presentación

| Qué | Comando en Cloud Shell |
| --- | --- |
| Apagar la máquina (deja de cobrar el cómputo; los datos se conservan) | `az vm deallocate -g redalimenta -n redalimenta-vm` |
| Encenderla de nuevo (la aplicación arranca sola en 1–2 minutos; el enlace es el mismo) | `az vm start -g redalimenta -n redalimenta-vm` |
| Actualizar a la última versión de `main` | volver a pegar el comando del paso 1 |
| Ver el registro de la instalación | `az vm run-command invoke -g redalimenta -n redalimenta-vm --command-id RunShellScript --scripts "tail -n 40 /var/log/redalimenta-instalacion.log" --query "value[0].message" -o tsv` |
| Entrar por SSH (las llaves quedaron en Cloud Shell) | `ssh azureuser@<ip>` y luego `cd /opt/redalimenta` |
| Borrar todo al terminar el semestre | `az group delete -n redalimenta --yes` |

**Costo aproximado** (revísalo en *Cost Management* del portal): una B2s encendida cuesta del orden de
30–40 USD al mes; apagada con `deallocate` solo se pagan el disco y la IP pública, unos pocos dólares al mes.
Con el crédito de estudiante alcanza de sobra si la apagas cuando no la uses.

## 3. Seguridad de la demostración

- Cualquiera con el enlace puede intentar entrar. Por eso la contraseña de los usuarios de demostración ya
  **no es `demo123`**: el script genera una al azar (o usa `CLAVE_DEMO`). Compártela solo con tu docente.
- El inicio de sesión se bloquea temporalmente (429) tras unos 20 intentos fallidos seguidos desde la misma IP.
- Los secretos (contraseñas de la base, JWT, token interno) se generan en la máquina, en
  `/opt/redalimenta/infra/.env`, y nunca pasan por el repositorio.
- El botón de demostración **⏱ Forzar expiración** sigue activo para poder mostrar las tareas automáticas.

## Problemas frecuentes

| Síntoma | Qué hacer |
| --- | --- |
| "No se pudo crear la máquina en ninguna región o tamaño permitido" | Tu suscripción limita regiones. En el portal busca **Directivas → Ubicaciones permitidas**, y ejecuta con esas regiones: `... \| REGIONES="eastus2 westeurope" bash` |
| El enlace no abre o el navegador dice que no es seguro | El certificado tarda 1–2 minutos la primera vez. Si sigue, revisa que los puertos 80 y 443 estén abiertos: `az vm open-port -g redalimenta -n redalimenta-vm --port 80,443 --priority 900` |
| `QuotaExceeded` | La suscripción de estudiante tiene un límite de núcleos; borra otras máquinas o usa `TAMANOS="Standard_B2s"` en otra región |
| La página carga pero no deja entrar | Usa la contraseña que mostró el script (no `demo123`). Para verla: `az vm run-command invoke -g redalimenta -n redalimenta-vm --command-id RunShellScript --scripts "grep CLAVE_DEMO /opt/redalimenta/infra/.env" --query "value[0].message" -o tsv` |

## Detalle técnico

- `scripts/nube/azure.sh`: crea el grupo, la máquina y los puertos con la CLI de Azure, y lanza la instalación
  como servicio de systemd en la máquina (`az vm run-command`).
- `scripts/nube/instalar.sh`: en la máquina, agrega 2 GB de memoria de intercambio, instala Docker, clona el
  repositorio en `/opt/redalimenta`, crea `infra/.env` con secretos al azar y el dominio `<ip>.sslip.io`, y
  levanta `infra/docker-compose.yml` + `infra/docker-compose.nube.yml`. Sirve para cualquier servidor Ubuntu.
- `infra/docker-compose.nube.yml`: agrega Caddy (puertos 80 y 443, `infra/caddy/Caddyfile`), deja el gateway en
  `127.0.0.1` y reinicia todo solo si la máquina se reinicia. El gateway toma la IP real del cliente desde
  `X-Forwarded-For` para que el límite de intentos sea por persona.
