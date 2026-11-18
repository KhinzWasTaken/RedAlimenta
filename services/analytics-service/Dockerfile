# analytics-service · imagen del servicio (S6-01). Se construye desde la carpeta services/:
#   docker build -f analytics-service/Dockerfile -t redalimenta/analytics .
# Sin secretos: la configuración (DATABASE_URL, RABBITMQ_URL, JWT_SECRETO, TOKEN_INTERNO...) llega por variables.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY comun /opt/comun
RUN pip install /opt/comun
COPY analytics-service/requirements.txt .
RUN pip install -r requirements.txt
COPY analytics-service/ .

USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/vivo', timeout=2)"
CMD ["uvicorn", "analitica.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
