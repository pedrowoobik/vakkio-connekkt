#!/usr/bin/env python3
"""Vakkio Connekkt · provisioning del agente (onboarding sin SSH).

Canjea un CÓDIGO de emparejamiento (generado en la web de Vakkio) por el token del
agente, escribe la config local y arranca el colector como servicio systemd.
Las credenciales de la plataforma (Tuya) se quedan SIEMPRE en local (nunca al backend).

Fuentes de config, por prioridad:
  1) flags CLI:  --code, --tuya-id, --tuya-secret, --tuya-region, --api
  2) variables de entorno (útil en Docker): PAIRING_CODE, TUYA_*, VAKKIO_API, RUN_AS
  3) fichero:    /boot/firmware/vakkio-agent.conf | /boot/vakkio-agent.conf | ./vakkio-agent.conf
  4) preguntas interactivas (si hay terminal)
"""
import os, sys, json, argparse, subprocess, getpass
import urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_API = 'https://vakkio.woobik.dev/api'
CONF_PATHS = [
    '/boot/firmware/vakkio-agent.conf',
    '/boot/vakkio-agent.conf',
    os.path.join(HERE, 'vakkio-agent.conf'),
]
ENV_PATH = os.environ.get('VAKKIO_ENV') or os.path.join(HERE, 'vakkio.env')
SERVICE_PATH = '/etc/systemd/system/vakkio-connekkt.service'
ENV_KEYS = ['PAIRING_CODE', 'VAKKIO_API', 'TUYA_ACCESS_ID', 'TUYA_ACCESS_SECRET', 'TUYA_REGION', 'RUN_AS']


def read_conf():
    d = {}
    for p in CONF_PATHS:
        if os.path.isfile(p):
            for line in open(p):
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    d[k.strip()] = v.strip()
            print(f"· config leída de {p}")
            break
    return d


def ask(conf, key, prompt, secret=False, default=None):
    if conf.get(key):
        return conf[key]
    if not sys.stdin.isatty():
        if default is not None:
            return default
        sys.exit(f"falta {key} y no hay terminal para preguntarlo (ponlo en vakkio-agent.conf o por env)")
    val = (getpass.getpass(prompt) if secret else input(prompt)).strip()
    return val or (default or '')


def redeem(api, code):
    url = f"{api.rstrip('/')}/agent/pair"
    req = urllib.request.Request(
        url, data=json.dumps({'code': code}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        sys.exit(f"✗ emparejamiento rechazado ({e.code}): {body}\n"
                 f"  ¿código caducado o ya usado? Genera uno nuevo en la web.")
    except urllib.error.URLError as e:
        sys.exit(f"✗ no se pudo contactar con {url}: {e}")


def write_env(env):
    with open(ENV_PATH, 'w') as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")
    os.chmod(ENV_PATH, 0o600)
    print(f"· credenciales guardadas (local, chmod 600) en {ENV_PATH}")


def install_service(run_as):
    py = os.path.join(HERE, 'venv', 'bin', 'python')
    if not os.path.exists(py):
        py = sys.executable
    unit = f"""[Unit]
Description=Vakkio Connekkt · agente colector (control-plane)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={run_as}
WorkingDirectory={HERE}
ExecStart={py} {os.path.join(HERE, 'vakkio_collector.py')}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    with open(SERVICE_PATH, 'w') as f:
        f.write(unit)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'vakkio-connekkt.service'], check=True)
    print("· servicio systemd 'vakkio-connekkt' instalado y arrancado")


def main():
    ap = argparse.ArgumentParser(description='Provisioning del agente Vakkio Connekkt')
    ap.add_argument('--code', help='código de emparejamiento (de la web)')
    ap.add_argument('--api', help=f'base de la API (def. {DEFAULT_API})')
    ap.add_argument('--tuya-id')
    ap.add_argument('--tuya-secret')
    ap.add_argument('--tuya-region', help='eu/us/cn/in')
    ap.add_argument('--no-service', action='store_true', help='no instalar el servicio systemd')
    a = ap.parse_args()

    conf = read_conf()                          # 3) fichero
    for key in ENV_KEYS:                         # 2) variables de entorno
        if os.environ.get(key):
            conf[key] = os.environ[key]
    for key, val in {'PAIRING_CODE': a.code, 'VAKKIO_API': a.api, 'TUYA_ACCESS_ID': a.tuya_id,
                     'TUYA_ACCESS_SECRET': a.tuya_secret, 'TUYA_REGION': a.tuya_region}.items():
        if val:                                  # 1) flags CLI (mayor prioridad)
            conf[key] = val

    api = conf.get('VAKKIO_API', DEFAULT_API)
    code = ask(conf, 'PAIRING_CODE', 'Código de emparejamiento (de la web de Vakkio): ')
    tid = ask(conf, 'TUYA_ACCESS_ID', 'Tuya Access ID: ')
    tsec = ask(conf, 'TUYA_ACCESS_SECRET', 'Tuya Access Secret: ', secret=True)
    treg = ask(conf, 'TUYA_REGION', 'Región Tuya (eu/us/cn/in) [eu]: ', default='eu') or 'eu'

    print(f"· canjeando el código en {api} …")
    res = redeem(api, code)
    if res.get('status') != 'ok' or not res.get('token'):
        sys.exit(f"✗ emparejamiento fallido: {res}")
    print(f"✓ vinculado a la propiedad {res.get('property_id')} (source={res.get('source')})")

    write_env({
        'VAKKIO_API': res.get('api_base', api),
        'VAKKIO_TOKEN': res['token'],
        'TUYA_ACCESS_ID': tid,
        'TUYA_ACCESS_SECRET': tsec,
        'TUYA_REGION': treg,
    })

    if a.no_service:
        print("· config lista (--no-service). Para arrancar el colector:")
        print(f"  {sys.executable} {os.path.join(HERE, 'vakkio_collector.py')}")
        return

    if os.geteuid() != 0:
        print("\nNOTA: para instalar el servicio systemd hace falta root. Reejecuta con sudo:")
        print(f"  sudo {sys.executable} {os.path.abspath(__file__)}")
        return

    run_as = conf.get('RUN_AS') or os.environ.get('SUDO_USER') or 'pi'
    install_service(run_as)
    print("\n✓ Listo. El agente ya reporta su inventario. Elige qué monitorizar en la web:")
    print("  Dispositivos → Integraciones → Tuya → Gestionar")


if __name__ == '__main__':
    main()
