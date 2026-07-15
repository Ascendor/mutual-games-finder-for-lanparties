# LAN Party Game Finder

Lokale Fullstack-Webanwendung zum Zusammenfuehren von Spielebibliotheken mehrerer LAN-Party-Teilnehmer und zum Finden gemeinsamer Koop-, LAN- und Multiplayer-Spiele.

Die Anwendung ist fuer ein vertrautes LAN gedacht. Innerhalb der Anwendung gibt es absichtlich keine Rollen oder Rechteverwaltung: jeder angemeldete Benutzer darf alles bearbeiten. Der Docker-Betrieb setzt davor einen einfachen HTTPS-Reverse-Proxy mit Basic Auth.

## Stack

- Backend: Python 3.12+, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL
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

Das In-App-Adminpasswort ist im lokalen Compose-Setup ebenfalls auf `QC4lF93bYgwTHRT4xRynsAIz3San1lDW` gesetzt. Basic Auth schuetzt den Zugriff auf die gesamte Anwendung; das Adminpasswort entsperrt nur die Administrationsbereiche innerhalb der Anwendung.

Die Werte koennen in `.env` angepasst werden:

```env
BASIC_AUTH_USER=lanparty
BASIC_AUTH_PASSWORD=QC4lF93bYgwTHRT4xRynsAIz3San1lDW
ADMIN_PASSWORD=QC4lF93bYgwTHRT4xRynsAIz3San1lDW
```

Backend und Frontend werden im Docker-Compose-Betrieb nicht mehr direkt veroeffentlicht. Der Zugriff laeuft ueber den Gateway, damit TLS und Basic Auth nicht umgangen werden.

PostgreSQL speichert seine Daten im Docker-Volume `postgres-data`. Es ist das einzige unterstuetzte Datenbanksystem der Anwendung.

Die PostgreSQL-Zugangsdaten koennen in `.env` angepasst werden:

```env
POSTGRES_DB=lanparty
POSTGRES_USER=lanparty
POSTGRES_PASSWORD=lanparty
```

## Direkte Provider

- Steam: offizielle Steam Web API
- Epic: direkt ueber `legendary`
- GOG: direkt ueber GOG-Web-APIs mit Auth-Cache
- Ubisoft Connect: dialoggefuehrter Login mit optionaler 2FA
- Xbox Live: dialoggefuehrter Microsoft-Geraetecode-Login
- EA App: dialoggefuehrte Uebernahme der einmalig angemeldeten Browser-Sitzung

### Xbox Live einmalig einrichten

Der Login fuer die Teilnehmer benoetigt nur einen kurzen Microsoft-Code. Der Server braucht dafuer einmalig eine eigene Microsoft-Anwendungs-ID:

1. Im Microsoft Entra Admin Center unter `App registrations` eine neue Anwendung anlegen.
2. Als Kontotyp `Personal Microsoft accounts only` waehlen.
3. Unter `Authentication` die Option `Allow public client flows` aktivieren.
4. Die `Application (client) ID` in `.env` hinterlegen:

```env
XBOX_CLIENT_ID=00000000-0000-0000-0000-000000000000
```

Danach `docker compose up -d --build backend frontend` ausfuehren. Auf `Accounts & Logins` zeigt der Xbox-Assistent einen einmaligen Code, oeffnet die Microsoft-Anmeldung und synchronisiert direkt nach der Bestaetigung.

Der Xbox-Webdienst liefert normalen Drittanbietern keine vollstaendige Microsoft-Store-Besitzliste. Importiert werden deshalb Eintraege aus der Xbox-Titelhistorie, die Microsoft mit dem Geraet `PC` kennzeichnet. Noch nie gestartete und nicht installierte Store-Spiele koennen fehlen; Konsolentitel werden bewusst ausgeschlossen. Ein Playnite-Backup kann diese Liste ergaenzen.

EA App kann ueber einen gefuehrten Browser-Login direkt synchronisiert oder alternativ ueber ein Playnite-Backup importiert werden. Der Assistent erkennt den Browser, erklaert das Kopieren der EA-GraphQL-Anfrage als cURL und speichert daraus nur den Bearer-Token. Die komplette cURL-Anfrage und darin enthaltene Cookies werden verworfen.

## Playnite-Import

Auf der Seite `Accounts und Logins` kann pro Teilnehmer ein Playnite-JSON-Export oder ein Playnite-Backup-ZIP importiert werden. Der Gateway erlaubt Uploads bis 2 GB; der Wert kann in `.env` ueber `LAN_UPLOAD_LIMIT` angepasst werden, z.B. `LAN_UPLOAD_LIMIT=4g`. Der Import ordnet erkannte Quellen den vorhandenen Plattformen zu (`steam`, `epic`, `gog`, `ubisoft`, `ea`, `xbox` und weitere Playnite-Quellen) und nutzt vorhandene Accounts wieder, damit keine doppelten Ownerships neben direkten Provider-Syncs entstehen. Spiele ohne erkennbare Plattform werden als `local` importiert.

Direkte Provider-Syncs bleiben die bevorzugte Quelle fuer aktuelle Metadaten. Der Playnite-Import setzt deshalb nur vorsichtige Metadaten und ueberschreibt keine vertrauenswuerdigen Feature-Daten.

## Spielmetadaten

