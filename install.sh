#!/usr/bin/env bash
# Vakkio Connekkt · instalador para Raspberry (Pi OS Lite) o cualquier Debian + systemd.
#
#   sudo ./install.sh                 # lee vakkio-agent.conf o pregunta
#   sudo ./install.sh --code XXXX-XXXX --tuya-id … --tuya-secret … --tuya-region eu
#
# Deja el agente corriendo como servicio systemd 'vakkio-connekkt'.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
echo "== Vakkio Connekkt · instalador =="

if command -v apt-get >/dev/null 2>&1; then
  echo "· instalando dependencias del sistema…"
  apt-get update -qq
  apt-get install -y --no-install-recommends python3-venv python3-pip ca-certificates >/dev/null
fi

if [ ! -d "$DIR/venv" ]; then
  echo "· creando entorno virtual…"
  python3 -m venv "$DIR/venv"
fi
echo "· instalando librerías Python (tinytuya, python-kasa, requests)…"
"$DIR/venv/bin/pip" install --quiet --upgrade pip
"$DIR/venv/bin/pip" install --quiet tinytuya "python-kasa>=0.7" requests

echo "· provisioning…"
"$DIR/venv/bin/python" "$DIR/provision.py" "$@"
