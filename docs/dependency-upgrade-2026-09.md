# Dependency-Upgrade September 2026

Stand der Paketpruefung: 23. September 2026. Verwendet werden ausschliesslich
stabile Releases. Versionslisten wurden gegen PyPI, npm und die offiziellen
Runtime-Releases geprueft. Die Lockdateien enthalten die aufgeloesten Versionen
und Hashes; die Lizenzinventare und CycloneDX-SBOMs wurden neu erzeugt.

## Ergebnis

| Bereich | Getesteter Stand |
| --- | --- |
| Python | 3.14.7, durch uv 0.12.18 installiert |
| Backend | Direkte Abhaengigkeiten bereits aktuell; 17 transitive Updates |
| Node.js | 24.21.0 LTS fuer Frontend-Build und Steam-Helfer |
| Vue | 3.5.43 |
| Pinia | 4.0.3 |
| Vue Router | 5.3.1 |
| Vuetify | 4.2.1 |
| Vite / Vue-Plugin | 8.3.0 / 6.0.9 |
| TypeScript / vue-tsc | 6.0.3 / 3.3.11 |
| Playwright | 1.63.0, nur fuer Entwicklung und CI |
| nginx | 1.30.5, stabiler Release-Zweig |
| Steam-Helfer | steam-user 5.3.0, steam-session 1.9.4, qrcode 1.5.4 |

Python wird aus `backend/.python-version` auch im Docker-Build ueber
`uv python install` bezogen. Der fertige Container enthaelt den Interpreter
und die Runtime-Abhaengigkeiten, aber weder uv noch Tests oder Testpakete.
Die separate Dependency-Group `test` bleibt dem Test-Image vorbehalten.

## Bewusste Kompatibilitaetsgrenzen

- TypeScript 7.0.2 wurde ausprobiert. Der Build scheitert mit
  `ERR_PACKAGE_PATH_NOT_EXPORTED` fuer `typescript/lib/tsc` in vue-tsc 3.3.11.
  6.0.3 ist deshalb die neueste getestete kompatible stabile Version.
- Node.js 26.10.0 ist neuer, aber noch im Current-Zweig. Verwendet wird der
  aktuelle LTS-Zweig mit dem dort mitgelieferten npm.
- Der Steam-Helfer benoetigt protobufjs 7 gemaess seinen Upstream-Abhaengigkeiten.
  Der Override wurde auf 7.6.6 aktualisiert; Version 8.8.0 wird nicht gegen den
  deklarierten Major-Vertrag erzwungen. adm-zip bleibt bei 0.6.1.
- PostgreSQL bleibt bei Major-Version 17. Ein Wechsel auf 18 benoetigt einen
  eigenen Datenmigrationsplan und ist kein Bestandteil dieses Library-Upgrades.
- Keine Betas, RCs, Nightlies oder experimentellen Python-Varianten.
  Der uv-Resolver verbietet Prereleases explizit.

## Anpassungen an der Oberflaeche

Vuetify 4 benoetigt neue Typografieklassen, eine explizite CSS-Layer-Reihenfolge
und angepasste Item-Slots fuer die Teilnehmerauswahl. Die Checkboxen und
Realnamen in den Dropdowns bleiben erhalten. Die Hauptnavigation wird auf
schmalen Bildschirmen eingeklappt; die Startaktionen erhalten lesbare Umbrueche.
Router- und Store-Verhalten bleiben erhalten.

## Verifikation

- Backend: 165 Unit- und Integrationstests erfolgreich, gegen eine isolierte
  PostgreSQL-Testdatenbank unter Python 3.14.7.
- Frontend: TypeScript-Pruefung und Produktionsbuild erfolgreich.
- Browser: 16 Tests erfolgreich, zwei Desktop-Ausfuehrungen eines reinen
  Mobiltests absichtlich uebersprungen. Anmeldung/Abmeldung, Spiel-Autocomplete, Teilnehmer-Checkboxen,
  vorausgefuellte Suche, Tabellensortierung, Genre- und Singleplayerfilter,
  mobile Navigation und Layout werden automatisiert geprueft.
- Steam-Helfer: Syntaxpruefung, Start und Health-Endpunkt erfolgreich.
- npm-Audits fuer Frontend und Steam-Helfer sowie pip-audit fuer die
  Backend-Runtime: keine bekannten Sicherheitsluecken zum Pruefzeitpunkt.
- Lokale und Produktions-Compose-Konfiguration validiert; Images lokal gebaut.
- Lokaler Gesamtstack gestartet; Backend, Frontend und Steam-Helfer antworten.
- Gateway: ohne Zugangsdaten HTTP 401; mit Basic Auth liefern `/`,
  `/api/health` und `/legal/` ueber HTTPS jeweils HTTP 200.
- Runtime-Trennung geprueft: kein pytest, freezegun, uv oder Testordner im
  Produktions-Backend.

Die Browser-Suite laeuft auch in GitHub Actions und verwendet synthetische
API-Daten. Echte Store-Anmeldungen und Synchronisationen mit persoenlichen
Accounts wurden nicht erneut durchgefuehrt. Verbleibende Hinweise sind
bestehende Deprecation-Warnungen im Backend und die Frontend-Bundlewarnung
fuer einen Chunk ueber 500 kB; sie sind keine Build- oder Testfehler.

## Ausrollen

Normalen Deployment-Prozess mit Backup, neuem Release-Tag, Image-Neubau und
`up -d` verwenden. Keine neuen `.env`-Werte, keine neue Datenbankmigration und
keine Volume-Loeschung erforderlich. Auf dem Produktionshost muss Python
nicht separat installiert werden. Dieses Upgrade fuehrt selbst keinen Push,
Release oder produktiven Rollout aus.

Ohne Docker: Node.js 24.21.0 verwenden, im Backend `uv python install` und
`uv sync --locked --group test`, im Frontend und Steam-Helfer jeweils `npm ci`.
Die ausfuehrlichen Testbefehle stehen in README und CONTRIBUTING.

## Primaerquellen

- [uv und Docker](https://docs.astral.sh/uv/guides/integration/docker/)
- [Python-Releases](https://www.python.org/downloads/)
- [Node.js-Release-Zweige](https://nodejs.org/en/about/previous-releases)
- [Vuetify-Upgrade-Leitfaden](https://vuetifyjs.com/en/getting-started/upgrade-guide/)
- [Vue Router 4 auf 5](https://router.vuejs.org/guide/migration/v4-to-v5)
- [nginx-Releases](https://nginx.org/en/download.html)
