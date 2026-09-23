# Mutual Games Finder

Lokale Fullstack-Webanwendung zum Zusammenfuehren von Spielebibliotheken mehrerer LAN-Party-Teilnehmer und zum Finden gemeinsamer Koop-, LAN- und Multiplayer-Spiele.

Die Anwendung ist fuer ein vertrautes LAN gedacht. Innerhalb der Anwendung gibt es absichtlich keine Rollen oder Rechteverwaltung: jeder angemeldete Benutzer darf alles bearbeiten. Der Docker-Betrieb setzt davor einen einfachen HTTPS-Reverse-Proxy mit Basic Auth.

## Stack

- Backend: Python 3.14, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL
- Frontend: Vue 3, TypeScript, Pinia, Vue Router, Vuetify
- Deployment: Docker Compose

## Start

```bash
python scripts/generate_env_secrets.py --output .env
docker compose up --build
```

Danach:

- Anwendung: https://localhost:8443
- HTTP-Redirect: http://localhost:8080
- Swagger/OpenAPI: https://localhost:8443/docs

Der Gateway nutzt ein selbstsigniertes TLS-Zertifikat. Der Browser wird deshalb beim ersten Aufruf eine Zertifikatswarnung anzeigen. Das Zertifikat bleibt im Docker-Volume `gateway-certs` erhalten.

Das Skript erzeugt fuer jede Installation unterschiedliche alphanumerische
Kennwoerter in der nicht versionierten Datei `.env`. Der Basic-Auth-Benutzer
lautet standardmaessig `lanparty`. Das In-App-Adminpasswort entsperrt nur die
Administrationsansichten; die eigentliche Zugriffskontrolle fuer die gesamte
Anwendung erfolgt durch Basic Auth am Gateway.

Ein einzelnes Kennwort kann spaeter gezielt rotiert werden:

```bash
python scripts/generate_env_secrets.py --output .env --rotate ADMIN_PASSWORD
```

Backend und Frontend werden im Docker-Compose-Betrieb nicht mehr direkt veroeffentlicht. Der Zugriff laeuft ueber den Gateway, damit TLS und Basic Auth nicht umgangen werden.

PostgreSQL speichert seine Daten im Docker-Volume `postgres-data`. Es ist das einzige unterstuetzte Datenbanksystem der Anwendung.

Die PostgreSQL-Zugangsdaten stehen ebenfalls in `.env`. Bei einer bestehenden
Datenbank darf `POSTGRES_PASSWORD` nicht nur in der Datei geaendert werden;
die Rolle muss zuerst innerhalb von PostgreSQL auf dasselbe Passwort umgestellt
werden.

## Name und Titel anpassen

Die sichtbare Bezeichnung einer Installation kann ohne Aenderungen am Quellcode
und ohne neuen Frontend-Build in `.env` beziehungsweise `.env.production`
angepasst werden. Ohne eigene Konfiguration lautet der Seitentitel
`Mutual Games Finder - Der Spielefinder`.

```env
APP_DISPLAY_NAME=Mutual Games Finder
APP_TITLE=Mutual Games Finder - Der Spielefinder
APP_SUBTITLE=Der Spielefinder
APP_SOURCE_URL=https://github.com/Ascendor/mutual-games-finder-for-lanparties
UPSTREAM_SOURCE_URL=https://github.com/Ascendor/mutual-games-finder-for-lanparties
APP_CLIENT_NAME=Mutual Games Finder
APP_AUTH_REALM=Mutual Games Finder
```

`APP_DISPLAY_NAME`, `APP_TITLE` und `APP_SUBTITLE` steuern die Texte im
Frontend. `APP_SOURCE_URL` verweist auf den Quelltext dieser Installation;
bei einem Fork kann `UPSTREAM_SOURCE_URL` zusaetzlich auf das Ursprungsprojekt
zeigen. `APP_CLIENT_NAME` ist die technische Bezeichnung gegenueber
angebundenen Diensten. `APP_AUTH_REALM` benennt den Anmeldedialog des lokalen
Docker-Gateways. In Produktion kommt dieser Dialog vom Apache-VHost; dessen
`AuthName` muss daher auf denselben Text gesetzt werden.

