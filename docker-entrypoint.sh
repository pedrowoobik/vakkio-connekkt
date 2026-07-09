#!/bin/sh
# Vakkio Connekkt · arranque en Docker:
#   1) si no hay token (primer arranque), canjea el PAIRING_CODE por él;
#   2) arranca el colector elegido (control-plane: inventario + config + ingesta).
# La config llega por variables de entorno (ver docker-compose.yml / .env).
#
# COLLECTOR selecciona la integración: 'tuya' (por defecto) o 'tapo'. Cada contenedor
# gestiona UNA integración con su propio token en su volumen /data.
set -e

: "${COLLECTOR:=tuya}"
: "${VAKKIO_ENV:=/data/vakkio.env}"
export PYTHONUNBUFFERED=1
mkdir -p "$(dirname "$VAKKIO_ENV")"

case "$COLLECTOR" in
  tapo) SCRIPT=/app/tapo_collector.py ;;
  tuya) SCRIPT=/app/vakkio_collector.py ;;
  *) echo "COLLECTOR desconocido: $COLLECTOR (usa tuya|tapo)"; exit 1 ;;
esac

if [ ! -f "$VAKKIO_ENV" ]; then
  echo "· primer arranque ($COLLECTOR): emparejando con el código…"
  python /app/provision.py --no-service --collector "$COLLECTOR"
fi

echo "· arrancando colector $COLLECTOR"
exec python "$SCRIPT"
