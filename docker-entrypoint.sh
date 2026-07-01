#!/bin/sh
# Vakkio Connekkt · arranque en Docker:
#   1) si no hay token (primer arranque), canjea el PAIRING_CODE por él;
#   2) arranca el colector (control-plane: inventario + config + ingesta).
# La config llega por variables de entorno (ver docker-compose.yml / .env).
set -e

: "${VAKKIO_ENV:=/data/vakkio.env}"
mkdir -p "$(dirname "$VAKKIO_ENV")"

if [ ! -f "$VAKKIO_ENV" ]; then
  echo "· primer arranque: emparejando con el código…"
  python /app/provision.py --no-service
fi

echo "· arrancando colector"
exec python /app/vakkio_collector.py
