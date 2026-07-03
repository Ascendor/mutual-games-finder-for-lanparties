# Stoerungs- und Notfallcheckliste

[Zur Startseite](Readme.md)

## 1. Auswirkung bestimmen

- Ist nur ein Provider-Sync betroffen?
- Funktioniert die Startseite?
- Funktioniert `/api/health` lokal?
- Sind andere Serverdienste ebenfalls betroffen?
- Gab es gerade Update, Reboot, Zertifikatwechsel oder Speicherprobleme?

## 2. Nichts vorschnell loeschen

Nicht verwenden:

```text
docker system prune --volumes
docker volume rm ...
git reset --hard
```

Keine Datenbank oder Volumes entfernen, bevor ein aktuelles Backup vorhanden
und geprueft ist.

## 3. Diagnosekette

```bash
cd /opt/refjuplay-together

docker compose --env-file .env.production \
  -f compose.production.yml ps

curl --noproxy "*" --max-time 10 \
  http://127.0.0.1:18000/api/health

curl --noproxy "*" --max-time 10 --head \
  http://127.0.0.1:18080/

sudo apachectl configtest
sudo systemctl status apache2 --no-pager

docker compose --env-file .env.production \
  -f compose.production.yml logs --tail=300

df -h
free -h
```

## 4. Fehlerbilder

### Frontend erreichbar, API nicht

- Backendstatus und Backendlogs pruefen.
- Datenbankstatus pruefen.
- Keine Syncs oder Imports mehrfach starten.

### Apache liefert 502

- Loopback-Ports `18000` und `18080` pruefen.
- Containerstatus pruefen.
- UFW-/FireHOL-Reihenfolge pruefen.

### Anwendung verlangt kein Basic Auth mehr

- aktiven VHost mit `apachectl -S` pruefen.
- `<Location "/">` und `AuthUserFile` pruefen.
- Apache-Konfiguration testen und neu laden.

### Datenbank startet nicht

- Datenbanklogs und freien Speicher pruefen.
- PostgreSQL-Volume nicht loeschen.
- Vor Reparatur ein Volume-/Dateisystembackup erstellen.

### Provider-Sync fehlgeschlagen

- Bestehende Ownerships bleiben erhalten.
- Synchronisationsprotokoll und Backendlogs pruefen.
- Token bei Bedarf neu verbinden.
- Kein Datenbankrestore nur wegen eines Providerfehlers.

## 5. Wiederanlauf

Einzelnen Dienst:

```bash
docker compose --env-file .env.production \
  -f compose.production.yml restart backend
```

Gesamte Anwendung:

```bash
docker compose --env-file .env.production \
  -f compose.production.yml up -d --remove-orphans
```

Danach immer:

```bash
docker compose --env-file .env.production \
  -f compose.production.yml ps

curl --fail http://127.0.0.1:18000/api/health
```

## 6. Eskalationsdaten notieren

- Zeit und beobachteter Fehler
- aktueller Release-Tag
- letzte Aenderung
- betroffener Dienst
- relevante Logs ohne Tokens
- freier Speicher und Containerstatus
- bereits ausgefuehrte Massnahmen