Technische Namen wie Compose-Projekt, Docker-Volumes und Serverpfade bleiben
absichtlich stabil. Eine reine Umbenennung der Anzeige veraendert keine Daten
und erfordert keine Migration.

Nach einer Aenderung der Env-Datei muessen die betroffenen Container neu
erstellt, aber nicht neu gebaut werden. Lokal betrifft das `backend`,
`steam-helper` und `gateway`; in der Produktionskonfiguration `backend` und
`steam-helper`. Ein geaenderter produktiver Apache-`AuthName` wird mit einem
Apache-Reload wirksam.

## Direkte Provider

Steam und Xbox verwenden dokumentierte Anmeldewege. Weitere Direktanbindungen
sind experimentell und bei neuen Installationen standardmaessig deaktiviert.
Sie koennen nach bewusster Risikoabwaegung mit
`UNOFFICIAL_PROVIDER_INTEGRATIONS_ENABLED=true` aktiviert werden. Details,
verarbeitete Zugangsdaten und Importalternativen stehen in
[`PROVIDERS.md`](PROVIDERS.md).

- Steam: wahlweise QR-Anmeldung mit vollstaendiger Bibliotheks- und Lizenzabfrage, offizieller Steam-Browser-Login ohne Token oder manuelle Verbindung ueber die oeffentliche Steam-Community-ID
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

Danach `docker compose up -d --build` ausfuehren. Auf `Accounts & Logins` zeigt der Xbox-Assistent einen einmaligen Code, oeffnet die Microsoft-Anmeldung und synchronisiert direkt nach der Bestaetigung.

Der Xbox-Webdienst liefert normalen Drittanbietern keine vollstaendige Microsoft-Store-Besitzliste. Importiert werden deshalb Eintraege aus der Xbox-Titelhistorie, die Microsoft mit dem Geraet `PC` kennzeichnet. Noch nie gestartete und nicht installierte Store-Spiele koennen fehlen; Konsolentitel werden bewusst ausgeschlossen. Ein Playnite-Backup kann diese Liste ergaenzen.

EA App kann ueber einen gefuehrten Browser-Login direkt synchronisiert oder alternativ ueber ein Playnite-Backup importiert werden. Der Assistent erkennt den Browser, erklaert das Kopieren der EA-GraphQL-Anfrage als cURL und speichert daraus nur den Bearer-Token. Die komplette cURL-Anfrage und darin enthaltene Cookies werden verworfen.

Der Steam-Assistent bietet drei bewusst getrennte Verbindungsarten:

- **QR-Anmeldung (empfohlen):** Der QR-Code wird mit der Steam-App bestaetigt.
  Ein interner Hilfsdienst liest SteamID, Bibliothek und vorhandene
  Lizenzzeitpunkte. Das Steam-Passwort gelangt nie zur Anwendung. Ein
  erneuerbares Zugangstoken wird im geschuetzten `provider-auth`-Volume
  gespeichert und fuer spaetere Synchronisationen intern wiederverwendet; es
  wird nie an den Browser zurueckgegeben.
- **Offizielle Browser-Anmeldung ohne gespeichertes Token:** Die Anwendung
  leitet zur offiziellen Steam-OpenID-Seite weiter. Benutzername, Passwort und
  Steam Guard werden ausschliesslich bei Steam eingegeben. Die Anwendung
  erhaelt nur die bestaetigte SteamID. Diese Variante benoetigt weder die
  Steam-Mobile-App noch ein gespeichertes Steam-Token.
- **Community-ID manuell:** Angegeben werden
  SteamID64, Profilname oder Profillink. Die Anwendung speichert nur die
  SteamID und die importierten Bibliotheksdaten. Dieser Weg ist ein manueller
  Fallback und bestaetigt nicht, dass die eingebende Person das Profil selbst
  kontrolliert.

Bei beiden tokenlosen Wegen muessen Profil und `Spieldetails` oeffentlich sein.
Spaetere Synchronisationen funktionieren ohne erneute Anmeldung ueber die
offizielle Steam Web API; sichtbare Spielzeiten werden aus `playtime_forever`
uebernommen. Private Bibliotheken koennen nicht gelesen werden.
Lizenz- und Erwerbszeitpunkte fehlen; ungenutzte oder deinstallierte
Gratisspiele koennen ebenfalls fehlen. Separat ausgeblendete Spielzeiten sind
in keiner der drei Verbindungsarten lesbar: Auch die QR-Anmeldung umgeht diese
Steam-Privatsphaereeinstellung nicht. Beim Wechsel vom QR-Login zu einer
tokenlosen Verbindung wird ein zuvor gespeichertes Steam-Token geloescht. Beim
Loeschen des Accounts werden dessen gespeicherte Anmeldedaten ebenfalls
entfernt.

