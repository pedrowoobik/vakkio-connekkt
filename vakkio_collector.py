#!/usr/bin/env python3
"""Vakkio Connekkt · agente local (Tuya Cloud + tinytuya).

CONTROL-PLANE: en vez de una lista fija de dispositivos, este agente:
  1) reporta el INVENTARIO visible de la cuenta al backend (POST /api/agent/inventory),
     marcando cuáles miden potencia;
  2) pregunta al backend QUÉ monitorizar (GET /api/agent/config) y sondea SOLO esos;
  3) ingesta sus lecturas (POST /api/appliance/ingest).
Así el usuario elige los dispositivos desde la web de Vakkio y este agente se
sincroniza solo — sin editar ficheros ni entrar por SSH.

Escalas confirmadas contra la 'specification' del dispositivo:
cur_power /10 = W, add_ele /1000 = kWh.

Config en vakkio.env:
  TUYA_ACCESS_ID / TUYA_ACCESS_SECRET / TUYA_REGION   (credenciales, LOCALES)
  VAKKIO_TOKEN           token del agente (auth de agente e ingesta)
  VAKKIO_API             base de la API (def. https://vakkio.woobik.dev/api)
  INTERVAL               segundos entre lecturas (def. 60)
  INVENTORY_EVERY        cada cuántos ciclos re-reportar inventario (def. 15)
  TUYA_DEVICE_IDS        SOLO fallback si el backend no responde (opcional)
Argumento 'once' -> una sola pasada (inventario + config + ingesta) y sale.
"""
import os, sys, time, json, datetime as dt, requests, tinytuya

# env junto al script (portable). Override con VAKKIO_ENV (p.ej. /data/vakkio.env en Docker).
CFG   = os.environ.get('VAKKIO_ENV') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vakkio.env')
CACHE = os.path.join(os.path.dirname(CFG), 'vakkio_cache.json')

c = {}
for line in open(CFG):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1); c[k] = v

API             = c.get('VAKKIO_API', 'https://vakkio.woobik.dev/api').rstrip('/')
TOKEN           = c['VAKKIO_TOKEN']
INTERVAL        = int(c.get('INTERVAL', '60'))
INVENTORY_EVERY = int(c.get('INVENTORY_EVERY', '15'))
FALLBACK_IDS    = [x for x in c.get('TUYA_DEVICE_IDS', '').split(',') if x]
HDRS            = {'Authorization': f'Bearer {TOKEN}'}

cloud = tinytuya.Cloud(apiRegion=c['TUYA_REGION'], apiKey=c['TUYA_ACCESS_ID'],
                       apiSecret=c['TUYA_ACCESS_SECRET'],
                       apiDeviceID=(FALLBACK_IDS[0] if FALLBACK_IDS else ''))

# caché local (resiliencia si el backend cae): {enabled:[...], metered:{did:bool}}
def load_cache():
    try:
        return json.load(open(CACHE))
    except Exception:
        return {}

def save_cache():
    try:
        json.dump({'enabled': cache.get('enabled', []), 'metered': metered_cache}, open(CACHE, 'w'))
    except Exception:
        pass

cache = load_cache()
metered_cache = cache.get('metered', {})


def status_dps(did):
    st = cloud.getstatus(did)
    return {x['code']: x['value'] for x in st.get('result', [])} if isinstance(st, dict) else {}


def is_metered(did):
    """¿reporta potencia/energía? (probe una vez y cachea; los sensores no miden)."""
    if did in metered_cache:
        return metered_cache[did]
    dps = status_dps(did)
    if not dps:
        return False  # offline/desconocido: no cachear, se reintenta
    m = ('cur_power' in dps) or ('add_ele' in dps)
    metered_cache[did] = m
    return m


def report_inventory(devs):
    """Reporta el catálogo visible al backend (marca los que miden potencia)."""
    items = []
    for d in devs:
        did = d.get('id')
        if not did:
            continue
        items.append({'external_id': did, 'name': d.get('name') or did,
                      'category': d.get('category'), 'metered': is_metered(did)})
    save_cache()
    r = requests.post(f'{API}/agent/inventory', headers=HDRS, json={'devices': items}, timeout=25)
    r.raise_for_status()
    n = r.json().get('discovered')
    nm = sum(1 for i in items if i['metered'])
    print(f"[{dt.datetime.now():%H:%M:%S}] inventario: {n} reportados ({nm} con medida)")


def fetch_enabled():
    """Pregunta al backend qué external_id monitorizar. Cae al caché/env si falla."""
    try:
        r = requests.get(f'{API}/agent/config', headers=HDRS, timeout=15)
        r.raise_for_status()
        ids = r.json().get('enabled', [])
        cache['enabled'] = ids
        save_cache()
        return ids
    except Exception as e:
        print('config error (uso caché/env):', e)
        return cache.get('enabled') or FALLBACK_IDS


def read_one(did, names):
    dps = status_dps(did)
    if 'cur_power' not in dps and 'add_ele' not in dps:
        return None
    item = {'external_id': did, 'name': names.get(did, did), 'kind': 'plug',
            'read_at': dt.datetime.now(dt.timezone.utc).isoformat()}
    if 'cur_power' in dps: item['power_w'] = round(dps['cur_power'] / 10.0, 1)
    if 'add_ele' in dps:   item['energy_total_kwh'] = round(dps['add_ele'] / 1000.0, 3)
    if 'switch_1' in dps:  item['state'] = 'on' if dps['switch_1'] else 'off'
    return item


def cycle(names, enabled):
    batch = [it for did in enabled if (it := read_one(did, names))]
    if not batch:
        print(f"[{dt.datetime.now():%H:%M:%S}] nada que enviar ({len(enabled)} habilitados)")
        return 0
    r = requests.post(f'{API}/appliance/ingest', headers=HDRS, json={'appliances': batch}, timeout=15)
    r.raise_for_status()
    n = r.json().get('accepted')
    print(f"[{dt.datetime.now():%H:%M:%S}] {n} enviados:",
          [f"{b['name']}={b.get('power_w')}W" for b in batch])
    return n


def device_list():
    return cloud.getdevices() or []


if __name__ == '__main__':
    if 'once' in sys.argv:
        devs = device_list()
        report_inventory(devs)
        enabled = fetch_enabled()
        cycle({d.get('id'): d.get('name') for d in devs}, enabled)
        sys.exit(0)

    print(f"[vakkio-connekkt] control-plane -> {API} · interval={INTERVAL}s")
    devs = device_list()
    names = {d.get('id'): d.get('name') for d in devs}
    try:
        report_inventory(devs)
    except Exception as e:
        print('inventario error:', e)

    i = 0
    while True:
        try:
            enabled = fetch_enabled()
            if i > 0 and i % INVENTORY_EVERY == 0:
                devs = device_list()
                names = {d.get('id'): d.get('name') for d in devs}
                report_inventory(devs)
            cycle(names, enabled)
        except Exception as e:
            print('error:', e)
        i += 1
        time.sleep(INTERVAL)
