# Întâlniri și notițe locale

În **Calendar** există două taburi: **Agenda**, pentru funcțiile existente, și
**Întâlniri**, pentru contextul discuțiilor, notițe și acțiuni rezultate. Cele patru
destinații principale rămân Astăzi, Proiecte și taskuri, Calendar și Activitate.
Întâlnirile nu sunt taskuri și nu sunt sesiuni de lucru. Nu pornesc timerul,
nu creează rezervări și nu intră în totalurile Lucrat/Programat din dashboard.
Nu se presupune prezența utilizatorului pe baza intervalului calendaristic.

## Import explicit, doar pentru citire

1. Deschide Calendar → Întâlniri → **Alege calendarul…**.
2. Alege explicit un calendar dintre cele returnate de Outlook Classic. Alegerea
   este separată de calendarul în care FocusDesk salvează propriile rezervări.
3. **Actualizează întâlnirile** arată o previzualizare cu sursa și perioada înainte
   de citire. Implicit: ultimele 14 zile, ziua curentă și următoarele 60 de zile.
4. Pentru trecut mai îndepărtat, completează De la/Până la și folosește explicit
   **Încarcă interval din Outlook…**. O cerere acoperă cel mult un an.

Sunt vizibile ultima actualizare, rezultatul parțial, avertismentele și ultima
încercare eșuată. Nu există actualizare periodică și refreshul listei nu recitește
Outlook. Sunt refuzate cererile duplicate cât timp una este în curs. Citirea este
limitată la 3000 de elemente per comandă; atingerea limitei marchează rezultatul
ca parțial. Importul folosește `ComWorker` existent, fără COM în firul Tk.
Aplicarea JSON-urilor locale este progresivă, în loturi de cel mult opt elemente
care necesită prelucrare, cu revenire în bucla Tk între loturi. Un workspace nou
sau o altă sursă nu primește rezultatele întârziate ale unei cereri vechi.

Se citesc titlul, începutul/sfârșitul UTC, fusul sursei când este disponibil,
locația, organizatorul, identificatorii și starea, plus linkul de participare
HTTP/HTTPS dacă există în proprietatea calendaristică dedicată. Nu se citesc
Body/HTMLBody, atașamentele sau colecția completă de participanți. Evenimentele
personale și cele marcate Free rămân eligibile pentru import.

Nu se apelează Save/Send/Delete pe programări, nu se trimit invitații, nu se
acceptă/refuză întâlniri, iar notițele nu se scriu înapoi în Outlook. Importurile
nu intră în exportul ICS al rezervărilor. Evenimentele cu markerul existent
`FocusDeskSessionId` sunt excluse, indiferent de titlu; un titlu asemănător fără
marker nu este folosit ca motiv de excludere sau drept cheie de identitate.

Dacă Outlook Classic/COM lipsește, datele locale și notițele rămân disponibile.
**Întâlnire manuală…** funcționează offline. New Outlook nu oferă această integrare
COM. Nu s-a introdus import ICS pentru întâlniri în această etapă.

## Identitate, recurențe și absențe

ID-ul local este un UUID separat de identificatorii Outlook. Cheia de import
conține providerul, store-ul, calendarul, identificatorul evenimentului/seriei și
slotul original pentru o apariție recurentă; nu conține titlul. UUID-ul determinist
al importului permite reluarea după o întrerupere fără duplicate.

Cititorul COM sortează după Start, activează IncludeRecurrences și folosește
Restrict pe interval. Nu revine la parcurgerea întregului calendar dacă Restrict
eșuează. Preferă `PidLidCleanGlobalObjectId`; fallbackul GlobalAppointmentID
normalizează octeții datei apariției din GlobalObjectId. Pentru un eveniment
nerecurent fără Global ID se folosește EntryID; mutarea acelui element între
calendare/store-uri poate necesita verificare manuală a identității.

Pentru apariții normale se păstrează slotul StartUTC; pentru o excepție mutată,
`PidLidExceptionReplaceTime` păstrează slotul UTC original. Dacă Outlook nu expune
identitatea necesară unei excepții, elementul este omis cu avertisment și rezultatul
este parțial, în loc să fie ghicită o identitate nouă. Schimbarea orei/titlului
actualizează metadatele aceleiași întâlniri, fără a modifica notițele.

