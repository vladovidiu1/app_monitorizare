# E-Mail und Anhänge {#e-mail-si-atasamente}
## Zweck {#la-ce-foloseste}
Neue bearbeitbare Aufgabennachricht mit vollständiger Beschreibung erstellen und über Outlook Classic (Standard) oder Gmail mit App-Passwort senden. Kein Reply/ReplyAll oder Posteingangslesen. Nachrichtenänderungen ändern keine Aufgabe.
## Wo du es findest {#unde-il-gasesti}
**Ctrl+M**, **Organisieren → E-Mail aus Aufgabe…**, **Mehr → E-Mail verfassen…** oder **Dateien → An E-Mail anhängen…**.
## Tutorial H: vollständige Beschreibung und Dokumente {#tutorial-h-descriere-completa-si-documente-alese}
1. Bei ungespeicherter Beschreibung aktuellen Text (Standard), gespeicherte Version oder Abbrechen wählen; keine Metadaten speichern.
2. An, CC, Betreff ausfüllen. Erfundenen Beispieladressen niemals echte Nachrichten senden.
3. Nachricht bearbeiten; vollständiger Text, Zeilenumbrüche und Akzente bleiben ohne alte 600-Zeichen-Grenze. Aktualisieren ersetzt bearbeiteten Text nicht.
4. Benötigte [Anhänge](#atasamente) wählen.
5. **Entwurf in Outlook öffnen** oder **Senden**; Empfänger, Betreff, Anhangszahl/-größe bestätigen.
## Anhänge {#atasamente}
Dateien hinzufügen… erlaubt Mehrfachauswahl; Aufgaben-/Projektdateien enthalten auch manuell hinzugefügte Dokumente. Aus E-Mail entfernen ändert nur die Auswahl. Gleiche Namen bei anderen Pfaden bleiben verschiedene Dateien. Ordner werden nicht automatisch verpackt/angehängt. Dateien werden vor Übergabe erneut geprüft; ein abgelehnter Anhang stoppt alles ohne Teilversand.
## Ergebnis und Speichern {#rezultate-si-salvare}
Geöffneter Entwurf ist nicht gesendet. Übergabe an Outlook bedeutet erfolgreicher Send-Aufruf, keine Zustellung. Outlook-Postausgang/Gesendete Elemente prüfen. Der Verlauf enthält Ergebnis und Dateinamen, nicht den ganzen Nachrichtentext.
## Fehler und häufige Irrtümer {#erori-si-greseli-frecvente}
Enter sendet nicht. Fehler erhalten das Formular. Bei Timeout/unklarem Ergebnis Outlook prüfen, dann **Ich habe in Outlook geprüft…** und ausdrücklich erneut versuchen; nie automatisch. Verlaufsfehler rechtfertigt keinen Neuversand. Formular bleibt nach App-Ende nicht als lokaler Entwurf gespeichert. [Outlook](guide:setari#outlook-classic-si-lucru-offline).

## Gmail einrichten {#gmail-configurare}
Outlook Classic bleibt der Standard. Öffne **Einstellungen → Integrationen → E-Mail** oder **Gmail einrichten…** im Nachrichtenformular. Gib die Gmail-/Google-Workspace-Kontoadresse (auch mit eigener Domain) und optional einen Anzeigenamen ein. Beliebige Absender und ungeprüfte Aliasse werden nicht angeboten.

Aktiviere die Bestätigung in zwei Schritten im Google-Konto und erstelle über **Wie erhalte ich ein App-Passwort?** manuell ein App-Passwort im Browser unter `https://myaccount.google.com/apppasswords`. Gib das verdeckte App-Passwort ein, weder dein normales Passwort noch Bestätigungscodes. Nur Leerzeichen zur Gruppierung werden entfernt. Organisationsrichtlinien, Advanced Protection oder andere Kontobeschränkungen können App-Passwörter verhindern. Eine Änderung des Google-Passworts kann sie widerrufen. Dies ist weder OAuth noch „Sign in with Google“.

**Auf diesem Computer sicher speichern** verwendet die Windows-Anmeldeinformationsverwaltung. Das Geheimnis gelangt nicht in Arbeitsbereich, JSON, Journal oder Sicherungen. Ohne sichere Speicherung bleibt es nur im Sitzungsspeicher; nach Neustart erneut eingeben. **E-Mail-Einstellungen speichern** speichert nur das Computerprofil, keine Aufgabenänderungen. Können alte Anmeldedaten nicht gelöscht werden, bleiben Warnung und Referenz für die spätere Entfernung erhalten.

**Verbindung testen** prüft TLS und Anmeldung ohne Nachricht und ohne Speichern der Felder. Erfolg garantiert weder Nachrichtenannahme noch Zustellung. **Anmeldedaten entfernen** löscht das lokale Geheimnis und die Kontometadaten; bei Google das App-Passwort separat widerrufen.

## Gmail-Versand und Ergebnisse {#gmail-trimitere}
Wähle im selben Formular **Senden über → Gmail — Kontoadresse**. Anbieterwechsel und Einrichtung erhalten An, CC, Betreff, Text und Anhänge. Der Outlook-Kalender bleibt unverändert. Gmail benötigt kein Outlook; Versand und Verbindungstest benötigen Internet. Die übrige Anwendung bleibt offline.

**Senden** verlangt Bestätigung von Konto und Nachricht. SMTP nutzt `smtp.gmail.com:465`, geprüftes TLS und Zeitlimits, niemals eine unverschlüsselte Verbindung. Alle Dokumente werden vor der Übergabe gelesen; fehlende oder unlesbare Dateien verhindern unvollständige Nachrichten.

**Nachricht vom Gmail-Server zum Versand angenommen** bestätigt weder Zustellung noch Lesen. Teilannahme zeigt angenommene und abgelehnte Empfänger mit SMTP-Codes. **Nur abgelehnte Empfänger vorbereiten…** entfernt bereits angenommene Empfänger und verlangt eine neue Versandbestätigung. Kein automatischer Neuversand oder Wechsel zu Outlook. Ein Verbindungsabbruch bei der Übergabe kann ein ungewisses Ergebnis hinterlassen: Gmail/Empfänger vor **Ich habe Gmail geprüft…** prüfen. Ein Anbieterwechsel allein hebt die Sperre nicht auf.

SMTP erstellt keine Entwürfe in Gmail Web. **Als .eml speichern (lokal)…** erzeugt eine lokale Datei mit Text und Anhängen, ohne Versand oder Synchronisierung. **Entwurf in Outlook öffnen** gibt es nur für Outlook. Das Journal enthält Anbieter, Konto, Empfänger, Betreff, Zeitpunkt, Message-ID und Dateinamen, niemals Geheimnis oder SMTP-Dialog. Ein Journalfehler nach Annahme rechtfertigt keinen Neuversand.

Internet/DNS, Zeitüberschreitung, TLS/Zertifikate, Anmeldung, Empfänger und Kontolimits getrennt prüfen. Anmeldecodes unterscheiden ein falsches oder widerrufenes Passwort nicht immer von einer Kontorichtlinie. Fehler erhalten das Formular; TLS-Sicherheit nicht abschalten.
