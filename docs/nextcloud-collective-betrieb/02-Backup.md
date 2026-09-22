# Backup erstellen

[Zur Startseite](Readme.md)

Ein vollstaendiges Sicherungsset besteht aus:

- PostgreSQL-Dump
- Provider-Auth-Volume mit Tokens und Sitzungsdaten
- `.env.production`
- Release-Tag
- Pruefsummen

Playnite-Uploaddateien sind temporaer und muessen nicht gesichert werden.

## Manuelles Komplettbackup

Das Backup ist online moeglich; die Anwendung muss dafuer nicht gestoppt
werden.

```bash
cd /opt/mutual-games-finder

STAMP=$(date +%F-%H%M%S)
BACKUP_DIR="/var/backups/mutual-games-finder/$STAMP"

sudo install -d -o root -g root -m 0700 "$BACKUP_DIR"

docker compose --env-file .env.production \
  -f compose.production.yml exec -T database \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' |
  gzip |
  sudo tee "$BACKUP_DIR/postgres.sql.gz" >/dev/null

PROVIDER_AUTH_VOLUME="$(
  docker inspect \
    "$(docker compose --env-file .env.production -f compose.production.yml ps -q backend)" \
    --format '{{range .Mounts}}{{if eq .Destination "/provider-auth"}}{{.Name}}{{end}}{{end}}'
)"
test -n "$PROVIDER_AUTH_VOLUME"

sudo docker run --rm \
  -v "$PROVIDER_AUTH_VOLUME:/source:ro" \
  -v "$BACKUP_DIR:/backup" \
  mirror.gcr.io/library/alpine:3.21 \
  tar -C /source -czf /backup/provider-auth.tar.gz .

sudo install -o root -g root -m 0600 \
  .env.production "$BACKUP_DIR/env.production"

git describe --tags --exact-match |
  sudo tee "$BACKUP_DIR/release-tag.txt" >/dev/null

sudo gzip -t "$BACKUP_DIR/postgres.sql.gz"
sudo tar -tzf "$BACKUP_DIR/provider-auth.tar.gz" >/dev/null

sudo sha256sum \
  "$BACKUP_DIR/postgres.sql.gz" \
  "$BACKUP_DIR/provider-auth.tar.gz" \
  "$BACKUP_DIR/env.production" \
  "$BACKUP_DIR/release-tag.txt" |
  sudo tee "$BACKUP_DIR/SHA256SUMS" >/dev/null

sudo find "$BACKUP_DIR" -maxdepth 1 -type f \
  -exec chmod 0600 {} +

echo "Backup: $BACKUP_DIR"
sudo ls -lh "$BACKUP_DIR"
```

## Backup pruefen

```bash
BACKUP_DIR=/var/backups/mutual-games-finder/<zeitstempel>

sudo sh -c "cd '$BACKUP_DIR' && sha256sum -c SHA256SUMS"
sudo gzip -t "$BACKUP_DIR/postgres.sql.gz"
sudo tar -tzf "$BACKUP_DIR/provider-auth.tar.gz" >/dev/null
```

Alle Pruefsummen muessen `OK` melden.

## Aufbewahrung

Empfehlung:

- mindestens 14 Tagesstaende
- ein Stand vor jedem Update
- mindestens eine verschluesselte Kopie auf einem anderen System
- regelmaessiger Restore-Test

Vor einer Loeschung zuerst nur anzeigen, welche Verzeichnisse aelter als
14 Tage sind:

```bash
sudo find /var/backups/mutual-games-finder \
  -mindepth 1 -maxdepth 1 -type d -mtime +14 -print
```

Alte Backups erst loeschen, wenn die externe Sicherung nachweislich vorhanden
und lesbar ist.

## Sensible Inhalte

`env.production` und `provider-auth.tar.gz` enthalten Zugangsdaten. Das
Backup-Verzeichnis muss `root:root` gehoeren und Modus `0700` besitzen.
Externe Kopien muessen verschluesselt werden.
