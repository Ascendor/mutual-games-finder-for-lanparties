# Anwendung oder Server neu starten

[Zur Startseite](Readme.md)

## Welche Art Neustart ist richtig?

### Nur einen Container neu starten

Geeignet bei einem einmaligen Prozessproblem:

```bash
cd /opt/mutual-games-finder

docker compose --env-file .env.production \
  -f compose.production.yml restart backend
```

Moegliche Dienste: `backend`, `frontend`, `database`.

Die Datenbank nur mit Grund neu starten. Laufende Imports und Syncs vorher
beenden lassen.

### Neue Images oder Env-Werte aktivieren

`restart` reicht dafuer nicht:

```bash
docker compose --env-file .env.production \
  -f compose.production.yml up -d --remove-orphans
```

Nach Codeaenderungen vorher `build` ausfuehren.

### Apache-Konfiguration neu laden

```bash
sudo apachectl configtest
sudo systemctl reload apache2
```

`reload` ist einem harten Restart vorzuziehen.

### Ganzen Server neu starten

```bash
sudo reboot
```

SSH wird getrennt. Nach dem erneuten Login:

```bash
cd /opt/mutual-games-finder

systemctl is-active docker apache2 postfix mumble-server

docker compose --env-file .env.production \
  -f compose.production.yml ps

curl --fail http://127.0.0.1:18000/api/health

sudo ss -ltnup |
  grep -E ':(22|25|80|443|64738|18000|18080)\b'
```

## Nicht leichtfertig verwenden

`sudo systemctl restart docker` betrifft alle Docker-Anwendungen des Servers,
nicht nur den Spielefinder.

