#!/usr/bin/env python3
"""Vakkio · colector de enchufes TP-Link Tapo (LOCAL, python-kasa / protocolo KLAP).

Mismo patrón control-plane que el colector Tuya: reporta el INVENTARIO visible, pregunta
al backend QUÉ monitorizar e INGESTA sus lecturas. La diferencia: Tapo no tiene API cloud
pública, así que esto habla con los enchufes por la RED LOCAL (hay que estar en la misma
WiFi que ellos).

  - P100/P105  -> solo on/off (sin medir). El consumo estimado se pone en Vakkio por
                  enchufe (editar aparato -> "Potencia estimada"); Vakkio se lo atribuye
                  mientras el enchufe está encendido.
  - P110/P115  -> además reportan W (y kWh si el firmware lo expone).

Uso:
  python tapo_collector.py pair AAAA-BBBB   # canjea el código de Vakkio -> guarda el token
  python tapo_collector.py discover         # lista los Tapo que se ven en la red (debug)
  python tapo_collector.py once             # una pasada (inventario + config + ingesta)
  python tapo_collector.py                  # bucle continuo

Requiere:  pip install "python-kasa>=0.7" requests
Config en collectors/tapo.env (ver tapo.env.example).
"""
import os, sys, time, asyncio, datetime as dt, requests

