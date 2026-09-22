# Auf eine neue Version aktualisieren

[Zur Startseite](Readme.md)

Produktiv werden nur getestete Release-Tags ausgerollt. Nicht direkt auf
`main` oder einen anderen beweglichen Branch wechseln.

## 1. Neue Version vorbereiten

```bash
cd /opt/mutual-games-finder

git status --short
git fetch --tags
git tag --sort=-version:refname | head
```

`git status --short` muss leer sein. Lokale Aenderungen vor dem Update
klaeren, nicht mit Gewalt verwerfen.

## 2. Backup erstellen

Vor jedem Update das vollstaendige Verfahren aus
[Backup erstellen](02-Backup.md) ausfuehren.

## 3. Release auschecken

```bash
git checkout <neuer-release-tag>
git describe --tags --exact-match
```

## 4. Konfiguration, Build und Tests

```bash
docker compose --env-file .env.production \
  -f compose.production.yml config --quiet

docker compose --env-file .env.production \
  -f compose.production.yml build

docker compose --env-file .env.production \
  -f compose.production.yml run --rm backend pytest
```

Bei einem Build- oder Testfehler nicht deployen.

## 5. Deployment

```bash
docker compose --env-file .env.production \
  -f compose.production.yml up -d --remove-orphans

docker compose --env-file .env.production \
  -f compose.production.yml ps

curl --fail http://127.0.0.1:18000/api/health
```

Das Backend fuehrt Alembic-Migrationen beim Start automatisch aus.

## 6. Externe Abnahme

```bash
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

Im Browser pruefen:

1. Anmeldung und Spielerauswahl
2. Dashboard und Spielelisten
3. Accounts und Logins
4. ein kleiner Provider-Sync
5. bei Import-Aenderungen ein Playnite-Test

## 7. Logs kontrollieren

```bash
docker compose --env-file .env.production \
  -f compose.production.yml logs --tail=200
```

Das Vorupdate-Backup behalten, bis die neue Version mehrere Tage stabil lief.

