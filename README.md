# Vakkio Connekkt

Agente local de **[Vakkio](https://vakkio.woobik.dev)** — la "cajita" (o contenedor)
que corre en casa del usuario, descubre sus dispositivos (hoy **Tuya / SmartLife**) y
envía su consumo a Vakkio. Se gestiona **desde la web** (elegir qué monitorizar) —
sin SSH ni tocar ficheros una vez emparejado.

- **Privado por diseño**: las credenciales de la plataforma se quedan en tu equipo;
  al backend solo viaja un token del agente.
- **Sin puertos abiertos**: todas las conexiones las inicia el agente (sirve detrás
  de cualquier router doméstico, sin IP fija).
- **Se actualiza solo** (con Docker + Watchtower).

## Cómo funciona

El backend es la fuente de verdad y el agente se **sincroniza**:

1. **Empareja** una vez con un código de un solo uso → obtiene su token.
2. **Reporta** el inventario visible (`POST /api/agent/inventory`).
3. **Pregunta** qué monitorizar (`GET /api/agent/config`) y sondea solo eso.
4. **Ingesta** las lecturas (`POST /api/appliance/ingest`).

Para añadir o quitar dispositivos, lo haces desde la web y el agente lo recoge en
~1 minuto. No vuelves a tocar la caja.

## Puesta en marcha

Primero genera el **código de emparejamiento** en la web de Vakkio:
**Dispositivos → Integraciones → Vincular agente → Tuya** (un solo uso, ~15 min).

Luego elige una vía:

### A) Docker — recomendado (cualquier caja Linux 24/7)

Ideal si ya tienes un NAS, router, mini-PC o Home Assistant. Sin hardware nuevo.

```bash
git clone https://github.com/pedrowoobik/vakkio-connekkt.git
cd vakkio-connekkt
cp .env.example .env        # rellena PAIRING_CODE + credenciales Tuya
docker compose up -d
```

Se empareja solo en el primer arranque (el token queda en el volumen `vakkio-data`)
y empieza a reportar. Incluye **Watchtower**, que mantiene el agente actualizado.
Logs: `docker compose logs -f vakkio-connekkt`.

### B) Raspberry / Debian + systemd (cajita dedicada)

Para quien no tenga dónde correr Docker. Raspberry Pi OS **Lite**:

```bash
git clone https://github.com/pedrowoobik/vakkio-connekkt.git
cd vakkio-connekkt
sudo ./install.sh           # pide el código y las credenciales, o pásalos por flags
```

O headless (sin teclado): rellena `vakkio-agent.conf` (copia de
`vakkio-agent.conf.example`) y colócalo en la partición `/boot` de la SD; en el
primer arranque `sudo ./install.sh` lo lee solo. Deja el servicio
`vakkio-connekkt` corriendo (`systemctl status vakkio-connekkt`).

## Credenciales de Tuya Cloud

En [iot.tuya.com](https://iot.tuya.com): Cloud → Development → tu proyecto →
**Access ID / Access Secret**, y vincula tu cuenta de la app SmartLife/Tuya
(Devices → Link Tuya App Account). La región suele ser `eu`.

## Configuración

| Variable | Descripción |
|---|---|
| `PAIRING_CODE` | Código de emparejamiento (solo el primer arranque). |
| `TUYA_ACCESS_ID` / `TUYA_ACCESS_SECRET` | Credenciales de Tuya Cloud (locales). |
| `TUYA_REGION` | `eu` \| `us` \| `cn` \| `in`. |
| `VAKKIO_API` | Base de la API (por defecto ya apunta a producción). |
| `INTERVAL` | Segundos entre lecturas (def. 60). |

Por Docker se pasan como variables de entorno (`.env`); en la Raspberry, en
`vakkio-agent.conf` o por flags de `install.sh`.

## Licencia

[MIT](LICENSE) © 2026 Pedro Cordeiro (Woobik).
