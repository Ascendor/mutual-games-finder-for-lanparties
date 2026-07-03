# Monitoring und Fehlersuche

[Zur Startseite](Readme.md)

## Statusuebersicht

```bash
cd /opt/refjuplay-together

docker compose --env-file .env.production \
  -f compose.production.yml ps

docker stats --no-stream
df -h
free -h
```

## Logs nach Dienst

```bash
docker compose --env-file .env.production \
  -f compose.production.yml logs --tail=300 backend

docker compose --env-file .env.production \
  -f compose.production.yml logs --tail=300 frontend

docker compose --env-file .env.production \
  -f compose.production.yml logs --tail=300 database
```

Live verfolgen:

```bash
docker compose --env-file .env.production \
  -f compose.production.yml logs --follow --tail=100 backend
```

Mit `Ctrl+C` wird nur die Loganzeige beendet, nicht der Container.

## Apache-Logs

```bash
sudo tail -n 200 \
  /var/log/apache2/refjuplay-together-error.log

sudo tail -n 100 \
  /var/log/apache2/refjuplay-together-access.log
```

## Datenbankgroesse

```bash
docker compose --env-file .env.production \
  -f compose.production.yml exec -T database \
  sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB" -Atc \
    "SELECT pg_size_pretty(pg_database_size(current_database()));"'
```

## Portbindungen

```bash
sudo ss -ltnp |
  grep -E ':(80|443|18000|18080|5432)\b'
```

Erwartet:

- Apache oeffentlich auf `80` und `443`
- Backend nur `127.0.0.1:18000`
- Frontend nur `127.0.0.1:18080`
- kein Host-Listener auf `5432`

## Wenn lokale Requests haengen

Zuerst Proxy-Variablen umgehen:

```bash
curl --noproxy "*" --max-time 10 \
  http://127.0.0.1:18000/api/health
```

Wenn es nur bei aktiver UFW haengt:

```bash
sudo ufw status verbose
sudo iptables -L ufw-before-input -n --line-numbers
docker network inspect refjuplay-together_application
```

Auf diesem Server hatte eine vorgeschaltete FireHOL-Drop-Regel Docker-
Bridge-Verkehr vor den normalen UFW-Regeln blockiert. Eine Freigabe muss vor
einer solchen globalen Drop-Regel greifen. Bridge-Name und Subnetz nie blind
von einer anderen Installation uebernehmen.

## Typische HTTP-Fehler

- `401`: Ohne Basic Auth normal; mit korrekten Daten Passwortdatei pruefen.
- `502`: Apache erreicht Frontend oder Backend nicht.
- `504`: Request dauerte laenger als das Apache-Proxy-Timeout.
- `413`: Uploadlimit in Apache und Backend pruefen.
- `500`: Backend-Logs und Synchronisationsprotokoll ansehen.

## Docker-Speicher

```bash
docker system df
```

Keine pauschalen `docker system prune --volumes`-Befehle verwenden. Volumes
enthalten Datenbank und Provider-Tokens.

