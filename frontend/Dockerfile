# Gateway de RedAlimenta (S6-01, S6-03): compila el frontend y lo sirve con nginx, que además reparte
# /api a cada servicio según infra/rutas.json. Se construye desde la raíz del repositorio:
#   docker build -f frontend/Dockerfile -t redalimenta/gateway .
FROM node:22-alpine AS compilacion
WORKDIR /repo
COPY infra/rutas.json infra/rutas.json
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund
COPY frontend frontend
RUN cd frontend && npm run build

FROM nginx:1.27-alpine
# La imagen oficial corre como root solo para abrir el puerto; aquí escucha en 8080 y corre como usuario nginx
RUN chown -R nginx:nginx /var/cache/nginx /etc/nginx/conf.d /usr/share/nginx/html \
 && touch /var/run/nginx.pid && chown nginx:nginx /var/run/nginx.pid \
 && sed -i '/^user /d' /etc/nginx/nginx.conf
COPY infra/gateway/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=compilacion /repo/frontend/dist /usr/share/nginx/html
ENV DOMINIO_SERVICIOS="" NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/salud || exit 1
