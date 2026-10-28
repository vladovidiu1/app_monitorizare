# Verificări pentru versiunea office fără AI

Revizia curentă elimină motorul local și toate funcțiile AI, precum și citirea,
monitorizarea și analiza inboxului Outlook. Nu s-a construit executabilul și nu
s-a pornit workflow-ul de distribuție în această etapă, conform cererii.

## Șabloane reutilizabile — verificarea curentă

Implementate local: catalog implicit/personal, creare cu previzualizare și variabile,
capturarea unei structuri existente, editor Markdown/ierarhie/checklist, duplicare,
ștergere, import/export JSON și integrare în backup/restaurare. Fără AI sau analiză de mail.

Verificat efectiv în Linux/Python 3.12/Tk 9, pe date temporare:

- **42 teste noi trec**, dintre care 6 UI: structuri pe mai multe niveluri, UUID-uri noi,
  remapare dependențe/legături, păstrarea ordinii, excluderea metadatelor personale,
  variabile inclusiv blocuri Markdown de cod, limite de expansiune/import, JSON invalid,
  scheme incompatibile, câmpuri nepermise și cicluri.
- Catalogul implicit nu creează noduri sau fișiere personale. Copiile se păstrează
  după restart. Editările concurente nu se suprascriu. Doar citire și schimbarea
  workspace-ului blochează aplicarea dialogurilor vechi.
- Backup/restaurare meta și full păstrează șabloanele. O eroare după scrierea
  parțială declanșează rollback. Simularea întreruperii procesului este recuperată
  la redeschidere; este testată și reîncercarea unui rollback blocat inițial.
- Apăsarea repetată nu dublează structura; ID-ul cererii funcționează și după restart.
  UI cere o previzualizare nouă când datele au fost schimbate.
- Suita completă: **267 trec, 14 eșecuri preexistente pe Linux, 1 omis**. Eșecurile
  au fost comparate cu raportul anterior: exact același set de validări Windows ale
  căilor (stage3/stage7/files-checkpoint UI). Regulile Windows nu au fost relaxate.
- Capturi reale Tk inspectate pentru gestionare, creare/previzualizare și editor:
  [ghid și capturi](SABLOANE.md). Scriptul folosește workspace demonstrativ temporar.

Nu s-a construit executabilul și nu s-a lansat workflow-ul. Resursele șabloanelor sunt
incluse în configurația setuptools/PyInstaller, dar distribuția EXE nu a fost verificată
în această etapă. Outlook real și DPI nativ Windows rămân verificări manuale.

## Spațiul de lucru al taskului — verificarea precedentă

Pagina centrală reutilizează editorul Markdown, ciornele inspectorului și serviciile
existente. Include navigare Înapoi/subtask, panou secundar redimensionabil, F11 pentru
Concentrare și stare explicită a salvării. Nu schimbă formatul workspace-ului.

Verificări executate în Linux/Python 3.12/Tk 9, fără AI și fără Outlook:

- **18 teste noi trec** (`tests/test_task_space.py`): salvare și revenire, ciornă comună,
  scroll, subtaskuri, focus/layout exact, Ctrl+S, timer în navigare, anularea plecării,
  doar citire, task dispărut/restaurat, arhivare, eroare la salvare, dublu clic existent,
  fereastră minimă, multe subtaskuri și schimbarea workspace-ului fără scurgere de undo.
- Suita completă: **225 trec, 14 eșecuri preexistente, 1 omis**. Setul eșecurilor a fost
  comparat cu raportul reviziei precedente: identic. Sunt cazuri de căi Windows pe
  Linux (stage3, stage7 și files/checkpoint UI); regulile Windows nu au fost relaxate.
- Smoke din surse: pornire fără AI/Outlook, cele patru destinații, editare/salvare în
  spațiul taskului, intrare/ieșire Concentrare și revenire, redeschiderea datelor.
- Capturi reale Tk pe date demonstrative temporare: 1440×900, 1100×700 și scalare Tk
  125% (1800×1125). Inspectate pagina și Concentrare; fără erori callback în script.
  Vezi [ghidul și capturile](SPATIU-DE-LUCRU.md).

Nu s-a construit executabilul și nu s-a pornit workflow-ul. Outlook Classic real și
DPI nativ Windows rămân verificări manuale pe calculatorul țintă. Toate integrările
existente sunt păstrate; nu există AI sau citire/analiză de inbox.

