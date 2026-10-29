# Fișiere: exploratorul folderelor reale

Tabul **Fișiere** din inspector și din spațiul taskului afișează directoarele reale. Un document pus manual într-un subfolder al proiectului apare fără creare de Attachment, modificarea node.json sau restart. Deschiderea tabului și navigarea nu marchează taskul ca editat. Funcționează și pentru taskuri finalizate/arhivate și în workspace read-only.

## Sursele și asocierea

- **Folderul proiectului / de lucru** folosește `source_workspace` și rezolvarea existentă `effective_source()`: propriu, moștenit sau comun unei cerințe ulterioare. Calea rădăcinii și „Moștenit de la …” sunt afișate și la selectarea unui document. Pentru surse comune rămâne explicația „Folder de cod comun”.
- **Fișierele taskului / proiectului** reprezintă conținutul real din `files/` al nodului, inclusiv documentele copiate manual, fără înregistrare individuală.
- **Legături externe / alte referințe** păstrează referințele existente care nu sunt deja acoperite de rădăcinile de mai sus. Două referințe către aceeași locație nu devin două documente; o referință către un document deja vizibil pe disc oferă acțiunile de gestionare pe acel rând.

Dacă rădăcinile sunt identice, se afișează o singură sursă cu etichetă comună. Dacă una este în interiorul celeilalte, ambele roluri sunt păstrate și suprapunerea este explicată: conținut comun, fără copii suplimentare. Folderul de lucru nu este înlocuit automat cu directorul intern care conține node.json, istoric sau snapshoturi.

