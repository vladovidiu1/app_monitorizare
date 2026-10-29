# Dateien und Projektordner {#fisiere-si-folderul-proiectului}
## Zweck {#la-ce-foloseste}
Durchsuche echte Ordner, auch manuell hinzugefügte Dokumente. Navigation ändert keine Knotenmetadaten; Dokumente müssen nicht einzeln registriert werden.
## Wo du es findest {#unde-il-gasesti}
**Dateien** zeigt Projekt-/Arbeitsordner, Aufgabendateien (files/) und externe Links/Referenzen. Geerbte Wurzeln nennen die Quelle; Überlappung erzeugt keine Kopien.
## Tutorial G: Ordner zuordnen und Dokument finden {#tutorial-g-folder-asociat-si-document-pus-manual}
1. SAP-Projekt wählen, **Dateien → Aktionen → Projektordner wählen…**.
2. Bestehenden Ordner wählen; kein Verschieben oder Kopieren.
3. Projektaufgabe wählen, „Geerbt von“ prüfen.
4. Dokumente aufklappen; geschlossene Unterordner werden nicht rekursiv durchsucht.
5. Dokument im Explorer hinzufügen, dann zurückkehren oder Aktualisieren/F5 in Dateien.
6. Enter/Doppelklick öffnet sichere Dokumente; **An E-Mail anhängen…** übernimmt die Auswahl.
## Ergebnis und Speichern {#rezultatul-si-salvarea}
Dokumente erscheinen ohne node.json-Änderung. Aktualisieren erhält geöffnete Ordner; **Nächste 200 laden** erweitert große Listen. **Mehr Platz für Dateien** verbreitert den Aufgabenbereich.
## Kopien, Referenzen und Sicherheit {#copii-referinte-si-siguranta}
Hinzufügen… bietet verwaltete Kopie oder externen Link. Verwaltete Dateien gehören zur Vollsicherung, externe Links speichern nur Pfade. Entfernen der Referenz löscht kein Original; es kann sichtbar bleiben. Löschen verwalteter Kopien ist getrennt und bestätigt. Bestehende Links können neu zugeordnet werden. Skripte/Programme werden nicht versehentlich ausgeführt; VS Code/Explorer wählen. Symlinks/Junctions werden nicht automatisch verfolgt. Langsame Netzwerkordner rechtfertigen keine Datenlöschung. [Sicherung](guide:siguranta).