## Navigare și experiență zilnică — verificarea precedentă

Patru destinații: Astăzi, Proiecte și taskuri, Calendar, Activitate. Așteptare,
restante și finalizate sunt filtre rapide. Inspectorul are Detalii/Subtaskuri/
Activitate/Fișiere/Planificare/Versiuni; se retrage fără selecție și păstrează
acțiunile esențiale vizibile. E-mailul manual este în Mai multe și pe Ctrl+M.
Arhiva, setările, coșul și backupurile rămân accesibile secundar.

Statusul vechi `inbox` este afișat și filtrat ca De făcut, fără rescriere la citire
sau la salvarea altor câmpuri. Captura rapidă folosește acum `todo`. Fără proiect
se calculează prin părinții reali, independent de status sau legături. Datele nu au
fost șterse sau mutate automat. Preferințele vechi de navigare și taburi sunt acceptate.

Verificări efective în Linux, Python 3.12/Tk 9 și Xvfb, fără AI și fără Outlook real:

- **21 cazuri noi** pentru statutul vechi și lipsa rescrierii, filtre/proiect real/
  solicitant, câmpuri de filtrare cu evenimente Tk, preferințe vechi, cele patru
  destinații, task independent → proiect → subtask → sesiune → pauză/continuare →
  finalizare/redeschidere → arhivare/restaurare și coș/restaurare, notițe nesalvate,
  selecție/scroll, timer și registrul timpului lucrat separat de programat.
- **53 teste UI/editor/compatibilitate trec** în cadrul suitei complete.
- Suita completă: **207 trec, aceleași 14 eșecuri preexistente pe Linux, 1 omis**.
  Validările Windows ale căilor nu au fost relaxate.
- Scenariile existente de calendar/Planner/ICS/recurențe și e-mail manual cu
  confirmare prin backend Outlook fals sunt păstrate în suită.
- Smoke real din surse: pornire, toate cele patru pagini, creare/redeschidere date
  temporare și compatibilitate; fără pachete AI sau Outlook. Nu este un test EXE.
- Capturi reale regenerate: 1440×900, minim 1100×700 și scalare Tk 125% pe un
  desktop virtual 2600×1800. Inspectate vizual Astăzi, task/inspector, Activitate,
  lista completă și exemplele de la minim/125%; zero erori de callback Tk.
  Sesiunile din capturi sunt sintetice, numai în workspace demonstrativ temporar.
- Documentația, legăturile interne și compileall sunt actualizate/verificate.
  Nu s-a construit executabilul și nu s-a pornit workflow-ul.

Detalii: [NAVIGARE.md](NAVIGARE.md). Windows DPI real, Outlook Classic real și
executabilul împachetat rămân verificări manuale. Testele cu backend fals și
scalarea Tk nu certifică aceste integrări.

## Etapa precedentă — statusuri și editor Markdown

Implementate pictograme locale originale MIT pentru cele șase statusuri, etichete
explicite și actualizare în arbore, listă/căutare, Astăzi și inspector/subtaskuri.
Textul taskurilor închise rămâne lizibil; filtrul listei supraviețuiește refresh-ului,
arborele are opțiune persistentă, iar inspectorul oferă redeschidere explicită.
Statusul părintelui nu este derivat automat din finalizarea copiilor.

Editorul Markdown are panou redimensionabil, toolbar, liste/indentare, Undo/Redo,
preview inert Tk și fereastră modală cu buffer partajat (peer Text). Anularea
restabilește snapshot-ul și starea de dinaintea extinderii; salvarea folosește
Workspace și păstrează fereastra deschisă la eroare. `description.md` rămâne autoritar.
Nu s-au introdus dependențe sau acces la rețea. Ghid: [DESCRIERE-MARKDOWN.md](DESCRIERE-MARKDOWN.md).

Verificat efectiv în Linux, Python 3.12.14, Tk 9/Xvfb, virtualenv fără AI/COM:

- **23 cazuri noi** pentru formatare și Undo/Redo, titluri, liste/Enter/indentare,
  șablon, linkuri și preview sigur, descrieri vechi, paste multilinie și diacritice,
  Ctrl+S real, selecție cu modificări nesalvate, peer/cancel/save/failure,
  redeschidere, pictograme actualizate, părinte independent și layout minim.
