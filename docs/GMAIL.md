# Gmail prin parolă de aplicație

FocusDesk poate trimite mesaje prin Gmail/Google Workspace, folosind SMTP și o parolă de aplicație Google. **Outlook Classic rămâne implicit** și folosește în continuare ComWorker, inclusiv deschiderea ciornelor. Ambele transporturi folosesc același formular, MailDraft, validarea adreselor și selecția atașamentelor. Nu există citire de inbox, import de mesaje, Google Calendar sau OAuth.

## Configurare și utilizare

1. Deschide **Setări → Integrări → E-mail**, inclusiv fără workspace sau într-un workspace read-only. Alege furnizorul implicit și adresa contului Gmail/Google Workspace; sunt acceptate domenii proprii, nu numai `@gmail.com`. Numele afișat este opțional.
2. Activează verificarea în doi pași în contul Google. **Cum obțin parola de aplicație?** deschide pagina oficială [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) în browser. Generează manual parola; FocusDesk nu automatizează site-ul și nu solicită coduri de verificare. Folosește **parola de aplicație**, nu parola obișnuită. Politicile organizației, Advanced Protection sau alte restricții pot face opțiunea indisponibilă; schimbarea parolei Google poate revoca parolele de aplicație.
3. Introdu parola în câmpul mascat. Sunt eliminate numai spațiile ASCII de prezentare, fără o regulă de tip „exact 16 litere” care ar înlocui autentificarea reală. Caracterele de control sunt refuzate.
4. **Memorează securizat pe acest calculator** folosește Windows Credential Manager. Dacă stocarea nu este disponibilă, parola rămâne numai în memoria procesului și trebuie reintrodusă după restart. **Salvează configurarea e-mail** salvează profilul calculatorului, fără să salveze alte modificări ale taskului sau workspace-ului.
5. **Testează conexiunea** negociază TLS și autentificarea, apoi închide conexiunea. Nu trimite un mesaj și nu salvează automat câmpurile. Reușita nu garantează acceptarea unui mesaj, livrarea sau citirea.
6. În formularul obișnuit de e-mail alege **Trimite prin → Gmail — adresa contului**. **Configurează Gmail…** permite completarea configurării fără închiderea ciornei. Schimbarea furnizorului păstrează Către, CC, subiectul, corpul editat și atașamentele. Confirmarea afișează contul și destinatarii. Calendarul Outlook rămâne separat.

Gmail nu necesită Outlook instalat. Numai trimiterea Gmail, testul conexiunii și deschiderea voluntară a paginii Google necesită rețea; navigarea, taskurile, notițele, calendarul local și compunerea rămân offline. Formularul nu permite un From arbitrar sau aliasuri neverificate.

## Rezultate, ciorne și atașamente

- **Mesaj acceptat de serverul Gmail pentru trimitere** înseamnă acceptarea SMTP, fără dovadă de livrare/citire. Un eșec al QUIT după răspunsul pozitiv de acceptare nu transformă rezultatul în eșec și nu provoacă retrimitere.
- La **acceptare parțială** sunt afișați destinatarii acceptați/refuzați și codurile SMTP. Formularul rămâne deschis și trimiterea este blocată. **Pregătește numai destinatarii refuzați…** cere confirmare, elimină adresele deja acceptate și păstrează rolurile Către/CC. Poate rămâne numai CC; noua trimitere cere încă o confirmare. Pregătirea singură nu trimite nimic.
- La **rezultat incert** după pierderea răspunsului în timpul predării, verifică Gmail și destinatarii înainte de **Am verificat în Gmail…**. Schimbarea furnizorului nu elimină blocarea. Nu există retry sau fallback automat către Outlook. SMTP nu oferă o garanție globală de „exact o dată” după un crash sau o întrerupere ambiguă.
- Refuzul total, autentificarea refuzată, DNS/conexiunea, timeoutul înainte de predare, TLS și limitele furnizorului au explicații distincte. Codul SMTP și tiparele cunoscute de cotă/rate limit sunt clasificate fără afișarea conversației SMTP. Un cod de autentificare nu dovedește întotdeauna dacă parola este greșită, revocată sau blocată de politică; explicația păstrează această limită.
- **Deschide ciorna în Outlook** există numai pentru Outlook. SMTP nu creează ciorne în Gmail web. **Salvează ca .eml (local)…** include corpul integral și atașamentele într-un fișier local, fără trimitere/sincronizare și fără parolă. Exportul nu deblochează o trimitere incertă.