## Playnite-Import

Auf der Seite `Accounts und Logins` kann pro Teilnehmer ein Playnite-JSON-Export oder ein Playnite-Backup-ZIP importiert werden. Der Gateway erlaubt Uploads bis 2 GB; der Wert kann in `.env` ueber `LAN_UPLOAD_LIMIT` angepasst werden, z.B. `LAN_UPLOAD_LIMIT=4g`. Der Import ordnet erkannte Quellen den vorhandenen Plattformen zu (`steam`, `epic`, `gog`, `ubisoft`, `ea`, `xbox` und weitere Playnite-Quellen) und nutzt vorhandene Accounts wieder, damit keine doppelten Ownerships neben direkten Provider-Syncs entstehen. Spiele ohne erkennbare Plattform werden als `local` importiert.

Direkte Provider-Syncs bleiben die bevorzugte Quelle fuer aktuelle Metadaten. Der Playnite-Import setzt deshalb nur vorsichtige Metadaten und ueberschreibt keine vertrauenswuerdigen Feature-Daten.

## GOG-Galaxy-Import

Als zweiter Komfort-Fallback kann auf `Accounts und Logins` eine lokale GOG-Galaxy-2.0-Bibliothek importiert werden. Erwartet wird entweder `C:\ProgramData\GOG.com\Galaxy\storage\galaxy-2.0.db` oder ein ZIP mit dieser Datei; wenn im ZIP auch `galaxy-2.0.db-wal` und `galaxy-2.0.db-shm` enthalten sind, werden diese mitgelesen. Am robustesten ist es, GOG Galaxy vorher zu schliessen oder den ganzen Ordner `storage` zu zippen.

Der Import liest nur die zentrale Galaxy-Bibliothek mit Plattform, Plattform-ID, Titel und Spielzeit. Plugin-Caches und gespeicherte Credentials werden nicht uebernommen. Erkannte PC-Plattformen werden auf die vorhandenen Plattformen gemappt, z.B. `origin` -> `ea`, `uplay` -> `ubisoft`, `battlenet` -> `battle_net` und `xboxone` -> `xbox`; bekannte Konsolenplattformen werden ignoriert.

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

Die Browser-Sitzungsanbindungen sind inoffiziell und koennen durch Aenderungen der Anbieter ausfallen oder eine erneute Anmeldung verlangen. Zugangspasswoerter werden dabei nicht an die Anwendung uebermittelt. Playnite-Backups und GOG-Galaxy-Datenbankimporte bleiben fuer alle Plattformen als Fallback verfuegbar.

## Entwicklung ohne Docker

Frontend und Steam-Helfer verwenden Node.js 24.21.0 LTS.

