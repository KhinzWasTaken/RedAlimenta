# Guía de despliegue en Kubernetes local

Probada la validez de los manifiestos contra Kubernetes 1.31 (`kubeconform`). Requiere Docker y un clúster
local: **Kubernetes de Docker Desktop** (lo más sencillo en Windows y macOS) o **kind**.

## 1. Preparar

1. Instala Docker Desktop. En *Settings → Kubernetes* marca **Enable Kubernetes** y espera a que diga
   *running*. (Con kind: `kind create cluster --name redalimenta --config scripts/kind.yaml`.)
2. Comprueba que `kubectl` apunta al clúster:

   ```bash
   kubectl config current-context
   ```

   Debe decir `docker-desktop` (o `kind-redalimenta`).
3. Ten `infra/.env` creado con todas las claves (copia de `infra/.env.example`) y las dependencias de
   Python instaladas (`pip install -r requirements-dev.txt`).

## 2. Construir las imágenes

```bash
python scripts/k8s.py imagenes
```

Construye `redalimenta/{identity,catalog,fulfillment,notification,analytics,herramientas,gateway}:local`.
En Docker Desktop el clúster usa directamente las imágenes locales; con kind el script las carga en el nodo.

## 3. Desplegar

```bash
python scripts/k8s.py desplegar
```

El script crea el namespace `redalimenta`, el Secret `redalimenta-secretos` desde `infra/.env` (nunca se
guarda en el repositorio) y el ConfigMap con el script de inicio de PostgreSQL; aplica `infra/k8s/` con
kustomize y espera, en orden: PostgreSQL, RabbitMQ, el Job de migraciones, la carga inicial del almacén y los
Deployments. Al final muestra los pods.

Abre **http://localhost:30080** (NodePort del gateway).

## 4. Qué queda desplegado

| Recurso | Detalle |
| --- | --- |
| `StatefulSet/postgres` + PVC | PostGIS 16 con las seis bases |
| `Deployment/rabbitmq` | Broker de eventos |
| `Job/migraciones` | Esquemas y datos semilla |
| `Deployment` + `Service` por servicio | catalog y fulfillment con **2 réplicas** y `PodDisruptionBudget`; sondas `/salud` (readiness) y `/vivo` (liveness); sin root |
| `CronJob/tareas-fulfillment` | Cada minuto: expirar, vencer, avisar, conciliar (`concurrencyPolicy: Forbid`) |
| `Job/etl-carga-inicial`, `CronJob/etl-eventos`, `CronJob/etl-historica` | Almacén: carga inicial, continua cada 10 min y completa cada noche |
| `Deployment/gateway` + `Service` NodePort 30080 + `Ingress` | Única entrada pública |
| `ConfigMap/redalimenta-config`, `Secret/redalimenta-secretos` | Configuración y secretos |

## 5. Comprobar

```bash
python scripts/k8s.py probar
```

Corre el flujo completo por el gateway, 20 reservas simultáneas contra las dos réplicas de fulfillment
(una 201 y 19 con 409) y borra un pod de catalog mientras se consulta, para mostrar que el servicio sigue
respondiendo. Comandos útiles:

```bash
kubectl -n redalimenta get pods,jobs,cronjobs
```

```bash
kubectl -n redalimenta logs deployment/fulfillment --tail=50
```

## 6. Borrar

```bash
python scripts/k8s.py borrar
```

Elimina el namespace completo, incluidos los datos.

## Problemas frecuentes

| Síntoma | Causa y solución |
| --- | --- |
| Pods en `ErrImageNeverPull` / `ImagePullBackOff` | Las imágenes no están en el clúster: repite `python scripts/k8s.py imagenes` (con kind, el clúster debe llamarse `redalimenta`) |
| `Job/migraciones` falla al principio | PostgreSQL aún arranca; el Job se reintenta solo (`backoffLimit: 6`) |
| `localhost:30080` no responde con kind | Crea el clúster con `scripts/kind.yaml`, que publica ese puerto |
| Gateway responde 502 | Algún servicio aún no está listo: `kubectl -n redalimenta get pods` |