- **32 teste selectate trec**, inclusiv design și compatibilitatea versiunii office.
- Suita completă: **186 trec, aceleași 14 eșecuri preexistente de căi Windows pe
  Linux, 1 omis** (junction Windows). Nu au fost relaxate validările căilor.
- Smoke-ul real din surse pornește, creează și redeschide date temporare; trece.
- 9 capturi reale regenerate, inclusiv toate statusurile și preview extins;
  capturile inspectorului, statusurilor și preview-ului au fost inspectate vizual.
- Nu s-a construit executabilul și nu s-a pornit workflow-ul. Windows/Tk 8.6,
  DPI Windows și Outlook real rămân verificări manuale. Fonturile X11 din acest
  mediu au unele limitări de randare; testele verifică textul Unicode păstrat.

## Domeniul păstrat

Proiecte, taskuri/subtaskuri, checklisturi, dependențe, descrieri, jurnal, sesiuni,
timer, dashboard, calendar local, Planner determinist, recurențe, ICS, colegi și
solicitant, fișiere/VS Code/Git, checkpointuri/backup și interfața luminoasă.
Outlook: disponibilitate și rezervări personale de timp în calendar; e-mail manual
nou din task, ciornă editabilă în Outlook și trimitere numai după confirmare.

## Protecția datelor

Cheile vechi din configurație sunt tolerate și păstrate inert. Taskurile și
înregistrările deja create nu sunt filtrate după origine și nu sunt șterse.
Cache-ul `_system/mail/` și evenimentele istorice rămân pe disc, fără procesare sau
curățare automată. Testele de compatibilitate verifică redeschiderea acestor date.

## Verificări ale etapei de eliminare AI

Mediu executat: Linux x64, CPython 3.12.14, Tk real cu Xvfb. A fost creat un
virtualenv nou numai cu `pip install -e ".[dev]"`, fără llama-cpp-python, NumPy,
Jinja2, diskcache, pywin32 sau model. `pip check` nu raportează dependențe lipsă.

| Verificare executată | Rezultat |
|---|---|
| Pornire reală `python -m focusdesk --smoke-test` în mediul curat | Trece; proiect/task/subtask, jurnal și sesiune, navigare, închidere/redeschidere și setări păstrate |
| Smoke separat cu importuri AI și COM blocate explicit | Trece; pornirea și funcțiile locale nu depind de acestea |
| Date istorice și configurații vechi | Trec; checklist bifat, descriere, subtask, notiță, sesiune și istoric păstrate; cache mail nemodificat; chei vechi active rămase inerte |
| Suită relevantă selectată | **131 trec**: compatibilitate, distribuție/audit, UI/design, ierarhie/mail/colegi, Outlook fals, organizare, Planner/ICS/recurențe și formate |
| Suită completă în mediul nou | **163 trec, 14 eșuează, 1 omis** |
| Comparație cu revizia anterioară `0ff4a09` | Aceleași 14 eșecuri reproduse în modulele stage3/stage7/UI; niciun eșec nou |
| Capturi reale ale interfeței actuale | 7 capturi, 1440×900, fără erori Tk; Astăzi inspectat vizual; comenzile și paginile eliminate nu mai apar |
| Windows wheels rămase | **27 hash-uri SHA256 verificate** folosind fișierele Windows descărcate anterior; nu s-a executat codul Windows |
| Colectare licențe, compileall și legături documentație | Trec; licențele nu includ pachete AI; fără legături interne lipsă |

Cele 14 eșecuri preexistente sunt provocate de `PureWindowsPath` în validarea
căilor externe pe Linux: 12 în `test_stage3.py`, unul în `test_stage7.py`, unul în
`test_ui_integration.py`. Nu a fost relaxată validarea Windows pentru a le ascunde.
Testul omis privește junction-uri Windows. Testele integrărilor folosesc backenduri
false; nu demonstrează funcționarea Outlook real. Nici scriptul PowerShell de build,
nici workflow-ul Windows actual nu au fost executate.

## Verificări manuale rămase

