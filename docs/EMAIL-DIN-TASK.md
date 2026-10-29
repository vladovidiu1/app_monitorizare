# E-mail din task

Din inspector, spațiul taskului, meniul contextual sau Ctrl+M, compune un mesaj nou prin Outlook Classic (implicit) sau [Gmail cu parolă de aplicație](GMAIL.md). Formularul, ciorna editabilă și selecția documentelor sunt comune. Outlook păstrează ComWorker, Gmail folosește UiBridge pentru SMTP; UI și jurnalul se actualizează pe firul Tk. Nu există citire de inbox sau trimitere fără acțiunea utilizatorului. Detaliile și rezultatele Outlook de mai jos descriu etapa inițială; verificarea Gmail este separată.

## Descriere și ciornă

Contextul include titlul, locația în proiect, statusul, prioritatea, termenul, următorul pas și **descrierea completă**, fără limita veche de 600 de caractere. Se păstrează diacriticele, liniile goale și indentarea; descrierea goală nu adaugă o secțiune. Mesajul este text simplu, nu HTML.

Dacă descrierea din bufferul comun diferă de versiunea salvată, alegi explicit:

- **Folosește descrierea curentă** — opțiunea implicită;
- **Folosește ultima versiune salvată**;
- **Anulează**.

Alegerea nu salvează taskul sau celelalte metadate editate. Corpul e-mailului este un snapshot independent, editabil; modificarea sa nu modifică descrierea din inspector/spațiul de lucru. Refreshul aplicației nu regenerează mesajul. Citirea snapshotului salvat păstrează reperul editorului pentru conflicte externe; nu autorizează suprascrierea unei descrieri schimbate din alt program.

## Atașamente

**Adaugă fișiere…** permite selecție multiplă de pe calculator. **Din fișierele taskului/proiectului…** deschide selectorul local: locațiile taskului și strămoșilor săi, referințele externe și folderul de cod efectiv. Se listează un singur director la cerere, inclusiv documentele puse manual pe disc, nu numai referințele `node.attachments`. Directoarele mari sunt sortate integral și afișate în loturi de 200; Enter/dublu-click deschide un folder, Alt+↑ revine în folderul părinte. Ctrl/Shift selectează mai multe documente.

Nu se selectează automat toate fișierele proiectului. Nu se copiază documente în workspace pentru e-mail, nu se atașează și nu se arhivează automat directoare. Selectorul nu traversează automat symlinkuri/junctions. **Elimină din e-mail** sau Delete elimină numai selecția din mesaj, fără ștergerea originalului sau a referinței sale în task.

Lista arată numele, dimensiunea, starea și calea; selecția unui rând arată și calea completă dedesubt. Două nume identice din directoare diferite rămân două atașamente distincte. Deduplicarea folosește calea normalizată potrivit Windows, inclusiv separatorii, literele mari/mici și segmentele `..`.

Se verifică existența, tipul de fișier obișnuit și citirea efectivă la selectare, la validare și în worker înaintea predării către backend; backendul COM verifică din nou înainte de a construi mesajul. Fișierele dispărute/inaccesibile rămân vizibile pentru corectare. Toate sunt adăugate prin `MailItem.Attachments.Add` **înainte** de Display/Send. Refuzul unuia oprește operația; mesajul incomplet nu este trimis sau afișat. Nu există o limită de dimensiune pretins universală: Outlook poate refuza un document sau dimensiunea totală conform mediului/politicilor reale, iar eroarea concretă rămâne în formular.

## Predare, erori și jurnal

**Deschide ciorna în Outlook** deschide mesajul cu toate atașamentele pentru revizuire, fără Send. **Trimite** cere confirmare cu destinatari, CC, subiect, număr și dimensiune totală a atașamentelor. Enter într-un câmp nu trimite. Comenzile sunt dezactivate cât operația este în curs; clickul repetat nu creează cereri suplimentare.

Formularul rămâne deschis pe durata operației și la eroare păstrează destinatarii, subiectul, corpul și atașamentele. Pe ferestre mici conținutul se derulează; butoanele și explicația erorii au spațiu separat. Tab aduce în vedere controlul focalizat. Erorile lungi au derulare proprie.

Rezultatele sunt distincte:

- **Ciornă deschisă**: Display a reușit; mesajul nu a fost trimis de FocusDesk.
- **Mesaj predat Outlook pentru trimitere**: Send a revenit fără eroare. Nu confirmă livrarea către destinatar, sincronizarea Exchange sau ieșirea din De trimis.
- **Rezultat incert**: timeout, excepție din Display/Send sau rezultat necunoscut. Mesajul poate exista deja în Outlook. Verifică ferestrele deschise, Ciorne, De trimis și Elemente trimise. FocusDesk nu reia automat Send și ignoră rezultatul tardiv. Butonul **Am verificat în Outlook…** cere confirmare înainte de reactivarea unei noi încercări explicite.

