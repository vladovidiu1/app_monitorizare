# Rezervări, sesiuni de lucru și timer

O **rezervare** este un interval programat în calendar. O **sesiune de lucru**
începe prin acțiunea explicită a utilizatorului. **Timerul** este cronometrul unic
al sesiunii curente, inclusiv când este în pauză. Ora unei rezervări nu pornește
lucrul automat. O suprapunere în calendar poate fi un conflict de planificare,
nu dovada a două timere care rulează.

## Ce a arătat verificarea codului

Versiunea anterioară refuza deja al doilea timer. Nu am reprodus două cronometre
simultane în aceeași aplicație. Fără workspace-ul și momentul incidentului nu
putem identifica exact înregistrările observate de utilizator.

Au fost însă confirmate prin cod și teste următoarele probleme:

- Astăzi afișa **statusul taskului** în lista sesiunilor, nu starea rezervării sau
  a lucrului; „Activă” nu diferenția pauza și înregistrările fără timer.
- Pornirea salva sesiunea înaintea fișierului timerului. Un eșec între scrieri
  putea lăsa o înregistrare active fără timer recuperabil.
- Încheierea salva timpul înaintea metadatelor taskului, rezumatului și istoricului.
  Eșecul ulterior putea lăsa timerul prezent pentru o sesiune deja done; retry-ul
  putea produce înregistrări auxiliare repetate.
- Anularea încheierii relua inclusiv o sesiune care era deja în pauză.
- Intervalul tehnic al unui timer pornit direct intra în durata Programat,
  deși nu fusese creată o rezervare.

Aceste fluxuri sunt corectate. Nu au fost rescrise date istorice reale pentru
remediere sau teste.

## Comenzi și stări

Stările vizibile sunt **Programată**, **În lucru**, **În pauză**, **Încheiată**,
**Anulată**, **Ratată**. În fișiere, statusurile rămân compatibile: planned,
active, done, cancelled, missed; pauza este starea timerului unic, nu o a doua
sesiune. O înregistrare active care nu corespunde timerului curent este afișată
**De verificat (fără timer curent)**. Recuperarea este etichetată separat.

Indicatorul de jos rămâne vizibil în cele patru pagini și în Concentrare. Arată
starea, durata, titlul prescurtat și ora începerii; tooltipul include contextul
complet. Oferă Pauză/Continuă, Încheie și Deschide taskul. Fără sesiune apare
„Nicio sesiune de lucru pornită”. **Avertizare…** configurează numărul de minute
pentru avertizarea discretă de sesiune lungă; 0 dezactivează. Nu există oprire
automată. Configurația este locală, `long_session_minutes`, implicit 240.

Începerea altui task cere explicit:

1. Continuă sesiunea existentă;
2. Încheie sesiunea și începe taskul ales;
3. Anulează.

Încheierea folosește dialogul existent pentru rezumat, următorul pas, timp rămas
și status. Anularea păstrează starea anterioară de pauză/rulare. Dacă salvarea
eșuează, taskul nou nu începe. Încheierea deja începută se reia cu planul salvat,
fără un alt rezumat sau eveniment duplicat. Startul repetat pentru aceeași sesiune
este idempotent; operațiile modale sunt protejate împotriva evenimentelor repetate.
Selectarea și deschiderea taskului nu pornesc timerul.

Din Astăzi și Calendar se poate începe rezervarea selectată: se reutilizează ID-ul
rezervării, iar datele efective sunt distincte de intervalul programat.
Calendar și Planificare au meniul **Sesiune ▾** pentru pornire, recuperare și corecție.
Lista Astăzi distinge **Rezervări și lucru azi** și permite pornirea numai a unei
rezervări încă programate.

## Restart, repaus și schimbarea workspace-ului

Recuperarea arată taskul, ultima stare, momentul ultimei salvări și timpul cunoscut.
Timpul cât aplicația a fost închisă nu este însumat ca muncă. Opțiunile sunt:

- **Continuă**: păstrează timpul salvat și reia de acum, fără intervalul offline;
- **Încheie la o oră aleasă…**: dată/oră ISO în fusul workspace-ului, cu offset
  explicit pentru ora repetată la DST; ora trebuie să fie între început și acum.
  Timpul păstrat este limitat la intervalul efectiv ales, fără completare automată
  a intervalului offline;
- **Renunță la intervalul nesalvat**: încheie la ultimul heartbeat păstrând munca
  cunoscută în acel interval; nu tratează timpul offline drept muncă.