Atașamentele sunt selectate prin mecanismul existent. Toate sunt revalidate și citite înainte de deschiderea conexiunii SMTP. Un document lipsă/inaccesibil blochează mesajul incomplet. MIME folosește From din contul configurat, To, CC, subiect/corp Unicode, Date, Message-ID și nume internaționale de fișiere. Conținutul nu este trunchiat. Limitele reale de mesaj/atașamente sunt cele impuse de cont și Google; nu se inventează o limită universală în UI.

## Secret, profil și jurnal

Metadatele sunt în `%APPDATA%/FocusDesk/app.json`, sub `mail`: furnizor, UUID de profil, adresă, nume și indicatori de stocare. Parola nu este un câmp al modelului și nu este serializată. Secretul memorat folosește `CredWriteW`/`CredReadW`/`CredDeleteW`, tip `CRED_TYPE_GENERIC`, ținta `FocusDesk/Gmail/<UUID>`, persistență pentru același utilizator pe acest calculator și blob UTF-16LE. Nu există fișier de parole, cheie fixă inclusă în aplicație, keyring cu backend SQL sau fallback la text simplu.

Scrierea profilului este atomică. Dacă eșuează după modificarea Credential Manager, serviciul încearcă restabilirea secretului anterior și păstrează configurarea activă; dacă restabilirea eșuează, eroarea cere reconciliere explicită. Dacă o credențială veche nu poate fi eliminată fiindcă backendul este indisponibil, noua parolă poate rămâne în memorie, dar profilul păstrează referința pentru ștergere ulterioară și UI explică situația. Nu se pretinde că vechiul secret a fost șters.

**Elimină datele de conectare** șterge secretul local, memoria sesiunii și metadatele, revenind la furnizorul implicit Outlook. Dacă ștergerea securizată eșuează, apare o eroare și se păstrează referința necesară pentru retry. Revocarea la Google se face separat din contul Google. Datele taskurilor nu sunt afectate.

Jurnalul taskului păstrează rezultatul, furnizorul/contul, destinatarii, subiectul, momentul UTC, Message-ID și numele documentelor. Nu păstrează secretul, dialogul SMTP sau corpul integral. Read-only nu scrie jurnal; callbackul verifică identitatea workspace-ului și disponibilitatea taskului. Un eșec al jurnalului după acceptarea SMTP nu repetă transportul. Backupurile workspace-ului nu includ profilul sau Credential Manager.

## Implementare și distribuție

- `domain/mail.py`: metadate de profil, cu provider implicit `outlook` și fără câmp de parolă.
- `services/mail.py`: compunere, MailDraft și validare comune. Outlook își păstrează infrastructura și rezultatele existente.
- `integrations/gmail.py`: MIME și SMTP; implicit `smtp.gmail.com:465` cu TLS, timeout de 25 s pe operațiile socket. Clasa permite și 587 cu EHLO → STARTTLS verificat → EHLO → autentificare. Alte porturi sunt refuzate. Nu este promis un deadline global pentru DNS sau pentru întregul mesaj.
- `integrations/credentials.py`: API nativ Windows încărcat la cerere, prin `ctypes`.
- `services/gmail.py`: ciclul profil/secret, rezultate și lucrări trimise prin UiBridge. Workerul nu accesează widgeturi Tk. Erorile SMTP sunt sanitizate înainte de traversarea limitei worker/log; nu se activează debug SMTP.
- `ui/gmail_ui.py`: aceeași componentă în Setări și în dialogul imbricat al compunerii. Câmpurile au scroll și focus vizibil; acțiunile principale rămân accesibile.

