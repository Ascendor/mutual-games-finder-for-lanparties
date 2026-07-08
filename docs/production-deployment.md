# Produktionsbetrieb auf einem Debian-VServer

Die auf einzelne Aufgaben aufgeteilten Betriebs-Runbooks fuer Nextcloud
Collectives liegen unter
[`docs/nextcloud-collective-betrieb/`](nextcloud-collective-betrieb/Readme.md).

Diese Anleitung beschreibt die spaetere manuelle Installation unter
`https://refjuplay-together.<deine-domain>`. Apache bleibt der einzige
oeffentliche Webserver. Die Docker-Container lauschen ausschliesslich auf
Loopback-Adressen; PostgreSQL besitzt keinen Host-Port.

Das vorhandene `docker-compose.yml` bleibt fuer den lokalen Betrieb bestimmt.
Auf dem VServer wird ausschliesslich `compose.production.yml` verwendet.

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
sudo install -d -o "$USER" -g "$USER" /opt/refjuplay-together
git clone https://codeberg.org/Ascendor/ref_ju_geeks-play-together.git /opt/refjuplay-together
cd /opt/refjuplay-together
git fetch --tags
git checkout <release-tag>
```

Fuer produktive Updates sollte immer ein getesteter Release-Tag statt eines
beweglichen Branches verwendet werden.

## 3. Produktionsvariablen anlegen

```bash
cd /opt/refjuplay-together
cp .env.production.example .env.production
chmod 600 .env.production
joe .env.production
openssl rand -hex 32
```

Den ausgegebenen Zufallswert als `POSTGRES_PASSWORD` eintragen und mindestens
folgende Werte anpassen:

```env
APP_HOST=refjuplay-together.example.org
ADMIN_PASSWORD=<zufaelliges-admin-passwort>
POSTGRES_DB=lanparty
POSTGRES_USER=lanparty
POSTGRES_PASSWORD=<zufaelliger-hex-wert>
STEAM_API_KEY=
IGDB_CLIENT_ID=
IGDB_CLIENT_SECRET=
RAWG_API_KEY=
XBOX_CLIENT_ID=
PLAYNITE_UPLOAD_MAX_BYTES=4294967296
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
cd /opt/refjuplay-together
docker compose --env-file .env.production -f compose.production.yml config --quiet
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml run --rm backend pytest
docker compose --env-file .env.production -f compose.production.yml up -d
docker compose --env-file .env.production -f compose.production.yml ps
```

Alembic aktualisiert die PostgreSQL-Datenbank automatisch beim Backend-Start.

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
sudo htpasswd -c /etc/apache2/auth/refjuplay-together.htpasswd lanparty
sudo chown root:www-data /etc/apache2/auth/refjuplay-together.htpasswd
sudo chmod 0640 /etc/apache2/auth/refjuplay-together.htpasswd
```

Die Vorlage installieren:

```bash
sudo cp deploy/apache/refjuplay-together.conf.example \
  /etc/apache2/sites-available/refjuplay-together.conf
sudo joe /etc/apache2/sites-available/refjuplay-together.conf
sudo install -o root -g root -m 0644 \
  deploy/logrotate/refjuplay-together \
  /etc/logrotate.d/refjuplay-together
```

In der Kopie muessen der echte `ServerName` sowie die bereits vorhandenen
Wildcard-Pfade fuer `SSLCertificateFile` und `SSLCertificateKeyFile`
eingetragen werden. Zertifikate werden nicht in das Repository oder in Docker
kopiert.

```bash
sudo a2ensite refjuplay-together.conf
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
curl --head https://refjuplay-together.example.org/
curl --user lanparty https://refjuplay-together.example.org/api/health
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
sudo install -d -o root -g root -m 0700 /var/backups/refjuplay-together
cd /opt/refjuplay-together
docker compose --env-file .env.production -f compose.production.yml exec -T database \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' |
  gzip |
  sudo tee /var/backups/refjuplay-together/postgres-$(date +%F-%H%M).sql.gz >/dev/null
sudo docker run --rm \
  -v refjuplay-together_provider-auth:/source:ro \
  -v /var/backups/refjuplay-together:/backup \
  mirror.gcr.io/library/alpine:3.21 \
  tar -C /source -czf /backup/provider-auth-$(date +%F-%H%M).tar.gz .
```

Die Backups sollten danach mit dem vorhandenen Server-Backupverfahren
verschluesselt auf ein anderes System kopiert werden. Empfohlen sind mindestens
14 Tagesstaende und ein regelmaessig getesteter Restore.

PostgreSQL-Restore in eine leere Datenbank:

```bash
gunzip -c /var/backups/refjuplay-together/<backup>.sql.gz |
  docker compose --env-file .env.production -f compose.production.yml exec -T database \
  sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

## 8. Updates

Vor jedem Update zuerst ein Backup erstellen.

```bash
cd /opt/refjuplay-together
git fetch --tags
git checkout <neuer-release-tag>
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml run --rm backend pytest
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
cd /opt/refjuplay-together
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
