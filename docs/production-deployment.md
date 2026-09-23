# Produktionsbetrieb auf einem Debian-VServer

Die auf einzelne Aufgaben aufgeteilten Betriebs-Runbooks fuer Nextcloud
Collectives liegen unter
[`docs/nextcloud-collective-betrieb/`](nextcloud-collective-betrieb/Readme.md).

Diese Anleitung beschreibt die spaetere manuelle Installation unter
`https://mutual-games-finder.<deine-domain>`. Apache bleibt der einzige
oeffentliche Webserver. Die Docker-Container lauschen ausschliesslich auf
Loopback-Adressen; PostgreSQL besitzt keinen Host-Port.

Das vorhandene `docker-compose.yml` bleibt fuer den lokalen Betrieb bestimmt.
Auf dem VServer wird ausschliesslich `compose.production.yml` verwendet.

Die Beispiele verwenden neutrale Standardpfade fuer Neuinstallationen.
Bestehende Installationen muessen nicht verschoben oder umbenannt werden:
Befehle werden dort einfach aus dem bereits vorhandenen Repository-Verzeichnis
ausgefuehrt. Docker Compose leitet den Projektnamen aus diesem Verzeichnis ab,
sodass bestehende Volumes unveraendert weiterverwendet werden.

## 1. Voraussetzungen pruefen

Die Subdomain muss als DNS-A- und, falls genutzt, AAAA-Record auf den VServer
zeigen. Ein Wildcard-Zertifikat muss genau eine Subdomain-Ebene abdecken.

```bash
docker compose version
apachectl -S
free -h
df -h
sudo ss -ltnp
```

Fuer grosse Playnite-Backups sollte auf dem Docker-Dateisystem mindestens die
doppelte Groesse des groessten erwarteten Backups frei sein. Der Import wird
auf Disk gepuffert und nicht mehr vollstaendig in den Arbeitsspeicher geladen.

## 2. Repository installieren

```bash
sudo install -d -o "$USER" -g "$USER" /opt/mutual-games-finder
git clone https://github.com/Ascendor/mutual-games-finder-for-lanparties.git /opt/mutual-games-finder
cd /opt/mutual-games-finder
git fetch --tags
git checkout <release-tag>
```

Fuer produktive Updates sollte immer ein getesteter Release-Tag statt eines
beweglichen Branches verwendet werden.

Das Dependency-Upgrade vom September 2026 installiert Python 3.14.7 im
Docker-Build ueber uv. Auf dem Host ist dafuer keine neue Python-Installation
noetig. PostgreSQL bleibt bei Major-Version 17; bestehende Volumes und
`.env.production` bleiben unveraendert. Die neuen Laufzeiten werden beim
normalen Image-Neubau und anschliessenden `up -d` uebernommen.

## 3. Produktionsvariablen anlegen

```bash
cd /opt/mutual-games-finder
python3 scripts/generate_env_secrets.py \
  --template .env.production.example \
  --output .env.production
chmod 600 .env.production
joe .env.production
openssl rand -hex 32
```

Den ausgegebenen Zufallswert als `POSTGRES_PASSWORD` eintragen und mindestens
folgende Werte anpassen:

```env
APP_HOST=mutual-games-finder.example.org
APP_DISPLAY_NAME=Mutual Games Finder
APP_TITLE=Mutual Games Finder - Der Spielefinder
APP_SUBTITLE=Der Spielefinder
APP_SOURCE_URL=https://github.com/Ascendor/mutual-games-finder-for-lanparties
UPSTREAM_SOURCE_URL=https://github.com/Ascendor/mutual-games-finder-for-lanparties
APP_CLIENT_NAME=Mutual Games Finder
ADMIN_PASSWORD=<bereits zufaellig erzeugter Wert>
UNOFFICIAL_PROVIDER_INTEGRATIONS_ENABLED=false
POSTGRES_DB=lanparty
POSTGRES_USER=lanparty
POSTGRES_PASSWORD=<zufaelliger-hex-wert>
STEAM_API_KEY=
IGDB_CLIENT_ID=
IGDB_CLIENT_SECRET=
RAWG_API_KEY=
XBOX_CLIENT_ID=
PLAYNITE_UPLOAD_MAX_BYTES=4294967296
IMPORT_ARCHIVE_MAX_MEMBERS=25000
IMPORT_ARCHIVE_MAX_MEMBER_BYTES=2147483648
IMPORT_ARCHIVE_MAX_UNCOMPRESSED_BYTES=6442450944
IMPORT_ARCHIVE_MAX_COMPRESSION_RATIO=500
PRIVACY_CONTROLLER_NAME=<name-der-verantwortlichen-person>
PRIVACY_CONTROLLER_CONTACT=<kontaktmoeglichkeit>
PRIVACY_HOSTING_PROVIDER=<name-des-vserver-hosters>
PRIVACY_SUPERVISORY_AUTHORITY=<zustaendige-landesbehoerde>
PRIVACY_SUPERVISORY_AUTHORITY_URL=<https-url-der-landesbehoerde>
ANALYTICS_RETENTION_DAYS=180
PRIVACY_ACCESS_LOG_RETENTION_DAYS=7
PRIVACY_BACKUP_RETENTION_DAYS=14
```

