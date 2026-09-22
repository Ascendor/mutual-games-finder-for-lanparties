# Tagesbetrieb und Schnellcheck

[Zur Startseite](Readme.md)

Im Normalbetrieb ist keine taegliche Bedienung auf dem Server erforderlich.
Docker startet die Container mit `restart: unless-stopped`.

## Aktuellen Release anzeigen

```bash
cd /opt/mutual-games-finder
git describe --tags --exact-match
```

## Containerstatus

```bash
cd /opt/mutual-games-finder

docker compose --env-file .env.production \
  -f compose.production.yml ps
```

Erwartet:

- `database`: `healthy`
- `backend`: `healthy`
- `frontend`: `healthy`

## Lokale Healthchecks

```bash
curl --noproxy "*" --fail \
  http://127.0.0.1:18000/api/health

curl --noproxy "*" --fail --head \
  http://127.0.0.1:18080/
```

## Externer Healthcheck

```bash
cd /opt/mutual-games-finder
set -a
source .env.production
set +a

curl --output /dev/null --silent \
  --write-out 'Ohne Anmeldung: HTTP %{http_code}\n' \
  "https://$APP_HOST/"

curl --user lanparty --fail \
  "https://$APP_HOST/api/health"
echo
```

Der erste Request muss `401` liefern. Beim zweiten fragt `curl` nach dem
Basic-Auth-Passwort und muss danach `{"status":"ok"}` liefern.

## Speicherplatz

```bash
df -h / /var/lib/docker /var/backups 2>/dev/null
docker system df
```

Fuer grosse Playnite-Backups sollte mindestens die doppelte Groesse des
groessten erwarteten Uploads frei sein.

## Letzte Logs

```bash
cd /opt/mutual-games-finder

docker compose --env-file .env.production \
  -f compose.production.yml logs --tail=200
```

Nur einen Dienst anzeigen:

```bash
docker compose --env-file .env.production \
  -f compose.production.yml logs --tail=200 backend
```

## Was ist normal?

- Metadaten- und Playnite-Jobs koennen lange laufen.
- Provider koennen zeitweise Rate-Limits oder abgelaufene Tokens melden.
- Deprecation-Warnungen in Tests sind kein Produktionsausfall.
- Ein `401` ohne Basic Auth ist beabsichtigt.

