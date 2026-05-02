# FV Neuhausen Vereinsspielplan als ICS-Kalender

Dieses Repo erzeugt automatisch eine `vereinsspielplan.ics` aus dem Vereinsspielplan von FUSSBALL.DE und aktualisiert sie täglich per GitHub Actions.

## Kalender-Link nach dem Upload

Wenn dein Repo z. B. `fvn-kalender` heißt und GitHub Pages aktiv ist:

```text
https://DEIN-GITHUB-NAME.github.io/fvn-kalender/vereinsspielplan.ics
```

## Einrichtung

1. Neues öffentliches GitHub-Repository erstellen, z. B. `fvn-kalender`
2. Alle Dateien aus diesem Paket hochladen
3. In GitHub unter `Settings → Pages` einstellen:
   - Source: `Deploy from a branch`
   - Branch: `main`
   - Folder: `/ (root)`
4. Unter `Actions` einmal `Update Vereinsspielplan ICS` manuell starten
5. Danach wird die ICS-Datei täglich automatisch aktualisiert

## Anpassungen

Im Script `generate_ics.py` kannst du oben diese Werte ändern:

- `CLUB_URL`
- `CALENDAR_NAME`
- `DEFAULT_EVENT_DURATION_HOURS`
- `DAYS_AHEAD`

Standardmäßig werden alle gefundenen Vereinsspielplan-Spiele der nächsten ca. 180 Tage eingetragen.