Die Datei darf nicht committet oder ausserhalb eines geschuetzten Backups
kopiert werden.

Die Datenschutzangaben werden auf der Seite `Datenschutz & Hinweise`
angezeigt. Sie muessen fuer die konkrete Installation ausgefuellt werden.

## 4. Produktionskonfiguration pruefen und starten

```bash
cd /opt/mutual-games-finder
docker compose --env-file .env.production -f compose.production.yml config --quiet
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml run --build --rm backend-tests
docker compose --env-file .env.production -f compose.production.yml rm --stop --force test-database
docker compose --env-file .env.production -f compose.production.yml up -d
docker compose --env-file .env.production -f compose.production.yml ps
```

Alembic aktualisiert die PostgreSQL-Datenbank automatisch beim Backend-Start.

`backend-tests` baut ein eigenes Testimage und startet nur die separate
PostgreSQL-Testdatenbank im RAM, ohne Produktionsvolumes oder Provider-Tokens.
Der normale Backend-Dienst enthaelt keine Testpakete. Die Testdienste sind
hinter dem Profil `testing` und werden beim regulaeren Start nicht gestartet.
uv wird nur beim Image-Build verwendet; auf dem Host ist keine uv-Installation
und keine neue Env-Variable erforderlich.

Vor der Apache-Freigabe:

```bash
curl --fail http://127.0.0.1:18000/api/health
curl --fail --head http://127.0.0.1:18080/
```

## 5. Apache vorbereiten

Erforderliche Module:

```bash
sudo a2enmod proxy proxy_http ssl headers rewrite auth_basic authn_file
sudo install -d -o root -g www-data -m 0750 /etc/apache2/auth
sudo htpasswd -c /etc/apache2/auth/mutual-games-finder.htpasswd lanparty
sudo chown root:www-data /etc/apache2/auth/mutual-games-finder.htpasswd
sudo chmod 0640 /etc/apache2/auth/mutual-games-finder.htpasswd
```

Die Vorlage installieren:

```bash
sudo cp deploy/apache/mutual-games-finder.conf.example \
  /etc/apache2/sites-available/mutual-games-finder.conf
sudo joe /etc/apache2/sites-available/mutual-games-finder.conf
sudo install -o root -g root -m 0644 \
  deploy/logrotate/mutual-games-finder \
  /etc/logrotate.d/mutual-games-finder
```

In der Kopie muessen der echte `ServerName` sowie die bereits vorhandenen
Wildcard-Pfade fuer `SSLCertificateFile` und `SSLCertificateKeyFile`
eingetragen werden. `AuthName` ist die sichtbare Bezeichnung im
Basic-Auth-Dialog und sollte zum konfigurierten `APP_DISPLAY_NAME` passen.
`APP_AUTH_REALM` aus der Env-Datei wirkt nur auf das lokale Docker-Gateway,
nicht auf den Apache des Hosts. Zertifikate werden nicht in das Repository
oder in Docker kopiert.