Fără asociere, **Alege folderul proiectului…** creează o asociere externă pe nodul selectat, fără copiere/mutare. Alegerea într-un task poate înlocui moștenirea numai pentru acel task; pentru asocierea la nivelul întregului proiect selectează proiectul. **Folosește files/** reutilizează folderul administrat existent drept folder de lucru. Folosește aceeași asociere ca versiunile/checkpointurile; nu există o a doua configurație divergentă a sursei.

**Elimină asocierea / oprește moștenirea…** elimină asocierea proprie sau dezactivează moștenirea numai pentru taskul curent, cu confirmare. Fișierele și asocierea proiectului nu se șterg. După eliminarea unei asocieri proprii, sursa unui strămoș poate redeveni efectivă.

## Explorare și actualizare

Arborele arată numele, tipul, dimensiunea fișierului și ultima modificare, în ora locală a sistemului. Dimensiunea folderelor rămâne „—”; nu se calculează recursiv. Sunt afișate toate elementele obișnuite, inclusiv fișierele ascunse și directoarele tehnice; nu există un filtru implicit care să ascundă permanent conținut.

Directoarele se citesc numai când sunt deschise. Fiecare listare citește metadatele unui singur director, fără conținutul documentelor. Rezultatul complet este sortat (foldere, apoi nume) înainte de afișarea primelor **200** de rânduri. Rândul **Încarcă următoarele 200** continuă afișarea fără o nouă scanare. Nu este un prag pentru numărul de fișiere permise.

- **Actualizează** sau **F5** cu focusul în explorator recitesc directoarele deschise, fără reloadul întregului workspace.
- Revenirea în tab/fereastra aplicației programează actualizarea cu debounce de 300 ms. Revenirea după suspendarea monitorizării o reactivează.
- Cât exploratorul este vizibil, pollingul verifică cel mult **4 directoare deschise la 2,5 secunde**, prin rotație, cu cel mult **2 cereri simultane per explorator**. Verifică și directoarele extinse din interior, fără să presupună că mtime al rădăcinii detectează schimbările lor.
- Monitorizarea este oprită la ascunderea tabului, schimbarea taskului/workspace-ului și închiderea aplicației. Rezultatele unei generații anterioare sunt ignorate. La schimbarea workspace-ului se eliberează și cache-urile de navigare și referința către vechiul Workspace.

Citirile folosesc workerii existenți. Niciun widget Tk nu este accesat din worker. Folderele de rețea și cele mari au stare de încărcare; nu blochează Tk în timpul listării. Un apel de sistem blocat în rețea nu poate fi întrerupt forțat: anularea împiedică aplicarea rezultatului și oprește lucrul cooperativ când apelul revine.

Refreshul reconciliază rândurile după calea stabilă, actualizând numai diferențele. Se păstrează selecția existentă, scrollul și folderele extinse; rândurile șterse sau redenumite sunt reconciliate. Contextul de navigare se păstrează în memorie pentru ultimele 10 taskuri vizitate. La un director temporar inaccesibil, rândul arată eroarea; listarea precedentă poate rămâne pentru păstrarea contextului și nu trebuie considerată actualizată până la reconectare. Celelalte surse continuă să funcționeze.

În spațiul taskului, exploratorul folosește direct înălțimea panoului. **Acțiuni → Mai mult spațiu pentru Fișiere** lărgește panoul; separatorul rămâne redimensionabil. În inspector există derulare verticală și orizontală, meniu contextual și toolbar compact.

## Deschidere și e-mail

Dublu-click sau Enter pe un folder îl extinde/restrânge; săgețile arborelui rămân disponibile. Dublu-click/Enter pe un document îl deschide în aplicația asociată. **Acțiuni**, click dreapta sau **Shift+F10** oferă:

- Deschide în Explorer;
- Deschide în VS Code;
- Copiază calea (inclusiv pentru selecție multiplă);
- Atașează la e-mail…;
- comenzile pentru asociere, referințe și copii administrate.

Scripturile și executabilele (.py, .bat, .ps1, .exe și celelalte extensii din politica existentă) nu sunt lansate cu aplicația asociată. Se cere alegerea editorului sau a afișării în Explorer; anularea nu execută nimic. Căile sunt reverificate la acțiune, în worker. Dacă fișierul dispare, este blocat sau o componentă a căii devine symlink/junction, acțiunea este refuzată contextual.

Pentru e-mail selectează unul sau mai multe **fișiere**, apoi **Atașează la e-mail…**. Formularul existent primește selecția, inclusiv fișiere descoperite pe disc fără Attachment. Nu se trimite automat și nu se creează copii în workspace. Directoarele nu sunt atașate sau arhivate automat. Verificările, deduplicarea, ciorna editabilă și confirmarea trimiterii rămân cele documentate în [EMAIL-DIN-TASK.md](EMAIL-DIN-TASK.md).

Symlinkurile/junctions sunt afișate cu starea „fără traversare automată”. Nu sunt extinse și nu permit ieșirea implicită din rădăcina aleasă. O legătură externă înregistrată este o sursă explicită; limitele acelei surse se verifică separat, inclusiv componentele rădăcinii. Un copil inaccesibil nu ascunde frații care pot fi listați. Listarea nu citește documente pentru preview; pentru deschidere/e-mail se verifică suplimentar citirea efectivă.

## Referință versus fișier fizic

**Adaugă…** păstrează alegerea dintre copie administrată și legătură externă. **Relocalizează legătura…** modifică numai calea referinței externe.

**Elimină doar legătura/referința…** nu șterge documentul. Un document rămas în folder continuă să apară, deoarece exploratorul citește discul. O referință către un fișier dispărut poate rămâne marcată ca lipsă în directorul listat. Pentru orice referință veche, inclusiv când întregul său subfolder nu mai există, folosește **Acțiuni → Legături și referințe existente…**.

Ștergerea fizică existentă rămâne o comandă separată: **Șterge copia administrată și referința…**, disponibilă numai pentru o copie administrată înregistrată și cu confirmare. Nu există o nouă ștergere generală a documentelor descoperite, mutare în masă sau redenumire. În read-only, navigarea/deschiderea/copierea căii/e-mailul rămân disponibile, iar mutațiile locale sunt dezactivate.

## Backup și versiuni

Regulile existente nu se schimbă: backupul complet include fișierele administrate din workspace, inclusiv cele adăugate manual în files/. Asocierea externă nu copiază automat folderul utilizatorului în backup. Restaurarea păstrează asocierea; disponibilitatea unei căi externe depinde în continuare de calculator/disc/rețea.

Checkpointurile continuă să folosească `effective_source()` și excluderile/limitele lor existente. Faptul că un fișier este afișat în explorator nu înseamnă că intră automat în checkpoint. O cerință ulterioară cu folder comun își păstrează regulile existente pentru proprietarul versiunilor; nu amestecă automat istoricul taskurilor.

## Verificări și limite

`tests/test_file_explorer.py` folosește numai directoare temporare și backenduri false pentru aplicații/e-mail. Acoperă modificări externe, subfoldere lazy, redenumire/ștergere, refresh fără pierderea contextului, nume identice, paginare după sortare, surse moștenite/suprapuse, referințe vechi, symlinkuri, erori pe copil/director, schimbare task și workspace cu scanare în curs, revenire/focus/F5, polling limitat, redeschidere după navigare, read-only/finalizate/arhivate, backup/restore și document descoperit preselectat în formularul de e-mail. Politica pentru .py/.bat/.ps1/.exe este verificată cu lansatoare false; nu sunt executate scripturi și nu sunt trimise mesaje.

Rezultate executate pentru această etapă:

- **537 teste reușite, 1 omis**, în 114,89 s în rularea completă finală. Omis este testul specific de junction Windows.
- **29 teste noi** pentru explorator, plus testele existente de fișiere, checkpointuri, backup, navigare, e-mail și cerințe ulterioare.
- **12 verificări de geometrie** și 6 capturi reale Tk la 100%/125%/150%, la dimensiunea minimă; pragurile de înălțime ale arborelui și accesul la Actualizează sunt verificate.
- `compileall`, `pip check` și verificarea whitespace compatibilă cu CRLF: reușite.
- Testele de listare verifică explicit zero citiri de conținut și lipsa scanării subfolderelor închise; pollingul este verificat la cel mult 4 directoare pe ciclu. Nu sunt benchmarkuri de latență Windows.

Reproducere în Linux cu Xvfb:

```sh
xvfb-run -a python -m pytest -q
xvfb-run -a python scripts/capture_files.py --scale 1.25 --output artifacts/files-125
```

Capturi Tk reale pe date demonstrative, la minimum 1100×700 logic: [inspector 100%](capturi-ui/fisiere/100/fisiere-inspector.png), [spațiu task 125%](capturi-ui/fisiere/125/fisiere-spatiu-lucru.png), [spațiu task 150%](capturi-ui/fisiere/150/fisiere-spatiu-lucru.png). Manifestele înregistrează geometria și faptul că aplicațiile externe nu au fost lansate. Scalarea Tk în Linux nu reprezintă validare DPI nativă Windows.

Nu sunt introduse SQL/SQLite, asocieri persistente paralele, watchers sau dependențe noi. Sortarea necesită metadatele întregului director deschis; subdirectoarele închise și documentele nu sunt încărcate. Pollingul are un cost proporțional cu conținutul directoarelor deschise verificate, nu cu întregul proiect. Nu se promite detectare instantanee sau o măsurătoare Windows de performanță. Limita de cale Windows existentă și verificările pentru reparse points rămân aplicate.

Verificare manuală necesară pe Windows: copiază un document într-un subfolder deschis din Windows Explorer, revino în FocusDesk, verifică apariția și deschiderea în aplicația asociată; repetă pentru o cale de rețea deconectată/reconectată și pentru un junction real. Testele automate folosesc lansatoare false; nu confirmă integrarea nativă Explorer/VS Code, Windows DPI sau un build executabil.
