# Rollback auf eine vorherige Version

[Zur Startseite](Readme.md)

Ein Rollback kann nur die Anwendung oder Anwendung plus Datenbank betreffen.

## Entscheidung

Nur Anwendung zurueckrollen, wenn:

- keine neue Datenbankmigration ausgefuehrt wurde oder
- die alte Version nachweislich mit dem neuen Schema kompatibel ist.

Anwendung und Datenbank zurueckrollen, wenn:

- Migrationen Daten oder Tabellen veraendert haben,
- die alte Version mit dem neuen Schema fehlschlaegt oder
- Daten durch das fehlerhafte Release veraendert wurden.

Im Zweifel den vollstaendigen Restore verwenden.

## Reiner Anwendungsrollback

```bash
cd /opt/mutual-games-finder

git fetch --tags
git checkout <vorheriger-release-tag>

docker compose --env-file .env.production \
  -f compose.production.yml build

docker compose --env-file .env.production \
  -f compose.production.yml up -d --remove-orphans

docker compose --env-file .env.production \
  -f compose.production.yml ps

curl --fail http://127.0.0.1:18000/api/health
```

## Vollstaendiger Rollback

1. Backend stoppen.
2. Vorupdate-Dump auswaehlen und Pruefsummen kontrollieren.
3. Datenbank nach [Backup wiederherstellen](03-Restore.md) restaurieren.
4. Den in `release-tag.txt` gespeicherten Release auschecken.
5. Images bauen und Compose starten.
6. Healthcheck, Logs und Browser pruefen.

## Wichtiger Hinweis

Nicht gleichzeitig:

- einen alten Release auschecken,
- aber die neue Datenbank ungeprueft behalten,
- und anschließend Alembic-Downgrades improvisieren.

Das getestete Rueckfallverfahren ist der Restore des Vorupdate-Backups.

## Rollback dokumentieren

Notieren:

- fehlerhafter Release
- Ziel-Release
- verwendeter Backup-Zeitstempel
- Zeitpunkt und Grund
- betroffene Funktionen
- Ergebnis der Healthchecks