IGDB ist die primaere Quelle fuer Spielmodi, Spielerzahlen, Koop, LAN, Splitscreen, Genres und Basisdaten. RAWG wird nur verwendet, wenn IGDB kein passendes Spiel oder unvollstaendige Angaben liefert. Lege dafuer folgende Werte in `.env` ab:

```env
IGDB_CLIENT_ID=...
IGDB_CLIENT_SECRET=...
RAWG_API_KEY=...
```

Die IGDB-Zugangsdaten stammen aus einer Twitch-Developer-Anwendung. Anschliessend werden alle bestehenden Spiele ueber `Synchronisation` -> `Alle Metadaten aktualisieren` neu bewertet. Dieser Lauf laedt zuerst Steam-Store-Basisdaten fuer Steam-Spiele und ergaenzt danach Spielmodi, Spielerzahlen, Koop, LAN und weitere Felder ueber IGDB mit RAWG-Fallback.

Einen RAWG-Schluessel gibt es unter `https://rawg.io/apidocs`. HTTP 401 oder 403 kann auch bei ausgeschoepftem Monatskontingent auftreten. IGDB laeuft dann weiter und RAWG wird fuer diesen Metadatenlauf nach einem einzigen Vorabcheck uebersprungen. Nach dem Kontingent-Reset kann der Metadatenlauf ohne Datenverlust erneut gestartet werden.

## Amazon Games, Battle.net, Humble und Meta/Oculus

Diese Plattformen koennen unter **Accounts & Logins** fuer jeden Teilnehmer getrennt verbunden werden:

- Amazon Games verwendet den Anmeldeablauf des Amazon Games Launchers. Nach der Anmeldung wird die komplette Adresse der Abschlussseite in den Assistenten eingefuegt. Das gespeicherte Geraetetoken kann automatisch erneuert werden.
- Battle.net und Humble verwenden die angemeldete Browser-Sitzung. Der Assistent erkennt den Browser, erklaert das Kopieren der passenden Netzwerkanfrage als cURL und liest die Cookies selbst aus.
- Meta/Oculus verwendet ebenfalls eine kopierte Browser-Anfrage. Aus ihr wird ausschliesslich das fuer die Oculus-GraphQL-Bibliothek erforderliche `oc_ac_at`-Token gespeichert.
- EA verwendet eine kopierte Anfrage an `service-aggregation-layer.juno.ea.com/graphql`. Gespeichert wird ausschliesslich der Bearer-Token; Bibliothek und Spielzeiten werden anschliessend direkt von EA geladen.

Die Browser-Sitzungsanbindungen sind inoffiziell und koennen durch Aenderungen der Anbieter ausfallen oder eine erneute Anmeldung verlangen. Zugangspasswoerter werden dabei nicht an die Anwendung uebermittelt. Playnite-Backups bleiben fuer alle Plattformen als Fallback verfuegbar.

## Entwicklung ohne Docker

Das Frontend benoetigt ohne Docker Node.js 20.19 oder neuer.

Backend:

```bash
cd backend
set DATABASE_URL=postgresql+psycopg://lanparty:lanparty@localhost:5432/lanparty
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.lock
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
docker compose run --rm backend pytest
```

Die Tests legen pro Testfall ein eigenes temporaeres PostgreSQL-Schema an und
entfernen es danach wieder. Ausserhalb von Docker muss `DATABASE_URL` oder
`TEST_DATABASE_URL` auf eine erreichbare PostgreSQL-Datenbank zeigen.
Getestet werden Matching Engine, Normalisierung, Importer-Verhalten und
API-Integration.

## Produktion auf Debian

Fuer einen vorhandenen Apache-VServer gibt es eine eigenstaendige
`compose.production.yml`. Sie startet keinen internen TLS-Gateway, bindet
Frontend und Backend nur an Loopback und laesst PostgreSQL ausschliesslich im
Docker-Netz.

Die vollstaendige manuelle Anleitung fuer DNS, Apache, Wildcard-Zertifikate,
Basic Auth, Backups, Updates und Rollback steht in
[`docs/production-deployment.md`](docs/production-deployment.md). Als Vorlage
fuer Secrets dient `.env.production.example`; echte Produktionswerte gehoeren
in die ignorierte Datei `.env.production`.

## Lizenz, Datenschutz und Drittanbieter

Der eigene Quellcode steht unter der [MIT-Lizenz](LICENSE). Abhaengigkeiten,
Playnite-Referenzen, Legendary und externe Datenquellen sind in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) dokumentiert. Die
vollstaendigen Lizenztexte und versionierten Paketinventare liegen unter
[`LICENSES/`](LICENSES/); dort befinden sich ausserdem CycloneDX-SBOMs fuer
Backend und Frontend.

Die Anwendung zeigt IGDB und RAWG als Metadatenquellen dauerhaft im Footer an.
Unter `/legal` sind die tatsaechlich verarbeiteten Daten, externe Uebertragungen
und inoffizielle Provider-Anbindungen beschrieben. Wer eine eigene Instanz
oeffentlich betreibt, muss dort eigene Kontaktdaten und gegebenenfalls weitere
Pflichtangaben ergaenzen.

Die Release-Checkliste fuer eine spaetere Quellcode- oder Image-Veroeffentlichung
steht in [`docs/open-source-compliance.md`](docs/open-source-compliance.md).