CFG = (os.environ.get('VAKKIO_TAPO_ENV') or os.environ.get('VAKKIO_ENV')
       or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tapo.env'))


def load_cfg():
    c = {}
    if os.path.isfile(CFG):
        for line in open(CFG):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                c[k] = v
    return c


c = load_cfg()
API      = c.get('VAKKIO_API', 'https://vakkio.woobik.dev/api').rstrip('/')
USER     = c.get('TAPO_USER', '')
PWD      = c.get('TAPO_PWD', '')
INTERVAL = int(c.get('INTERVAL', '60'))
INVENTORY_EVERY = int(c.get('INVENTORY_EVERY', '15'))


def hdrs():
    tok = load_cfg().get('VAKKIO_TOKEN', '')
    return {'Authorization': f'Bearer {tok}'}


# --------------------------------------------------------------- emparejamiento

def set_env(key, value):
    """Escribe (o reemplaza) KEY=value en tapo.env."""
    lines, done = [], False
    if os.path.isfile(CFG):
        for line in open(CFG):
            if line.strip().startswith(f'{key}='):
                lines.append(f'{key}={value}\n'); done = True
            else:
                lines.append(line)
    if not done:
        lines.append(f'{key}={value}\n')
    with open(CFG, 'w') as f:
        f.writelines(lines)
    os.chmod(CFG, 0o600)


def pair(code):
    """Canjea el código de emparejamiento generado en Vakkio (Dispositivos -> Tapo ->
    Conectar) por el token del colector y lo guarda en tapo.env."""
    r = requests.post(f'{API}/agent/pair', json={'code': code}, timeout=20)
    if r.status_code != 200:
        print('emparejamiento falló:', r.status_code, r.text); sys.exit(1)
    d = r.json()
    if d.get('source') != 'tapo':
        print(f"aviso: el código era para '{d.get('source')}', no 'tapo'.")
    set_env('VAKKIO_TOKEN', d['token'])
    print(f"emparejado OK (propiedad {d.get('property_id')}, fuente {d.get('source')}). Token guardado en {CFG}.")


# ------------------------------------------------------------- descubrimiento

async def _discover():
    from kasa import Discover, Credentials, Module
    if not USER or not PWD:
        print('faltan TAPO_USER/TAPO_PWD en tapo.env'); return []
    creds = Credentials(USER, PWD)
    found = {}
    # Si defines TAPO_HOSTS=ip1,ip2 en tapo.env, conecta DIRECTO por IP (lo más fiable:
    # evita problemas de broadcast entre subredes / AP-isolation). Si no, broadcast.
    hosts = [h.strip() for h in c.get('TAPO_HOSTS', '').split(',') if h.strip()]
    if hosts:
        for h in hosts:
            try:
                found[h] = await Discover.discover_single(h, credentials=creds)
            except Exception as e:
                print(f'  no conecto con {h}: {e}')
    else:
        # Descubrimiento por broadcast. Si el PC tiene varias interfaces (cable+WiFi), apunta
        # al broadcast de la subred de los enchufes con TAPO_BROADCAST=192.168.1.255 en tapo.env.
        target = c.get('TAPO_BROADCAST', '').strip() or '255.255.255.255'
        try:
            found = await Discover.discover(target=target, credentials=creds, timeout=8)
        except Exception as e:
            print('  broadcast falló:', e)
    out = []
    for ip, dev in found.items():
        try:
            await dev.update()
        except Exception as e:
            print('  update falló', ip, e); continue
        rec = {'id': dev.device_id, 'name': dev.alias or dev.model or dev.device_id, 'ip': ip,
               'mac': getattr(dev, 'mac', None), 'model': dev.model, 'is_on': bool(dev.is_on),
               'metered': False, 'power_w': None, 'energy_total_kwh': None}
        energy = dev.modules.get(Module.Energy) if getattr(dev, 'modules', None) else None
        if energy is not None:
            rec['metered'] = True
            try:
                rec['power_w'] = round(float(energy.current_consumption or 0), 1)
            except Exception:
                pass
            for attr in ('consumption_total', 'consumption_today'):
                try:
                    val = getattr(energy, attr, None)
                    if val is not None:
                        rec['energy_total_kwh'] = round(float(val), 3); break
                except Exception:
                    pass
        out.append(rec)
    return out


def discover():
    return asyncio.run(_discover())


# ---------------------------------------------------------- control-plane API

def report_inventory(devs):
    items = [{'external_id': d['id'], 'name': d['name'], 'category': d.get('model'),
              'metered': d['metered']} for d in devs]
    r = requests.post(f'{API}/agent/inventory', headers=hdrs(), json={'devices': items}, timeout=25)
    r.raise_for_status()
    nm = sum(1 for d in devs if d['metered'])
    print(f"[{dt.datetime.now():%H:%M:%S}] inventario: {r.json().get('discovered')} reportados ({nm} con medida)")


def fetch_enabled():
    try:
        r = requests.get(f'{API}/agent/config', headers=hdrs(), timeout=15)
        r.raise_for_status()
        return r.json().get('enabled', [])
    except Exception as e:
        print('config error:', e)
        return []


def cycle(devs, enabled):
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    batch = []
    for d in devs:
        if d['id'] not in enabled:
            continue
        it = {'external_id': d['id'], 'name': d['name'], 'kind': 'plug',
              'state': 'on' if d['is_on'] else 'off', 'read_at': now}
        if d['power_w'] is not None:
            it['power_w'] = d['power_w']
        if d['energy_total_kwh'] is not None:
            it['energy_total_kwh'] = d['energy_total_kwh']
        batch.append(it)
    if not batch:
        print(f"[{dt.datetime.now():%H:%M:%S}] nada que enviar ({len(enabled)} habilitados de {len(devs)} vistos)")
        return 0
    r = requests.post(f'{API}/appliance/ingest', headers=hdrs(), json={'appliances': batch}, timeout=15)
    r.raise_for_status()
    print(f"[{dt.datetime.now():%H:%M:%S}] {r.json().get('accepted')} enviados:",
          [f"{b['name']}={b['state']}" + (f"/{b['power_w']}W" if 'power_w' in b else '') for b in batch])
    return r.json().get('accepted')


def main():
    print(f"[tapo] control-plane -> {API} · interval={INTERVAL}s")
    once = 'once' in sys.argv
    i = 0
    while True:
        try:
            devs = discover()
            if i % INVENTORY_EVERY == 0:
                report_inventory(devs)
            cycle(devs, fetch_enabled())
        except Exception as e:
            print('error:', e)
        if once:
            break
        i += 1
        time.sleep(INTERVAL)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'pair':
        if len(sys.argv) < 3:
            print('uso: python tapo_collector.py pair AAAA-BBBB'); sys.exit(1)
        pair(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == 'discover':
        ds = discover()
        print(f"{len(ds)} enchufe(s) Tapo encontrados:")
        for d in ds:
            print(f"  {d['model'] or '?':10} {d['name']:22} {d['ip']:15} "
                  f"{d['mac'] or '--':17} {'ON ' if d['is_on'] else 'off'} "
                  f"{'medido ' + str(d['power_w']) + 'W' if d['metered'] else 'solo on/off'}")
        if not ds:
            print("  (ninguno). Revisa: el PC y los Tapo en la MISMA subred/WiFi, sin 'AP/Client")
            print("  isolation' en el router, y credenciales Tapo correctas. Si sabes las IPs")
            print("  (app Tapo -> aparato -> info, o la lista del router), ponlas en tapo.env:")
            print("      TAPO_HOSTS=192.168.1.50,192.168.1.51")
    else:
        main()
