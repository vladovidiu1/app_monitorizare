# Aktivität verstehen {#activitate-intelegerea-dashboardului}
## Zweck {#la-ce-foloseste}
Dashboard, Monatskalender, Tabellen und CSV verwenden ein Rechenmodell, ohne Doppelzählung von Eltern- und Unteraufgaben.
## Wo du es findest {#unde-il-gasesti}
**Aktivität**; **Monatskalender · Ctrl+D** öffnet die Zusatzansicht.
## Tutorial J: Arbeitszeit prüfen {#tutorial-j-verifica-timpul-lucrat}
1. 7/30/90 Tage, Aktueller Monat, Eigener Zeitraum oder Gesamter Verlauf wählen.
2. Projekt oder Ohne Projekt wählen; eigene Daten ausdrücklich anwenden.
3. Aufgezeichnete Arbeit und Geplant vergleichen, nicht als Arbeit addieren.
4. Tag/Projekt im Diagramm wählen; **Detail entfernen** oder **Filter zurücksetzen**.
5. Enter/Doppelklick auf Sitzung öffnet Aufgabe; Rückkehr erhält Kontext.
6. **CSV exportieren** berücksichtigt Filter, Definitionen, Akzente und Excel-Formelschutz.
## Kennzahlen lesen {#cum-interpretezi-cardurile}
Aufgezeichnete Arbeit summiert gespeicherte actual_seconds einmal pro Sitzung, auch für abgeschlossene/archivierte/fehlende Aufgaben. Tag ist tatsächlicher Beginn, ersatzweise geplanter Beginn, in Arbeitsbereichszeitzone. Ungespeicherte Live-Zeit bleibt separat. Geplant umfasst anrechenbare Reservierungen ohne cancelled/missed. Besprechungen erhöhen keine Summe.
Abgeschlossen zählt einzelne Aufgaben mit done-Übergang im Zeitraum; Wiederöffnung/erneuter Abschluss zählt nicht doppelt. Fehlender Altverlauf wird nicht aus updated_at erfunden. Jetzt überfällig und Status zeigen den aktuellen Zustand, Projekte aktuelle Zuordnung. Große Zeiträume werden sichtbar nach Wochen/Monaten aggregiert.
## Speichern und häufige Fehler {#salvare-si-greseli-frecvente}
Filter ändern keine Sitzungen. Export schreibt ausdrücklich die gewählte Datei. Nur erkennbare beendete Sitzungen korrigieren, Summen erneut prüfen. Stunden sind keine Produktivitätsbewertung. [Sitzungen](guide:sesiuni).