Backend ([uv](https://docs.astral.sh/uv/getting-started/installation/) installieren;
im Docker-Build ist uv 0.12.18 festgeschrieben). Python 3.14.7 wird durch uv aus
`backend/.python-version` installiert, auch beim Docker-Build:

```bat
cd backend
uv python install
set DATABASE_URL=postgresql+psycopg://lanparty:lanparty@localhost:5432/lanparty
uv sync --locked --group test
uv run --locked alembic upgrade head
uv run --locked uvicorn app.main:app --reload
```

Die Befehle oben verwenden die Windows-Eingabeaufforderung; unter Linux/macOS
statt `set` den Befehl `export DATABASE_URL=...` verwenden. uv verwaltet `.venv`
automatisch. `pyproject.toml` und `uv.lock` werden gemeinsam versioniert;
`--locked` bricht bei einer nicht passenden Lockdatei ab.

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

## Tests

```bash
docker compose run --build --rm backend-tests
```

Einzelne Tests: `docker compose run --build --rm backend-tests pytest tests/test_api.py`.
Der Testdienst nutzt das Docker-Buildziel `test` mit der Dependency-Group
`test` und startet eine eigene PostgreSQL-Testdatenbank im RAM. Produktionsdaten
und Provider-Tokens werden nicht eingebunden. Die Dienste gehoeren zum Profil
`testing` und starten nicht bei einem normalen `docker compose up`.
Nach den Tests kann die Testdatenbank gestoppt und entfernt werden:

```bash
docker compose rm --stop --force test-database
```

Das Backend-Produktionsimage enthaelt weder Testpakete noch Tests oder uv.
Der fruehere Testaufruf ueber den Dienst `backend` funktioniert daher nicht mehr.
Ausserhalb von Docker startet `uv run --locked --group test pytest` im Ordner
`backend` die Tests; `DATABASE_URL` oder `TEST_DATABASE_URL` muss dann auf eine
separate erreichbare PostgreSQL-Testdatenbank zeigen. Pro Testfall wird ein
temporaeres Schema angelegt und anschliessend entfernt.
Getestet werden Matching Engine, Normalisierung, Importer-Verhalten und
API-Integration.

Die Browser-Regressionstests pruefen Anmeldung, Spiel- und Mitspielerauswahl
sowie das Layout in Chromium, Firefox und einer mobilen Chromium-Ansicht.
Sie verwenden ausschliesslich synthetische API-Antworten, keine echten Accounts:

```bash
cd frontend
npm ci
npm run build
npx playwright install chromium firefox
npm run test:e2e
```

Unter Linux bei Bedarf `npx playwright install --with-deps chromium firefox`
verwenden. Die Kompatibilitaetsentscheidungen des aktuellen Upgrades stehen in
[`docs/dependency-upgrade-2026-09.md`](docs/dependency-upgrade-2026-09.md).

## Produktion auf Debian

Fuer einen vorhandenen Apache-VServer gibt es eine eigenstaendige
`compose.production.yml`. Sie startet keinen internen TLS-Gateway, bindet
Frontend und Backend nur an Loopback und laesst PostgreSQL ausschliesslich im
Docker-Netz.

Die vollstaendige manuelle Anleitung fuer DNS, Apache, Wildcard-Zertifikate,
Basic Auth, Backups, Updates und Rollback steht in
[`docs/production-deployment.md`](docs/production-deployment.md). Als Vorlage
fuer Secrets dient `.env.production.example`; echte Produktionswerte gehoeren
in die ignorierte Datei `.env.production`. Bei einer neuen Installation wird
sie mit zufaelligen alphanumerischen Werten erzeugt:

```bash
python3 scripts/generate_env_secrets.py \
  --template .env.production.example \
  --output .env.production
```

Bei einer bestehenden Produktionsdatenbank darf das PostgreSQL-Passwort nicht
allein durch erneutes Ausfuehren des Skripts geaendert werden; dazu muss auch
die Datenbankrolle kontrolliert rotiert werden.

## Lizenz, Datenschutz und Drittanbieter

Der eigene Quellcode steht unter der [MIT-Lizenz](LICENSE). Abhaengigkeiten,
Playnite-Referenzen, Legendary und externe Datenquellen sind in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) dokumentiert. Die
vollstaendigen Lizenztexte und versionierten Paketinventare liegen unter
[`LICENSES/`](LICENSES/); dort befinden sich ausserdem CycloneDX-SBOMs fuer
Backend, Frontend und Steam-Helfer.

Die Anwendung zeigt IGDB und RAWG als Metadatenquellen dauerhaft im Footer an.
Unter `/legal` sind die tatsaechlich verarbeiteten Daten, externe Uebertragungen
und inoffizielle Provider-Anbindungen beschrieben. Wer eine eigene Instanz
oeffentlich betreibt, muss dort eigene Kontaktdaten und gegebenenfalls weitere
Pflichtangaben ergaenzen.

Die Release-Checkliste fuer eine spaetere Quellcode- oder Image-Veroeffentlichung
steht in [`docs/open-source-compliance.md`](docs/open-source-compliance.md).
Das Sicherheitsmodell ist in [`SECURITY.md`](SECURITY.md) beschrieben; die
Bereinigung einer bestehenden Git-Historie in
[`docs/open-source-release.md`](docs/open-source-release.md).
