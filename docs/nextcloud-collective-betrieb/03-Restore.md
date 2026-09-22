# Backup pruefen und wiederherstellen

[Zur Startseite](Readme.md)

Es gibt zwei unterschiedliche Verfahren:

1. Isolierter Restore-Test ohne Einfluss auf Produktion
2. Echte Wiederherstellung der Produktionsdatenbank

## Isolierter Restore-Test

Der Test startet PostgreSQL ohne Host-Port auf einem temporaeren Dateisystem.
Das PostgreSQL-Image startet waehrend `initdb` kurz einen Zwischenserver.
Deshalb muss neben `pg_isready` auch die Abschlussmeldung des Entry-Points
abgewartet werden.

```bash
cd /opt/mutual-games-finder

bash <<'SCRIPT'
set -Eeuo pipefail
trap 'echo "Restore-Test fehlgeschlagen (Zeile $LINENO)" >&2' ERR

BACKUP_DIR=/var/backups/mutual-games-finder/<zeitstempel>
CONTAINER="mutual-games-finder-restore-test-$(date +%s)"

cleanup() {
  sudo docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

set -a
source .env.production
set +a

sudo docker run -d \
  --name "$CONTAINER" \
  -e POSTGRES_PASSWORD=restore-test-only \
  -e POSTGRES_DB=restore_test \
  --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=1g \
  mirror.gcr.io/library/postgres:17-alpine >/dev/null

READY=0
for attempt in $(seq 1 120); do
  if sudo docker logs "$CONTAINER" 2>&1 |
       grep -q "PostgreSQL init process complete" &&
     sudo docker exec "$CONTAINER" \
       pg_isready -U postgres -d restore_test >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  sudo docker logs "$CONTAINER"
  exit 1
fi

if [ "$POSTGRES_USER" != postgres ]; then
  sudo docker exec "$CONTAINER" \
    createuser -U postgres "$POSTGRES_USER"
fi

sudo gzip -dc "$BACKUP_DIR/postgres.sql.gz" |
  sudo docker exec -i "$CONTAINER" \
    psql -v ON_ERROR_STOP=1 -U postgres -d restore_test >/dev/null

sudo docker exec "$CONTAINER" \
  psql -U postgres -d restore_test -At -F '=' -c \
  "SELECT 'accounts', count(*) FROM accounts
   UNION ALL SELECT 'games', count(*) FROM games
   UNION ALL SELECT 'ownerships', count(*) FROM ownerships
   UNION ALL SELECT 'participants', count(*) FROM participants
   ORDER BY 1"

echo "RESTORE-TEST ERFOLGREICH"
SCRIPT
```

Wenn der Restore mit `ON_ERROR_STOP=1` ohne Fehler endet und die Tabellen
plausible Zaehler liefern, ist der Datenbankdump wiederherstellbar.

## Produktionsrestore

> Achtung: Die folgenden Schritte ersetzen die aktuelle Produktionsdatenbank.
> Vorher ein zusaetzliches aktuelles Backup erstellen und Wartungszeit
> ankuendigen.

### 1. Sicherungsset pruefen

```bash
BACKUP_DIR=/var/backups/mutual-games-finder/<zeitstempel>
sudo sh -c "cd '$BACKUP_DIR' && sha256sum -c SHA256SUMS"
sudo cat "$BACKUP_DIR/release-tag.txt"
```

### 2. Schreibzugriffe stoppen

```bash
cd /opt/mutual-games-finder

docker compose --env-file .env.production \
  -f compose.production.yml stop backend
```

### 3. Datenbank leeren und wiederherstellen

```bash
docker compose --env-file .env.production \
  -f compose.production.yml exec -T database \
  sh -c 'dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" &&
         createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$POSTGRES_DB"'

sudo gzip -dc "$BACKUP_DIR/postgres.sql.gz" |
  docker compose --env-file .env.production \
    -f compose.production.yml exec -T database \
    sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

### 4. Provider-Tokens nur bei Bedarf restaurieren

Dieser Schritt ersetzt das komplette Provider-Auth-Volume:

```bash
PROVIDER_AUTH_VOLUME="$(
  docker inspect \
    "$(docker compose --env-file .env.production -f compose.production.yml ps --all -q backend)" \
    --format '{{range .Mounts}}{{if eq .Destination "/provider-auth"}}{{.Name}}{{end}}{{end}}'
)"
test -n "$PROVIDER_AUTH_VOLUME"

sudo docker run --rm \
  -v "$PROVIDER_AUTH_VOLUME:/target" \
  -v "$BACKUP_DIR:/backup:ro" \
  mirror.gcr.io/library/alpine:3.21 \
  sh -c 'find /target -mindepth 1 -maxdepth 1 \
           -exec rm -rf "{}" ";" &&
         tar -C /target -xzf /backup/provider-auth.tar.gz'
```

`env.production` nicht blind ersetzen. Zuerst vergleichen:

```bash
sudo diff -u .env.production "$BACKUP_DIR/env.production"
```

### 5. Passenden Release starten

```bash
RELEASE=$(sudo cat "$BACKUP_DIR/release-tag.txt")
git checkout "$RELEASE"

docker compose --env-file .env.production \
  -f compose.production.yml build

docker compose --env-file .env.production \
  -f compose.production.yml up -d --remove-orphans

docker compose --env-file .env.production \
  -f compose.production.yml ps

curl --fail http://127.0.0.1:18000/api/health
```