StartUTC/EndUTC păstrează intervalele reale la DST. Evenimentele all-day păstrează
și datele calendaristice originale, cu sfârșit exclusiv, pentru a nu le muta în
altă zi doar prin conversia fusului workspace-ului. Nu se presupune că o zi
calendaristică are întotdeauna 24 de ore.

O anulare returnată explicit de Outlook este afișată **Anulată**. Absența dintr-o
interogare reușită și completă marchează doar **Sursă neconfirmată**, pentru
intervalul și calendarul verificate. Poate însemna ștergere, mutare în afara
intervalului sau o excepție eliminată care nu mai este returnată de Outlook.
Nu se deduce automat o ștergere/anulare din această absență. O interogare parțială
sau eșuată nu produce nici acest marcaj. Nu se șterg automat întâlniri, notițe,
acțiuni sau legături, inclusiv când ies din perioada curentă de import.

## Listă, editor și salvare

Filtre: Următoare, Trecute, Cu notițe, Cu acțiuni neconvertite, Toate; căutare după
titlu și interval. Filtrarea și sortarea întregului index preced paginarea. Lista
pornește cu 100 de rânduri; **Mai multe** extinde progresiv rezultatul. În listă
apar data/ora, starea calendaristică, Are notițe și numărul acțiunilor neconvertite.
Dublu-click, Enter sau **Deschide notițele** deschid spațiul întâlnirii.

Stările Urmează/În desfășurare/Încheiată sunt deduse din interval; În desfășurare
nu confirmă participarea și nu reprezintă un timer. Anularea și sursa neconfirmată
au etichete distincte.

Editorul este text liber, cu Undo/Redo și separator redimensionabil față de
**Acțiuni rezultate**. Șablonul opțional adaugă Subiecte discutate, Decizii,
De clarificat, fără a înlocui textul existent. Nu sunt necesare toate secțiunile.
**Înapoi** păstrează filtrul, selecția, pagina încărcată și poziția listei.

Modificările se salvează atomic în `notes.md`, după 900 ms fără editare.
Indicatorul arată Se salvează… / Salvat / Salvarea a eșuat. Ctrl+S salvează imediat
numai notițele întâlnirii vizibile. La eroare, textul și dirty state rămân în editor;
există **Reîncearcă salvarea**. Navigarea și închiderea încearcă salvarea și permit
reîncercare, păstrarea ciornei sau renunțare explicită. Backupul din UI rezolvă
mai întâi ciorna notițelor.

Modificările externe sunt protejate prin hash-ul textului încărcat. Refreshul sau
actualizarea sursei nu înlocuiesc bufferul. **Reîncarcă notițele…** cere o alegere
explicită dacă există o ciornă. Read-only permite citirea, fără autosalvare,
import, conversie sau modificare de acțiuni.

## Acțiuni, taskuri și proiecte

**Acțiuni → Adaugă acțiune…** păstrează text, responsabil și termen opționale,
precum și De clarificat/De făcut/Închisă. Atribuirea unei acțiuni altcuiva nu creează
un task personal. Nu se extrag automat acțiuni din text.

Pentru creare explicită:

- selectează un fragment din notițe și apasă **Creează task din selecție…**;
- sau alege o acțiune și folosește **Creează task… / Creează proiect…**;
- sau folosește **Cerință nouă pentru un task existent…**, care reutilizează
  FollowupService, relația tipizată și opțiunea explicită de folder de cod comun;
- pentru date deja existente, **Leagă task/proiect existent…** nu creează un nod.

Formularul precompletat rămâne editabil: titlu, descriere, container/proiect,
prioritate, termen și contextul întâlnirii. Se copiază doar fragmentul ales/textul
acțiunii, nu toate notițele. Originalul rămâne în notițe. Pentru o cerință nouă,
alegerea taskului sursă preselectează containerul acestuia dacă este disponibil;
un container arhivat necesită alegere explicită a unei destinații active.

Nodul nou are ID, timp și status propriu. Legătura tipizată `Node.meeting_ids`
permite deschiderea întâlnirii din inspector/spațiul taskului și din proiect.
Acțiunea convertită păstrează textul și arată Deschide taskul/proiectul.
Referințele indisponibile/coș sunt etichetate și rămân păstrate pentru restaurare.
Nici crearea unui task, nici deschiderea unei întâlniri nu pornesc lucrul.

