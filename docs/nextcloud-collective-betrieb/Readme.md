# Mutual Games Finder - Betrieb

Diese Seiten beschreiben den Betrieb der produktiven Installation auf dem
Debian-VServer.

Fuer Nextcloud Collectives alle Markdown-Dateien gemeinsam in den Ordner des
Collectives hochladen. `Readme.md` wird als Startseite verwendet.

Zuletzt praktisch geprueft:

- Release: `v1.1.0`
- Datum: 3. Juli 2026
- Apache terminiert TLS und Basic Auth.
- Frontend lauscht auf `127.0.0.1:18080`.
- Backend lauscht auf `127.0.0.1:18000`.
- PostgreSQL ist nur im internen Docker-Netz erreichbar.
- Datenbank-Backup und isolierter Restore wurden erfolgreich getestet.
- Container starten nach einem Serverneustart automatisch.

## Runbooks

- [Tagesbetrieb und Schnellcheck](01-Tagesbetrieb.md)
- [Backup erstellen](02-Backup.md)
- [Backup pruefen und wiederherstellen](03-Restore.md)
- [Auf eine neue Version aktualisieren](04-Update.md)
- [Rollback auf eine vorherige Version](05-Rollback.md)
- [Anwendung oder Server neu starten](06-Neustart.md)
- [Monitoring und Fehlersuche](07-Monitoring-und-Fehlersuche.md)
- [Sicherheit und Zugangsdaten](08-Sicherheit.md)
- [Stoerungs- und Notfallcheckliste](09-Notfallcheckliste.md)
- [Regelmaessiger Wartungsplan](10-Wartungsplan.md)

## Standardpfade

Die folgenden Pfade gelten fuer Neuinstallationen. Eine bestehende Installation
muss nicht umbenannt werden; dort weiterhin das tatsaechlich vorhandene
Repository-, Backup- und Apache-Verzeichnis verwenden. Der Docker-Projektname
wird aus dem Repository-Verzeichnis abgeleitet, damit bestehende Volumes
erhalten bleiben.

```text
Repository:       /opt/mutual-games-finder
Produktions-Env:  /opt/mutual-games-finder/.env.production
Compose-Datei:    /opt/mutual-games-finder/compose.production.yml
Backups:          /var/backups/mutual-games-finder
Apache-VHost:     /etc/apache2/sites-available/mutual-games-finder.conf
Basic-Auth-Datei: /etc/apache2/auth/mutual-games-finder.htpasswd
```

## Grundregeln

1. Produktiv immer einen Release-Tag auschecken, nie einen beweglichen Branch.
2. Vor jedem Update ein neues Backup erstellen.
3. Echte Secrets niemals in Tickets, Chat, Git oder Screenshots posten.
4. Vor destruktiven Datenbankarbeiten Backend stoppen und Backup pruefen.
5. `docker compose restart` uebernimmt keine neuen Images oder Env-Werte.
6. Fuer Deployments immer `up -d --remove-orphans` verwenden.
7. PostgreSQL-Port `5432` niemals am Host veroeffentlichen.
8. Provider-Auth-Backups wie Passwoerter behandeln.

## Compose-Grundform

Alle Produktionsbefehle werden aus dem Repository ausgefuehrt:

```bash
cd /opt/mutual-games-finder
docker compose --env-file .env.production -f compose.production.yml ps
```

## Schnellster Funktionstest

```bash
cd /opt/mutual-games-finder

docker compose --env-file .env.production \
  -f compose.production.yml ps

curl --fail http://127.0.0.1:18000/api/health
```

Erwartet werden drei gesunde Container und:

```json
{"status":"ok"}
```