Windows: buildul actual, EXE fără Python, DPI/High Contrast și politici corporate.
Outlook Classic real: calendar de test, disponibilitate, conflicte, ciornă,
rezolvarea destinatarilor și trimitere cu confirmare. Aceste verificări nu au fost
executate în mediul Linux. Evenimentele sunt rezervări personale, fără invitați sau
Teams. Vezi [diagnostic-integrari.md](diagnostic-integrari.md).

## Etapa de performanță locală

Validare Linux/Xvfb: 291 teste trecute, 14 eșecuri preexistente de compatibilitate
pentru căi Windows, 1 test junction Windows omis. Smoke-testul real Tk trece.
Indexuri reconstructibile, ciorne/conflicte, read-only, recuperare și măsurători
înainte/după pentru 1.000 și 5.000 de taskuri:
[raport de performanță și rezultate brute](PERFORMANTA.md).
Nu s-a efectuat validare Windows, push, merge sau release.

## Dashboardul Activitate

Dashboard local cu model comun pentru carduri, grafice, calendar lunar, tabele și
CSV. Validare Linux/Xvfb: 309 teste trecute, aceleași 14 eșecuri preexistente pentru
căi Windows, 1 test Windows omis; cele 18 teste noi de dashboard trec. Smoke-testul
real trece. Capturi reale la 100% și la minimul scalat 125%/150%:
[ACTIVITATE-DASHBOARD.md](ACTIVITATE-DASHBOARD.md).
Fără dependențe noi, fără validare Windows, fără push/merge/release.

## Ghidul opțional pentru descriere

Formular modal cu ciornă proprie, Scop/pași/Rezultat așteptat, aplicare atomică în
Undo și alegere explicită pentru text existent. Același buffer PeerText și același
Salvează/Ctrl+S; fără scrieri implicite sau checklist/subtaskuri generate.
Validare Linux/Xvfb: 339 teste trecute, aceleași 14 eșecuri preexistente pentru căi
Windows și 1 omis. Cele 30 de cazuri noi ale ghidului trec; smoke-testul trece.
[Ghid și captură reală](DESCRIERE-MARKDOWN.md). Fără push, merge sau release.

## Cerințe ulterioare

Implementate redeschiderea cu motiv opțional și crearea idempotentă a cerințelor independente, cu relație navigabilă, cod comun explicit și checkpointuri separate. Validare Linux/Xvfb: 382 passed, 1 skipped (specific Windows). [Detalii și limite](CERINTE-ULTERIOARE.md).

## Sesiuni — verificare finală

Rezervări distincte de lucrul început explicit, timer unic inclusiv în pauză, indicator permanent în toate paginile/Concentrare, alegere explicită la schimbarea taskului, recuperare fără muncă offline presupusă și corecții atomice cu audit. Întreruperile dintre scrieri sunt recuperabile, rezumatul și evenimentul nu se dublează la retry. Rapoartele exclud intervalul tehnic al timerelor directe din Programat și separă live de timpul salvat.

Validare finală Linux/Xvfb: **427 passed, 1 skipped**; smoke test GUI, compileall, pip check și diff --check reușite. Testele folosesc exclusiv date temporare, cu repaus/crash simulate. Nu s-au validat Windows, suspendarea Windows sau Outlook real. Nu s-a făcut push, merge sau release. [Investigație, comportament și limite](SESIUNI.md).

## Verificarea integrată finală

**473 teste trecute, 1 test Windows omis**, smoke test GUI reușit, compileall/pip check/diff --check reușite. Fluxul cap-coadă acoperă toate etapele, inclusiv restart, reconstrucția cache-urilor și backup/restore. Corectate footerul întâlnirilor la fereastra minimă și selecțiile întârziate din lista ascunsă de taskuri. Verificare Tk/Xvfb la 100%/125%/150%, cu timer activ: 45 verificări geometrice. Benchmarkul final include 5.000 taskuri și 2.000 întâlniri; sunt raportate și costul primului dashboard fără index și creșterea memoriei. [Rezultate complete și limite](VERIFICARE-INTEGRATA.md). Fără validare Windows/Outlook real sau build/release.

Corecție suplimentară de integrare: operațiile locale de fundal și callbackurile lor păstrează workspace-ul/lockul până la finalizare. Teste dedicate verifică și checkpointul pornit de încheierea sesiunii. Rezultat final: **473 passed, 1 skipped**, 36,38 s.
