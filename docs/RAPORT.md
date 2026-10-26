# Verificări pentru versiunea office fără AI

Revizia curentă elimină motorul local și toate funcțiile AI, precum și citirea,
monitorizarea și analiza inboxului Outlook. Nu s-a construit executabilul și nu
s-a pornit workflow-ul de distribuție în această etapă, conform cererii.

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

## Verificări curente

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
