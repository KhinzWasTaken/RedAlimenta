"""Genera la configuración del gateway nginx (S6-03) a partir de infra/rutas.json.

    python scripts/gateway.py            escribe infra/gateway/default.conf.template
    python scripts/gateway.py --revisar  falla si la configuración guardada no coincide con rutas.json

Así el proxy de desarrollo (Vite) y el gateway (Compose y Kubernetes) usan la misma tabla de rutas.
Las variables ${...} las resuelve la imagen oficial de nginx al arrancar (envsubst):
- NGINX_LOCAL_RESOLVERS: el DNS del contenedor (lo calcula la propia imagen).
- DOMINIO_SERVICIOS: sufijo de los nombres de los servicios ("" en Compose,
  ".redalimenta.svc.cluster.local" en Kubernetes, porque el resolver de nginx no usa dominios de búsqueda).
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "infra" / "gateway" / "default.conf.template"

PLANTILLA = """# GENERADO por scripts/gateway.py desde infra/rutas.json. No editar a mano.
# Gateway de RedAlimenta (S6-03): única dirección pública. Sirve el frontend y reparte /api por servicio.
# Las rutas /internal (servicio a servicio, D-01) no se publican.

# S8-06: límite de intentos de inicio de sesión y registro por dirección IP (fuerza bruta)
limit_req_zone $binary_remote_addr zone=autenticacion:10m rate=30r/m;
limit_req_status 429;

map $http_x_correlation_id $correlacion {{
    ""      $request_id;
    default $http_x_correlation_id;
}}

log_format redalimenta '$remote_addr [$time_local] "$request" $status $body_bytes_sent '
                       '${{request_time}}s corr=$correlacion upstream=$upstream_addr';

server {{
    listen 8080;
    server_name _;
    access_log /dev/stdout redalimenta;

    # Detrás de un proxy de la red privada (Caddy en la nube, Ingress en Kubernetes): IP real del cliente,
    # para que el límite de intentos de inicio de sesión sea por persona y no compartido
    set_real_ip_from 10.0.0.0/8;
    set_real_ip_from 172.16.0.0/12;
    set_real_ip_from 192.168.0.0/16;
    real_ip_header X-Forwarded-For;
    real_ip_recursive on;

    resolver ${{NGINX_LOCAL_RESOLVERS}} valid=10s ipv6=off;
    client_max_body_size 1m;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Correlation-Id $correlacion;
    proxy_connect_timeout 3s;
    proxy_read_timeout 30s;
    proxy_hide_header X-Correlation-Id;  # la pone el gateway una sola vez
    add_header X-Correlation-Id $correlacion always;
    # Cabeceras de seguridad (S8-06)
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    add_header Permissions-Policy "geolocation=(self), camera=(), microphone=()" always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'" always;
    server_tokens off;

    location = /salud {{
        default_type application/json;
        return 200 '{{"estado":"ok","servicio":"gateway"}}';
    }}

    # Rutas internas entre servicios: nunca desde afuera
    location ^~ /internal {{
        default_type application/json;
        return 404 '{{"detail":"Recurso no encontrado"}}';
    }}

    # Coincidencia exacta (=): tiene prioridad sobre el prefijo ^~ /api/auth; una expresión regular no la tendría
    location = /api/auth/login {{
        limit_req zone=autenticacion burst=20 nodelay;
        set $destino http://identity${{DOMINIO_SERVICIOS}}:8000;
        proxy_pass $destino;
    }}

    location = /api/auth/registro {{
        limit_req zone=autenticacion burst=20 nodelay;
        set $destino http://identity${{DOMINIO_SERVICIOS}}:8000;
        proxy_pass $destino;
    }}

{rutas}
    location ^~ /api/ {{
        default_type application/json;
        return 404 '{{"detail":"Recurso no encontrado"}}';
    }}

    # Frontend compilado (SPA): cualquier otra ruta devuelve index.html
    location / {{
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }}
}}
"""


def generar() -> str:
    servicios = json.loads((RAIZ / "infra" / "rutas.json").read_text(encoding="utf-8"))["servicios"]
    bloques = []
    pares = sorted(((p, n) for n, s in servicios.items() for p in s["prefijos"]), key=lambda x: -len(x[0]))
    for prefijo, nombre in pares:
        bloques.append(
            f"    location ^~ {prefijo} {{\n"
            f"        set $destino http://{nombre}${{DOMINIO_SERVICIOS}}:8000;\n"
            f"        proxy_pass $destino;\n"
            f"    }}\n")
    return PLANTILLA.format(rutas="\n".join(bloques))


def main(argv: list[str]) -> int:
    texto = generar()
    if "--revisar" in argv:
        if not DESTINO.exists() or DESTINO.read_text(encoding="utf-8") != texto:
            print("✗ infra/gateway/default.conf.template no coincide con infra/rutas.json")
            return 1
        print("✓ Gateway al día con infra/rutas.json")
        return 0
    DESTINO.write_text(texto, encoding="utf-8")
    print(f"» {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
