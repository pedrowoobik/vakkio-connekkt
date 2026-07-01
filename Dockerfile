# Vakkio Connekkt · agente local en contenedor. Corre en cualquier caja Linux 24/7
# (NAS, router, mini-PC, Home Assistant) — sin necesidad de una Raspberry dedicada.
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Vakkio Connekkt" \
      org.opencontainers.image.description="Agente local de Vakkio: descubre y monitoriza dispositivos y los envía a Vakkio." \
      org.opencontainers.image.source="https://github.com/pedrowoobik/vakkio-connekkt" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app
RUN pip install --no-cache-dir tinytuya requests

COPY vakkio_collector.py provision.py docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

# el token y la caché viven en el volumen /data (sobreviven reinicios)
ENV VAKKIO_ENV=/data/vakkio.env
VOLUME ["/data"]

ENTRYPOINT ["./docker-entrypoint.sh"]
