# Vakkio Connekkt

Agente local de **[Vakkio](https://vakkio.woobik.dev)** — la "cajita" (o contenedor)
que corre en casa del usuario, descubre sus dispositivos (**Tuya / SmartLife** y
**TP-Link Tapo**) y envía su consumo a Vakkio. Se gestiona **desde la web** (elegir qué
monitorizar) — sin SSH ni tocar ficheros una vez emparejado.

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

Primero genera el **código de emparejamiento** en la web de Vakkio (un solo uso, ~15 min),
uno por cada integración que vayas a usar:
- **Tuya**: Dispositivos → Integraciones → Vincular agente.
- **Tapo**: Dispositivos → TP-Link Tapo → Conectar.

Luego elige una vía:

### A) Docker — recomendado (cualquier caja Linux 24/7)

Ideal si ya tienes un NAS, router, mini-PC o Home Assistant. Sin hardware nuevo.

```bash
git clone https://github.com/pedrowoobik/vakkio-connekkt.git
cd vakkio-connekkt
cp .env.example .env        # rellena los códigos + credenciales de lo que uses
# arranca SOLO las integraciones que quieras (profiles):
docker compose --profile tuya up -d                    # solo Tuya
docker compose --profile tapo up -d                    # solo Tapo
docker compose --profile tuya --profile tapo up -d     # ambas
```

Cada integración es un contenedor con su propio token (en su volumen). Se emparejan
solas en el primer arranque y empiezan a reportar. Incluye **Watchtower** (auto-update).
Logs: `docker compose logs -f vakkio-tuya` (o `vakkio-tapo`).

> **Tapo es local** (protocolo KLAP): usa host networking para descubrir los enchufes,
> así que su contenedor debe correr en un host **Linux en la misma red** que los Tapo
> (no funciona en Docker Desktop de Mac/Windows). Tuya va por la nube y corre donde sea.

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

## Credenciales de Tapo

Usa el **email y la contraseña de tu cuenta TP-Link/Tapo** (la misma de la app Tapo).
Se quedan en el host, nunca viajan a Vakkio, y los enchufes deben estar en la misma red
que el agente. Los **P100/P105** dan on/off (asígnales un consumo estimado por enchufe
en la web); los **P110/P115** reportan vatios reales.

## Configuración

| Variable | Descripción |
|---|---|
| `COLLECTOR` | Integración de este contenedor: `tuya` (def.) \| `tapo`. |
| `PAIRING_CODE` / `PAIRING_CODE_TUYA` / `PAIRING_CODE_TAPO` | Código de emparejamiento (solo el primer arranque). |
| `TUYA_ACCESS_ID` / `TUYA_ACCESS_SECRET` / `TUYA_REGION` | Credenciales de Tuya Cloud (locales). |
| `TAPO_USER` / `TAPO_PWD` | Cuenta TP-Link/Tapo (locales). |
| `TAPO_BROADCAST` | (Tapo) broadcast de la subred para el descubrimiento, si el host tiene varias interfaces. |
| `VAKKIO_API` | Base de la API (por defecto ya apunta a producción). |
| `INTERVAL` | Segundos entre lecturas (def. 60). |

Por Docker se pasan como variables de entorno (`.env`); en la Raspberry, en
`vakkio-agent.conf` o por flags de `install.sh`.

## Licencia

[MIT](LICENSE) © 2026 Pedro Cordeiro (Woobik).
