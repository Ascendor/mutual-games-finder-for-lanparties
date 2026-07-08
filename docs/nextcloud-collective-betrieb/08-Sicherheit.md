# Sicherheit und Zugangsdaten

[Zur Startseite](Readme.md)

## Gespeicherte Geheimnisse

- `.env.production`: Adminpasswort, Datenbankpasswort und API-Schluessel
- Provider-Auth-Volume: Sitzungs- und Refresh-Tokens
- Apache-htpasswd: Basic-Auth-Pruefsumme
- Backup-Sets: Kopien aller genannten Daten

Diese Inhalte niemals in Git, Tickets, Chat oder Screenshots posten.

## Dateirechte pruefen

```bash
cd /opt/refjuplay-together

stat -c '%a %U:%G %n' .env.production
sudo stat -c '%a %U:%G %n' \
  /etc/apache2/auth/refjuplay-together.htpasswd
sudo stat -c '%a %U:%G %n' \
  /var/backups/refjuplay-together
```

Erwartet:

- `.env.production`: `600`
- htpasswd-Datei: `640 root:www-data`
- Backup-Verzeichnis: `700 root:root`

## Basic-Auth-Passwort aendern

```bash
sudo htpasswd \
  /etc/apache2/auth/refjuplay-together.htpasswd \
  lanparty

sudo apachectl configtest
sudo systemctl reload apache2
```

## In-App-Adminpasswort aendern

```bash
cd /opt/refjuplay-together
joe .env.production

docker compose --env-file .env.production \
  -f compose.production.yml up -d --remove-orphans backend
```

Relevant ist `ADMIN_PASSWORD`. Das Passwort entsperrt die internen
Administrationsseiten; Apache Basic Auth bleibt davon unabhaengig.

## Provider-Zugang widerrufen

1. Account in der Anwendung trennen oder loeschen.
2. Sitzung beim jeweiligen Provider widerrufen.
3. Bei Verdacht auf Abfluss Passwort beim Provider aendern.
4. Neues Backup erst nach Bereinigung erstellen.

## API-Schluessel rotieren

1. Neuen Schluessel beim Anbieter erzeugen.
2. `.env.production` mit `sudo joe` oder `joe` bearbeiten.
3. Alten Schluessel beim Anbieter deaktivieren.
4. Backend mit `up -d --remove-orphans` neu erzeugen.
5. Provider- oder Metadatenzugriff testen.

```bash
cd /opt/refjuplay-together
joe .env.production

docker compose --env-file .env.production \
  -f compose.production.yml up -d --remove-orphans backend
```

## Zertifikate

Apache verwendet die vorhandenen Wildcard-Zertifikate des Hosts. Nach einer
Erneuerung:

```bash
sudo apachectl configtest
sudo systemctl reload apache2
```

Zertifikate und private Schluessel werden nicht nach Docker kopiert.

## Datenschutzangaben und Logrotation

Die installationsbezogenen Angaben in `.env.production` muessen aktuell
gehalten werden:

```bash
cd /opt/refjuplay-together
joe .env.production
```

Relevant sind insbesondere `PRIVACY_CONTROLLER_NAME`,
`PRIVACY_CONTROLLER_CONTACT`, `PRIVACY_HOSTING_PROVIDER` und die
Aufbewahrungsfristen. Nach einer Aenderung das Backend neu erzeugen.

Die mitgelieferte Logrotation begrenzt die App-spezifischen Apache-Protokolle:

```bash
cd /opt/refjuplay-together
sudo install -o root -g root -m 0644 \
  deploy/logrotate/refjuplay-together \
  /etc/logrotate.d/refjuplay-together
sudo logrotate --debug /etc/logrotate.d/refjuplay-together
```

Der Apache-VHost verwendet ein minimales Access-Log ohne Client-IP,
Query-String, Referrer und User-Agent. Fehlerprotokolle koennen weiterhin
Verbindungsdetails enthalten und werden deshalb ebenfalls rotiert.

## Externe Backups

Lokale Backups schuetzen nicht vor Serververlust. Das Verzeichnis
`/var/backups/refjuplay-together` muss verschluesselt in das bestehende
Offsite-Backup aufgenommen werden.