Operațiile `meeting_convert` și `meeting_link` sunt jurnalizate, idempotente și
recuperate la deschiderea workspace-ului. Crearea unui nod normal reutilizează
motorul recuperabil existent prin `meeting_node_seed`; o cerință nouă folosește
operația FollowupService existentă. ID-urile sunt stabile la retry, iar o acțiune
cu o creare în curs este rezervată și la redeschiderea formularului cu alt UUID.
Schimbarea datelor unei operații deja începute este refuzată, fără duplicare.
Ciorna dialogului rămâne la eroare. Chitanța finală este compactă; planul complet
există doar cât recuperarea are nevoie de el.

## Fișiere, index și integritate

```text
_system/meeting-source.json                 # alegere sursă, perioadă, actualizare/erori
_system/meetings/<uuid>/source.json          # metadate calendar/manuale, autoritare
_system/meetings/<uuid>/local.json           # acțiuni și legături locale
_system/meetings/<uuid>/notes.md             # textul utilizatorului
_system/meetings/.cache/index.json           # metadate minimale, reconstructibil, v2
```

Actualizarea sursei scrie numai `source.json`. Nu rescrie `notes.md` sau acțiunile.
Indexul conține date, titlu, stare, existența notițelor, numărul acțiunilor
neconvertite și referințele, fără textul notițelor. La pornire se verifică semnăturile
fișierelor; un index valid evită încărcarea JSON-urilor individuale. Un index lipsă,
corupt sau incomplet se reconstruiește din JSON-uri și dimensiunea/stat-ul
Markdown-urilor, fără citirea conținutului lor. Cache-ul este salvat grupat; datele
autoritare sunt salvate imediat și atomic. Nu există SQL/SQLite sau servicii cloud.

Conținutul notițelor se citește la deschidere. Căutarea obișnuită nu parcurge
Markdown-urile. **Verifică integritatea locală…** este o comandă explicită care
verifică inclusiv textul și referințele; poate parcurge întregul istoric local.
Această citire nu schimbă baseline-ul de conflict al unui editor deschis.
Erorile de metadate apar și în verificarea workspace-ului/F5. Backupul de metadate
și cel complet includ întâlnirile, notițele, acțiunile și operațiile; restaurarea
reconstruiește indexul când semnăturile diferă. Ștergerea cache-ului nu pierde date.

## Verificat automat și de verificat pe Outlook real

Cu backend fals și workspace-uri temporare s-au verificat: import repetat,
modificarea orei/titlului, apariții și excepții mutate, anulări explicite,
rezultate parțiale/eșuate, excluderea markerilor FocusDesk, all-day/DST, folosirea
COM workerului în afara Tk și aplicarea pe Tk, oprirea aplicării progresive la
schimbarea workspace-ului, note offline și conflicte externe, read-only,
autosalvare/Ctrl+S/reîncercare, conversii task/proiect/cerință nouă, întreruperi la
etapele operației, rezervarea acțiunii contra duplicării, coș/restaurare,
backup/restore, integritate și un istoric de 180 de întâlniri fără citirea tuturor
notițelor la listare. Un index valid a fost verificat să citească doar indexul,
fără `source.json`, `local.json` sau `notes.md` individuale.

Capturi reale pe date demonstrative Linux/Xvfb:
[lista întâlnirilor](capturi-ui/intalniri-lista.png) și
[spațiul de notițe și acțiuni](capturi-ui/intalnire-notite.png).

**Nu s-a validat Outlook Classic real sau executabilul Windows.** Pe calculatorul
țintă trebuie verificate drepturile calendarului, formatele regionale ale Restrict,
StartUTC/EndUTC la DST, disponibilitatea CleanGlobalObjectId/ExceptionReplaceTime,
excepțiile mutate și eliminate, anularea unei apariții, all-day, calendarele/store-urile
folosite și disponibilitatea linkului de participare. Testele false nu garantează
expunerea tuturor proprietăților MAPI de fiecare versiune/profil Outlook.

Validarea finală integrată: **473 passed, 1 skipped**, inclusiv 41 teste dedicate întâlnirilor și scenariul cap-coadă. [Raport și benchmark](VERIFICARE-INTEGRATA.md).