Se folosesc numai bibliotecile standard `smtplib`, `ssl`, `email`, `ctypes` și infrastructura deja inclusă. Nu au fost adăugate dependențe runtime sau SQL/SQLite. Importurile statice intră în analiza PyInstaller. Verificarea distribuției (`--smoke-test` și `scripts/verify_distribution.py`) cere încărcarea modulelor Gmail/TLS și a simbolurilor Credential Manager în executabil; SMTP rămâne fals și nu citește/scrie credențiale reale. Această probă nu înlocuiește testul real al stocării Windows.

Cele cinci cataloage și ghidurile ro/en/de/fr/es includ configurarea, trimiterea, limitele și depanarea; ancorele `gmail-configurare`/`gmail-trimitere` sunt comune și F1 folosește ID-uri stabile. Datele și mesajele personale nu se traduc sau regenerează.

## Documentație oficială consultată

Au fost citite sursele oficiale CPython pentru [smtplib](https://github.com/python/cpython/blob/3.14/Doc/library/smtplib.rst), [ssl](https://github.com/python/cpython/blob/3.14/Doc/library/ssl.rst) și [email](https://github.com/python/cpython/blob/3.14/Doc/library/email.examples.rst), precum și sursele Microsoft pentru [CredWriteW](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/wincred/nf-wincred-credwritew.md) și [CREDENTIALW](https://github.com/MicrosoftDocs/sdk-api/blob/docs/sdk-api-src/content/wincred/ns-wincred-credentialw.md). Verificarea acoperă validarea certificatelor, STARTTLS înainte de autentificare, semantica destinatarilor refuzați, persistența și limita blobului nativ.

Paginile HTML ale Google, inclusiv [parolele de aplicație](https://support.google.com/accounts/answer/185833?hl=en) și [SMTP pentru Google Workspace](https://support.google.com/a/answer/176600?hl=en), au fost refuzate de proxy-ul mediului cu HTTP 403. Politicile/limitele actuale ale unui cont Google trebuie reconfirmate la verificarea manuală; nu sunt prezentate drept verificate live în această execuție. Paginile Python/Microsoft au fost consultate prin repository-urile oficiale, după același refuz pe domeniile HTML.

## Test manual necesar, separat de backendurile false

Pe un Windows 10/11 cu executabilul construit din branchul de integrare și un cont **Gmail/Google Workspace de test**:

1. Rulează verificarea distribuției cu PATH curat. Confirmă simbolurile Credential Manager și modulele TLS; nu folosi date personale în smoke.
2. Generează o parolă de aplicație în browser. Configurează contul, testează conexiunea și confirmă că testul nu trimite un mesaj. Închide/repornește aplicația și verifică păstrarea securizată a parolei în Credential Manager.
3. Trimite explicit către adrese de test controlate un corp lung cu diacritice, CC și mai multe documente cu nume internaționale. Verifică MIME/documentele, Gmail Sent și primirea separată; mesajul UI singur nu confirmă livrarea.
4. Verifică Outlook Classic rămas implicit pe un profil nou, schimbarea furnizorului fără pierderea ciornei, ciorna Outlook și exportul local .eml. Verifică faptul că Gmail funcționează și fără Outlook instalat.
5. Simulează lipsa rețelei sau o parolă revocată pe contul de test. Confirmă păstrarea formularului și absența retry/fallbackului automat. Nu provoca duplicate pentru a testa o întrerupere ambiguă; scenariul este automatizat cu backend fals.
6. Elimină credențialele local, verifică dispariția țintei proprii din Credential Manager, apoi revocă separat parola la Google. Verifică și modul numai pentru sesiune când memorarea securizată nu este disponibilă.

Nu s-au folosit credențiale reale și nu s-au trimis mesaje reale în testele automate. Rezultatele executate sunt în [VERIFICARE-GMAIL.md](VERIFICARE-GMAIL.md).
