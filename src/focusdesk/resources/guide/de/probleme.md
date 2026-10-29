# Häufige Probleme und Grenzen {#probleme-frecvente-si-limitari}
## Abgeschlossene Aufgabe fehlt {#nu-gasesc-un-task-finalizat}
Abgeschlossen/Geschlossen und passende Filter, zusätzlich Archiv prüfen. Projektlinks ändern keine Zuordnung. [Wiederöffnung und neue Anforderung](guide:cerinte) unterscheiden sich.
## Beschreibung nicht erhalten {#descrierea-nu-s-a-pastrat}
Assistent verändert Entwurf; Speichern/Ctrl+S schreibt ihn. Abbrechen im erweiterten Editor stellt Ausgangstext wieder her. Journalnotizen brauchen ausdrückliche Aufnahme; [Besprechungsnotizen](guide:intalniri) speichern automatisch.
## Neues Dokument fehlt {#un-document-nou-nu-apare}
Dateiwurzel prüfen, Ordner öffnen und Aktualisieren/F5. Nicht verfügbare Ordner können alte Listen zeigen, ohne aktuelle Verfügbarkeit zu beweisen. Links/Junctions werden nicht automatisch verfolgt. [Dateien](guide:fisiere).
## Geplante Zeit übersteigt Arbeitszeit {#vad-programat-dar-nu-am-lucrat-atat}
Reservierungen sind keine Arbeit. Gespeicherte Dauer und Live-Zeit bleiben separat; Besprechungen addieren keine Arbeit. Filter prüfen und nur identifizierte beendete Sitzungen korrigieren. [Rechenregeln](guide:activitate).
## Outlook antwortet nicht oder Modul fehlt {#outlook-nu-raspunde-sau-lipseste-un-modul}
Outlook Classic verwenden, Unternehmensrichtlinien beachten. `ModuleNotFoundError: win32timezone` bedeutet fehlende pywin32-Komponente; ein EXE-Bundle muss korrekt neu gebaut werden, separate Python-Installation repariert es nicht. Nach Send-Timeout Outlook-Fenster, Entwürfe, Postausgang und Gesendete Elemente vor Neuversuch prüfen. Erfolgreiches COM ist keine Zustellung. [E-Mail-Fehler](guide:email#erori-si-greseli-frecvente).
## Speichern verweigert oder externe Änderungen {#salvare-refuzata-sau-modificari-externe}
Entwürfe schützen. F5 erhält Konfliktprüfungen; Originaldateien nicht blind überschreiben. Andere Prozesssperre kann Schreibschutz bedeuten. Integritätsprüfung meldet Probleme ohne automatische Datenlöschung.
## Leistung und Sicherheit {#limite-de-performanta-si-siguranta}
Erste Indexrekonstruktion/globale Beschreibungssuche kann mehr Dateien lesen. Dateien durchsucht offene Ordner; Handbuchsuche nur mitgelieferte Dokumentation. Indexe sind löschbar, ersetzen keine Sicherung. Kein SQL/SQLite oder Cloud-Datensync.
## Auf eigenem Rechner prüfen {#ce-trebuie-verificat-pe-calculatorul-tau}
Echtes Outlook/COM-Richtlinien, Dateizuordnungen, VS Code, Junctions, natives DPI und Windows-EXE hängen vom Zielsystem ab. Fake-Backend/Linux-Skalierung zertifizieren sie nicht. Blockierte Netzwerkaufrufe lassen sich nicht sicher zwangsabbrechen. Wiederherstellung auf temporären Daten testen; externe Ordner separat sichern.
