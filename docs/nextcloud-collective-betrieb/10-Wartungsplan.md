# Regelmaessiger Wartungsplan

[Zur Startseite](Readme.md)

## Taeglich oder automatisiert

- PostgreSQL-, Provider-Auth- und Konfigurationsbackup erstellen.
- Sicherungsset verschluesselt auf ein anderes System uebertragen.
- Bei einer Monitoringmeldung Containerstatus und freien Speicher pruefen.

## Woechentlich

- Letzten erfolgreichen Backup-Zeitstempel kontrollieren.
- Pruefsummen des neuesten Backups kontrollieren.
- Freien Speicher unter `/`, `/var/lib/docker` und `/var/backups` pruefen.
- Auffaellige Apache- und Backendfehler ueberfliegen.

```bash
sudo ls -lht /var/backups/mutual-games-finder | head
df -h / /var/lib/docker /var/backups 2>/dev/null
```

## Monatlich

- Ein Backup nach [Restore](03-Restore.md) isoliert testen.
- Verfuegbare Release-Tags und sicherheitsrelevante Updates pruefen.
- `npm audit` und Backendtests beim Erstellen eines neuen Releases ausfuehren.
- Abgelaufene oder wiederholt fehlschlagende Provider-Verbindungen pruefen.
- Zertifikatslaufzeit kontrollieren.

```bash
cd /opt/mutual-games-finder
set -a
source .env.production
set +a

openssl s_client -connect "$APP_HOST:443" \
  -servername "$APP_HOST" </dev/null 2>/dev/null |
  openssl x509 -noout -subject -issuer -dates
```

## Vor jedem Release

- vollstaendiges Backup
- Release-Tag dokumentieren
- Compose-Konfiguration validieren
- Images bauen
- Backendtests ausfuehren
- Deployment und Healthchecks
- Browser-Abnahme

Siehe [Update](04-Update.md).

## Vor einer LAN-Veranstaltung

- alle Teilnehmer und Accounts einmal synchronisieren
- Metadatenlauf rechtzeitig vor Veranstaltungsbeginn ausfuehren
- grosses Playnite-Backup testweise importieren
- Basic-Auth-Zugang an die Gruppe verteilen
- freien Speicher und Swap pruefen
- aktuelles Backup extern sichern
- nach Beginn der Veranstaltung riskante Updates vermeiden

## Halbjaehrlich

- Serverneustart und automatischen Wiederanlauf testen
- Restore-Ablauf und Notfallcheckliste durchgehen
- nicht mehr benoetigte Accounts und Provider-Tokens entfernen
- Basic-Auth-Nutzerkreis und Serverzugriffe pruefen
- Aufbewahrungsfristen der Backups kontrollieren
