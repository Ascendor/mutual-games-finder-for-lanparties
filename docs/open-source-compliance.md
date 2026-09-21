# Open-Source- und API-Compliance

Diese Checkliste ist fuer private, nichtkommerzielle Releases dieses Projekts
gedacht. Sie ersetzt keine Rechtsberatung.

## Vor jedem Release

1. `LICENSE`, `THIRD_PARTY_NOTICES.md` und `LICENSES/` mit ausliefern.
2. Backend ausschliesslich aus `backend/requirements.lock`, Frontend und
   Steam-Helfer jeweils mit `npm ci` bauen.
3. Nach Abhaengigkeitsupdates die Inventare und gesammelten Lizenztexte
   erneuern:

   ```bash
   docker compose build backend frontend
   docker compose run --rm --no-deps \
     -v "$PWD/LICENSES:/out" -v "$PWD/scripts:/scripts:ro" backend \
     python /scripts/generate_backend_license_inventory.py
   docker run --rm -v "$PWD/frontend:/app" -v "$PWD/LICENSES:/out" \
     -v "$PWD/scripts:/scripts:ro" -w /app \
     mirror.gcr.io/library/node:20-alpine \
     sh -c "npm ci && node /scripts/generate_frontend_license_inventory.mjs /app /out"
   docker run --rm -v "$PWD/steam-helper:/app" -v "$PWD/LICENSES:/out" \
     -v "$PWD/scripts:/scripts:ro" -w /app \
     mirror.gcr.io/library/node:20-alpine \
     sh -c "npm ci && node /scripts/generate_frontend_license_inventory.mjs /app /out steam-helper lan-party-steam-helper"
   ```
   Danach muessen auch die drei `*.cdx.json`-Dateien als CycloneDX-SBOMs
   aktualisiert sein. `npm audit` muss separat bewertet werden;
   ein ungeprueftes `npm audit fix --force` ist kein Release-Schritt.
   Nach der Generierung die Images erneut bauen, damit sie die aktualisierten
   Inventare enthalten: `docker compose build backend frontend gateway steam-helper`.
4. Pruefen, dass `/licenses` in Backend-, Frontend- und Gateway-Image vorhanden
   ist.
5. Bei einer neuen Legendary-Version deren GPL-Lizenz, Versionsangabe und
   Corresponding-Source-Link aktualisieren.
6. IGDB-/RAWG-Attribution und die Seite `/legal` im gebauten Frontend pruefen.
7. API-Schluessel, Provider-Tokens, `.env` und Datenbank-Backups niemals in
   Quellcode, Image oder Release-Archiv aufnehmen.

## Backend-Abhaengigkeiten aktualisieren

`backend/pyproject.toml` beschreibt die gewuenschten direkten Abhaengigkeiten,
`backend/requirements.lock` die beim Docker-Build installierten Versionen
einschliesslich transitiver Abhaengigkeiten. Beide muessen zusammenpassen.
Ein Dependabot-PR, der nur `pyproject.toml` aendert, ist noch nicht vollstaendig.

Die Lockdatei im gleichen Python-/Linux-Umfeld wie das Backend regenerieren
(Befehle im Repository-Hauptverzeichnis ausfuehren):

```bash
docker run --rm -v "$PWD/backend:/work" -w /work \
  mirror.gcr.io/library/python:3.12-slim sh -ec '
    pip install pip-tools==7.6.1
    pip-compile --extra dev --strip-extras --allow-unsafe \
      --no-header --no-annotate --no-emit-index-url --no-emit-trusted-host \
      --output-file requirements.lock pyproject.toml
  '
docker compose build backend
docker compose run --rm backend pytest
```

Ohne `--upgrade` behaelt pip-compile bestehende transitive Versionen bei,
soweit sie mit den neuen Anforderungen vereinbar sind. Der Backend-Build
prueft die installierten Laufzeit- und Testabhaengigkeiten gegen
`pyproject.toml` und fuehrt `pip check` aus. Bei einer veralteten Lockdatei
bricht bereits der Build ab. Danach die Lizenzinventare wie oben erneuern
und gemeinsam mit Manifest und Lockdatei committen.

## Verteilung

Der reine Betrieb auf einem eigenen Server ist keine Weitergabe eines
Docker-Images. Werden Images oder Installationsarchive an Dritte verteilt,
muessen die darin enthaltenen Lizenztexte und Hinweise mitgeliefert werden.
Fuer das unveraendert enthaltene GPL-Programm Legendary muss der zu genau
dieser Version passende Quellcode erreichbar bleiben. Bei einer
Image-Veroeffentlichung sollte dessen Source-Archiv zusammen mit dem Image
angeboten und nicht nur auf ein moeglicherweise spaeter veraendertes
Upstream-Repository verwiesen werden:

```bash
python -m pip download --no-deps --no-binary=:all: \
  legendary-gl==0.21.1 --dest release-sources
```

Wird nur dieses Quellrepository angeboten und baut jeder Betreiber sein Image
selbst, wird Legendary beim Build unmittelbar aus der angegebenen Quelle
bezogen und kein vorgebautes Legendary-Objekt durch dieses Projekt verteilt.

## Provider und Daten

Die Provider-Anbindungen sind keine offiziellen Partnerschaften. Browser-
Sitzungen duerfen nur vom jeweiligen Accountinhaber fuer dessen eigene
Bibliothek bereitgestellt werden. Tokens werden lokal gespeichert und muessen
nach Trennung oder Loeschung eines Accounts entfernt werden.

RAWG-Daten duerfen nicht als eigenstaendige Datenbank weiterverteilt werden.
RAWG muss auf Seiten mit daraus stammenden Daten aktiv verlinkt sein. IGDB-
und Steam-Bedingungen verlangen ebenfalls transparente Datenverwendung,
Schutz der Schluessel und eine erreichbare Datenschutzinformation.

Bei einer spaeteren kommerziellen Nutzung sind mindestens IGDB, RAWG und die
inoffiziellen Provider-Anbindungen erneut anhand der dann geltenden
Bedingungen zu pruefen.