Activitatea taskului înregistrează rezultatul cunoscut/incert, destinatarii, subiectul și numele atașamentelor, fără corpul integral sau copii ale documentelor. Read-only permite compunerea, fără scrierea jurnalului. Callbackul verifică identitatea workspace-ului capturat și disponibilitatea taskului; nu scrie în alt workspace. Un eșec al jurnalului după predarea reușită este raportat separat și nu provoacă o nouă trimitere.

Formularul este o ciornă în memorie, fără o a doua copie persistentă a descrierii. Închiderea voluntară a formularului sau a aplicației nu salvează o ciornă locală de e-mail. După crash/timeout COM nu poate garanta trimitere exact o dată: verificarea în Outlook este necesară înainte de o nouă încercare. Între ultima verificare a unui document și accesul Outlook acesta poate fi modificat de alt program; nu se promit copii înghețate ale conținutului fișierelor.

## Verificare efectivă și limite

Testele folosesc numai workspace-uri temporare, Tk/Xvfb și backenduri false. `tests/test_mail_workflow.py` acoperă descrieri de peste 600 și 100.000 de caractere, diacritice/indentare, buffer comun nesalvat, snapshot independent, atașamente multiple și nume identice, deduplicare Windows, eliminare fără ștergere, fișiere dispărute/inaccesibile, revalidare după confirmare, COM Attachments.Add refuzat fără trimitere parțială, aceleași documente în ciornă/trimitere, anulare/Enter, click repetat, timeout/rezultat necunoscut, jurnal eșuat, read-only, schimbare workspace și grab modal imbricat.

Rezultate executate pentru această etapă:

- Suita completă: **508 passed, 1 skipped**, în 85,25 s; omis este testul de junction Windows.
- Suita nouă de e-mail: **35 passed**, inclusiv testele Tk reale și metoda backendului real executată numai pe obiecte COM false.
- Capturi Tk reale la 100%/125%/150%: **24 verificări de geometrie** reușite, pentru formular, selectorul local, eroare și accesul prin derulare la minimum 680×540 logic.
- `compileall` și `pip check`: reușite; verificarea whitespace respectă terminatorii CRLF existenți ai repository-ului.

O rulare combinată a întâlnit un abort Python/Tk când GC a curățat variabile ale unor interpretere Tk deja închise pe un thread de I/O. Izolarea testelor colectează acum aceste cicluri pe threadul principal, între teste; rerularea completă de mai sus a trecut. Aplicația folosește în continuare un singur interpreter principal, iar această schimbare de izolare este numai în `tests/conftest.py`.

Reproducere pe Linux cu display Xvfb:

```sh
xvfb-run -a python -m pytest -q
xvfb-run -a python scripts/capture_mail.py --scale 1.25 --output artifacts/mail-125
```

Capturile sunt ferestre Tk reale pe date demonstrative: [100%](capturi-ui/email/100/email-atasamente.png), [125%](capturi-ui/email/125/email-atasamente.png), [150%](capturi-ui/email/150/email-atasamente.png), [eroare la minimum](capturi-ui/email/100/email-eroare-minim.png). Scările sunt simulări Tk în Linux, nu validare DPI pe Windows.

Nu s-au trimis e-mailuri reale, nu s-a executat Outlook Classic real și nu s-a construit un executabil Windows pentru această modificare. Nu sunt introduse dependențe noi, SQL/SQLite sau servicii cloud. Pillow este folosit numai de scriptul opțional de capturi.

### Verificare manuală necesară în Outlook Classic

1. Încearcă întâi **Deschide ciorna**, cu două fișiere temporare (inclusiv nume identice în directoare diferite). Verifică atașamentele efective, corpul complet și diacriticele în fereastra Outlook; închide fără trimitere.
2. Pe date de test, modifică descrierea fără salvare, încearcă fiecare alegere și verifică păstrarea metadatelor nesalvate. Editează mesajul și verifică faptul că taskul nu se schimbă.
3. Mută/șterge/blochează un document după selectare: predarea trebuie oprită fără pierderea formularului. Testează și un refuz real al politicii de atașamente/dimensiune, dacă mediul îl permite.
4. Numai la alegerea ta, trimite-ți un mesaj de test după verificarea confirmării și a atașamentelor. Verifică separat De trimis/Elemente trimise și primirea; apelul COM nu dovedește livrarea.
5. Dacă Outlook afișează avertismente de securitate sau un timeout, verifică mesajul în Outlook înainte de reîncercare; aplicația nu ocolește avertismentele. New Outlook nu suportă acest COM. Semnătura implicită poate lipsi în modul Send: ajusteaz-o în ciornă dacă este necesar.
