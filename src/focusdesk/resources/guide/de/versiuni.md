# Versionen, Checkpoints und Code {#versiuni-checkpointuri-si-acces-la-cod}
## Zweck {#la-ce-foloseste}
Checkpoint: lokale Kopie geeigneter gespeicherter Dateien zum Vergleichen/Wiederherstellen. Git ist getrennt und optional; Skripte werden nicht ausgeführt.
## Wo du es findest {#unde-il-gasesti}
Aufgabe **Versionen**; Quelle in [Dateien](guide:fisiere), Ausschlüsse/Limits unter **Einstellungen → Versionen & VS Code**.
## Checkpoint erstellen {#pasi-pentru-un-checkpoint}
1. Dateien im externen Editor speichern.
2. Eigene/geerbte/gemeinsame Quelle prüfen.
3. Beschreibung eingeben, **Checkpoint speichern**.
4. Enthaltene Dateien…, Mit aktuellem/vorherigem Stand vergleichen.
5. **In separatem Ordner wiederherstellen…** außerhalb der aktiven Quelle bevorzugen.
## Ergebnis und Speichern {#rezultatul-si-salvarea}
Archiv/Manifest berücksichtigen Ausschlüsse und Limits; unveränderter Inhalt kann ohne neue Kopie bleiben. Separate Wiederherstellung verändert Quelle nicht. Quelle überschreiben… ist ein eigener bestätigter Schutzvorgang.
## Automatisierung und Git {#automatizari-si-git}
Checkpoints am Sitzungsende/täglich brauchen Konfiguration und gültige Quelle. Planung läuft nur bei offener App. Git bietet Status/Log/Diff und manuelle Commits gewählter Dateien; kein automatisches push/reset/checkout.
## Häufige Fehler {#greseli-frecvente}
Checkpoint ist keine Arbeitsbereichsvoll­sicherung. Externe Zuordnung ändert keine Sicherungsregeln. Versionen und Arbeit jeder [Anforderung](guide:cerinte#folder-de-cod-comun) getrennt betrachten.