```bash
sudo a2ensite mutual-games-finder.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

Der Apache-VHost erlaubt Requests bis 4 GiB und verwendet fuer lang laufende
Importe ein Proxy-Timeout von einer Stunde. Wird das Backendlimit geaendert,
muss `LimitRequestBody` in der Apache-Konfiguration mindestens denselben Wert
erhalten.

## 6. Firewall und Erreichbarkeit pruefen

Oeffentlich erforderlich sind nur die bereits genutzten HTTP-/HTTPS-Ports.
Die Ports 18000 und 18080 muessen ausschliesslich auf `127.0.0.1` lauschen;
PostgreSQL darf keinen Host-Port besitzen.

```bash
sudo ss -ltnp | grep -E ':(80|443|18000|18080|5432)\b'
curl --head https://mutual-games-finder.example.org/
curl --user lanparty https://mutual-games-finder.example.org/api/health
```

Der erste Request muss ohne Zugangsdaten `401 Unauthorized` liefern, der
zweite mit Basic Auth `{"status":"ok"}`.

Im Browser anschliessend pruefen:

1. Gueltige Zertifikatskette ohne Warnung.
2. Basic-Auth-Anmeldung und Spielerauswahl.
3. Frontend-Navigation und API-Listen.
4. Kleiner Playnite-Import.
5. Ein realistisches grosses Backup.
6. Mindestens ein direkter Provider-Sync.

## 7. Backups

Backups enthalten private Bibliotheksdaten und Provider-Tokens. Das
Provider-Auth-Archiv sollte verschluesselt und nur fuer Administratoren lesbar
sein.

```bash
sudo install -d -o root -g root -m 0700 /var/backups/mutual-games-finder
cd /opt/mutual-games-finder
docker compose --env-file .env.production -f compose.production.yml exec -T database \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' |
  gzip |
  sudo tee /var/backups/mutual-games-finder/postgres-$(date +%F-%H%M).sql.gz >/dev/null

PROVIDER_AUTH_VOLUME="$(
  docker inspect \
    "$(docker compose --env-file .env.production -f compose.production.yml ps -q backend)" \
    --format '{{range .Mounts}}{{if eq .Destination "/provider-auth"}}{{.Name}}{{end}}{{end}}'
)"
test -n "$PROVIDER_AUTH_VOLUME"

sudo docker run --rm \
  -v "$PROVIDER_AUTH_VOLUME:/source:ro" \
  -v /var/backups/mutual-games-finder:/backup \
  mirror.gcr.io/library/alpine:3.21 \
  tar -C /source -czf /backup/provider-auth-$(date +%F-%H%M).tar.gz .
```

Die Backups sollten danach mit dem vorhandenen Server-Backupverfahren
verschluesselt auf ein anderes System kopiert werden. Empfohlen sind mindestens
14 Tagesstaende und ein regelmaessig getesteter Restore.

PostgreSQL-Restore in eine leere Datenbank:

```bash
gunzip -c /var/backups/mutual-games-finder/<backup>.sql.gz |
  docker compose --env-file .env.production -f compose.production.yml exec -T database \
  sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

## 8. Updates

Vor jedem Update zuerst ein Backup erstellen.

```bash
cd /opt/mutual-games-finder
git fetch --tags
git checkout <neuer-release-tag>
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml run --build --rm backend-tests
docker compose --env-file .env.production -f compose.production.yml rm --stop --force test-database
docker compose --env-file .env.production -f compose.production.yml up -d --remove-orphans
docker compose --env-file .env.production -f compose.production.yml ps
curl --fail http://127.0.0.1:18000/api/health
```

Container-Logs sind auf drei Dateien zu je 10 MiB begrenzt:

```bash
docker compose --env-file .env.production -f compose.production.yml logs --tail=200
```

## 9. Rollback

Bei einem reinen Anwendungsfehler kann der vorherige Release-Tag ausgecheckt
und neu gebaut werden. Wenn der neue Release Datenbankmigrationen ausgefuehrt
hat, muss zusaetzlich das unmittelbar vor dem Update erstellte PostgreSQL-
Backup wiederhergestellt werden.

```bash
cd /opt/mutual-games-finder
git checkout <vorheriger-release-tag>
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml up -d --remove-orphans
```

## 10. Neustarttest

Alle Dienste verwenden `restart: unless-stopped`.

```bash
sudo reboot
```

Nach dem Neustart erneut `docker compose ... ps`, den lokalen Healthcheck und
den externen HTTPS-Aufruf pruefen. Bestehende Apache-, PHP-, Postfix- und
Mumble-Dienste duerfen dabei keine geaenderten Ports oder Units aufweisen.
