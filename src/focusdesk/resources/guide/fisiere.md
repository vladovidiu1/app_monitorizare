# Fișiere și folderul proiectului

## La ce folosește
Exploratorul arată foldere și documente reale, inclusiv cele adăugate manual pe disc. Nu trebuie înregistrat fiecare document drept Attachment. Navigarea nu schimbă metadatele și nu marchează taskul ca editat.

## Unde îl găsești
Tabul **Fișiere** din inspector/spațiul taskului. Sursele sunt **Folderul proiectului / de lucru**, **Fișierele taskului** din files/ și **Legături externe / alte referințe**. Un folder moștenit este etichetat cu proiectul sursă; suprapunerile sunt explicate fără copiere suplimentară.

## Tutorial G: folder asociat și document pus manual
1. Selectează proiectul `Automatizare raport SAP`, deschide **Fișiere** și alege **Acțiuni → Alege folderul proiectului…**. Fără asociere, aceeași comandă este oferită direct în tab.
2. Alege un folder real cu documente. Asocierea externă nu mută și nu copiază folderul.
3. Selectează un task al proiectului și verifică rădăcina și **Moștenit de la …**.
4. Extinde subfolderul `Documente`. Directoarele închise nu sunt scanate recursiv, iar dimensiunile folderelor nu sunt calculate.
5. Copiază manual un document în acel subfolder, în Windows Explorer. Revino în FocusDesk sau apasă **Actualizează** / **F5** cu focusul în explorator.
6. Selectează documentul. Dublu-click/Enter îl deschide în aplicația asociată dacă este sigur; **Acțiuni → Atașează la e-mail…** îl preselectează în formularul de e-mail.

## Rezultatul și salvarea
Documentul apare fără modificarea node.json sau creare automată de referință. Actualizarea păstrează contextul pentru directoarele deschise. Listele mari continuă prin **Încarcă următoarele 200**. În spațiul taskului, **Acțiuni → Mai mult spațiu pentru Fișiere** lărgește panoul.

## Copii, referințe și siguranță
**Adaugă…** oferă copie administrată sau legătură externă. Copia din files/ intră în backupul complet; legătura externă memorează calea și nu garantează backupul originalului. **Elimină doar legătura/referința…** nu șterge documentul: acesta poate continua să apară pe disc. Ștergerea copiei administrate este separată și cere confirmare; nu există ștergere generală a documentelor descoperite.

**Legături și referințe existente…** permite gestionarea referințelor vechi, inclusiv când folderul lor lipsește. Scripturile/executabilele nu sunt lansate accidental: alege VS Code sau Explorer. Symlinkurile/junctions sunt afișate fără traversare automată. Un director de rețea poate răspunde lent; erorile nu justifică ștergerea datelor.

[Folder comun pentru o cerință ulterioară](guide:cerinte) · [Backup](guide:siguranta) · [E-mail](guide:email).
