# LAN Party Game Finder

Lokale Fullstack-Webanwendung zum Zusammenfuehren von Spielebibliotheken mehrerer LAN-Party-Teilnehmer und zum Finden gemeinsamer Koop-, LAN- und Multiplayer-Spiele.

Die Anwendung ist fuer ein vertrautes LAN gedacht. Innerhalb der Anwendung gibt es absichtlich keine Rollen oder Rechteverwaltung: jeder angemeldete Benutzer darf alles bearbeiten. Der Docker-Betrieb setzt davor einen einfachen HTTPS-Reverse-Proxy mit Basic Auth.

## Stack

- Backend: Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, SQLite
- Frontend: Vue 3, TypeScript, Pinia, Vue Router, Vuetify
- Deployment: Docker Compose

## Start

```bash
docker compose up --build
```

Danach:

- Anwendung: https://localhost:8443
- HTTP-Redirect: http://localhost:8080
- Swagger/OpenAPI: https://localhost:8443/docs

Der Gateway nutzt ein selbstsigniertes TLS-Zertifikat. Der Browser wird deshalb beim ersten Aufruf eine Zertifikatswarnung anzeigen. Das Zertifikat bleibt im Docker-Volume `gateway-certs` erhalten.

Default Basic Auth:

- Benutzer: `lanparty`
- Passwort: `QC4lF93bYgwTHRT4xRynsAIz3San1lDW`

Die Werte koennen in `.env` angepasst werden:

```env
BASIC_AUTH_USER=lanparty
BASIC_AUTH_PASSWORD=QC4lF93bYgwTHRT4xRynsAIz3San1lDW
```

Backend und Frontend werden im Docker-Compose-Betrieb nicht mehr direkt veroeffentlicht. Der Zugriff laeuft ueber den Gateway, damit TLS und Basic Auth nicht umgangen werden.

Die SQLite-Datenbank wird im Docker-Volume `backend-data` gespeichert.

## Direkte Provider

- Steam: offizielle Steam Web API
- Epic: direkt ueber `legendary`
- GOG: direkt ueber GOG-Web-APIs mit Auth-Cache

Epic-Login im Backend-Container:

```bash
docker compose exec backend legendary auth
```

GOG erwartet einen Auth-Cache unter `/config/heroic_gogdl/auth.json`, persistent im Volume `gogdl-config`.

Xbox, Ubisoft Connect und EA App sind im Code als eigene Provider angelegt, aber ihre direkten API-/Auth-Adapter sind noch offen.

## Entwicklung ohne Docker

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend
pytest
```

Getestet werden Matching Engine, Normalisierung, Importer-Verhalten und API-Integration.