Anularea dialogului lasă sesiunea de recuperat, vizibilă în indicator. O încheiere
întreruptă oferă reluarea salvării existente. Detectarea suspendării/repausului
păstrează pragul existent de 20 secunde între tickuri și oprește acumularea până
la reconcilierea explicită. Schimbarea zilei nu creează automat altă sesiune.

La schimbarea workspace-ului sau ieșire, sesiunea se încheie explicit, se salvează
**în pauză pentru recuperare** sau se anulează schimbarea. Nu rămâne un timer care
rulează ascuns în workspace-ul anterior. A doua instanță respectă lockul;
în read-only poate vizualiza starea salvată și poate închide workspace-ul fără
să modifice timerul, sesiunile sau recuperarea.

## Diagnostic și corectarea timpului

La deschidere, diagnosticul citește metadatele indexate și semnalează înregistrări
active fără timer și intervale de muncă încheiată suprapuse. Nu modifică automat
aceste înregistrări. Din Planificare/Calendar, **Recuperează sesiunea…** preia
explicit o înregistrare active fără timer, numai după rezolvarea timerului curent;
nu adaugă timpul scurs de la începutul său.

**Corectează timpul…**, în Planificare, Calendar și tabelul Activitate, modifică
numai sesiuni încheiate. Permite durata în secunde, capetele intervalului efectiv
și motiv opțional. Sunt validate durata nenegativă, ordinea, fusul, sfârșitul în
trecut/prezent și durata care nu poate depăși intervalul specificat. Dacă lipsesc
ambele capete în date vechi, se poate corecta doar durata. Rezervarea nu se schimbă.

Corecția și auditul ei se salvează **atomic în același SessionRecord**, în lista
opțională `corrections`: ID, moment, înainte/după pentru durată și interval, motiv.
Jurnalul taskului afișează aceste corecții. Un eșec nu publică în cache noua durată;
indexurile, rapoartele, calendarul lunar și exportul folosesc valorile salvate.
Nu se corectează o sesiune a cărei încheiere este încă în curs de recuperare.

## Persistență și rapoarte

`_system/timer.json` este și plan local recuperabil: la start precedă sesiunea,
conține temporar `session_draft`/`session_before`; la stop păstrează `finalization`
cu valorile și momentul înghețate. După confirmarea startului copia temporară se
elimină; după încheiere se elimină fișierul timerului. ID-urile rezumatului și ale
evenimentului de încheiere derivă din UUID-ul sesiunii. Retry-ul este determinist.
Conflictele externe și erorile de ștergere a timerului nu sunt ascunse ca succes.
Fișierul corupt sau o modificare externă incompatibilă nu este suprascrisă automat;
poate necesita verificarea fișierelor/backupului înaintea continuării.

Indexul reconstructibil al sesiunilor are versiunea 3 și include `origin` pentru
separarea timerelor directe de rezervări, fără citirea tuturor payloadurilor.
Datele autoritare rămân JSON local. Nu există dependențe noi.

Lucrat este `actual_seconds`, o singură dată pe sesiune. Live nesalvat este doar
surplusul timerului față de timpul deja salvat pentru **același ID**. Programat
exclude cancelled/missed și `origin=timer`; o rezervare începută păstrează durata
rezervată distinct de lucrat. Ziua muncii rămâne `started_actual_at`, cu fallback
`start_at`, în fusul workspace-ului; o sesiune peste miezul nopții este atribuită
zilei începerii, fără împărțire implicită.

## Verificări și limite

Teste pe workspace-uri temporare: start repetat, pauză, schimbare de task,
anularea încheierii, eșecuri la fiecare etapă a salvării, retry/restart, rezervări,
repaus și schimbarea zilei, lock/read-only, schimbare workspace, auditul corecțiilor,
DST/miezul nopții, conflicte externe și egalitatea totalurilor cu exportul.
Captură reală Linux/Xvfb: [sesiune curentă și rezervare distinctă](capturi-ui/sesiune-curenta.png).
Nu reprezintă validare Windows, Outlook real sau suspendare Windows reală;
repausul și întreruperile sunt simulate determinist în teste.

Validarea finală în Linux/Xvfb: **427 teste reușite, 1 test specific Windows omis**; smoke test GUI reușit, compilare Python și verificarea dependențelor reușite. Protecția la dublu-click este testată cu ceas controlat; un gest distinct Continuă rămâne disponibil după intervalul scurt de protecție. Dialogul de corecție refuză salvarea peste o sesiune modificată după deschiderea sa.
