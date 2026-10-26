# Arhitectură

Module mici, separate pe responsabilități; fără stare globală: `Workspace` și serviciile sunt obiecte pasate explicit,
UI-ul le primește prin `FocusDeskApp`.

```
src/focusdesk/
  main.py, config.py, errors.py
  domain/        modele Pydantic (Node, Session, Settings, Checkpoint) + etichete RO + timp/fus orar
  storage/       atomic JSON, nume Windows, căi sigure, lock, repository, operații recuperabile, ZIP sigur
  services/      workspace (fațadă pentru scriere), queries, backup, timer, sesiuni, planner, planificare,
                 recurență, fișiere, checkpoint-uri, scheduler, calendar_sync, mail, demo
  integrations/  calendar (protocol), ics, outlook (logică) + outlook_com (pywin32: calendar și e-mail), git, system (Explorer/VS Code)
  workers/       bridge (thread pool + coadă către Tk), com_worker (thread COM dedicat)
  ui/            fereastra principală, arbore, listă, inspector (taburi), Astăzi, calendar, dialoguri, setări
  resources/     pictograma aplicației
```

## Fire de execuție

* **Thread-ul Tk** este singurul care atinge widgeturile și singurul care scrie în `Workspace` (UI + servicii).
* `UiBridge` rulează lucrări lungi (backup, checkpoint, copiere fișiere) în thread-uri; rezultatele ajung înapoi
  printr-o coadă golită cu `root.after`. O lucrare anulată (`CancelToken`) nu mai aplică rezultatul la sosire.
* **COM** rulează într-un singur thread dedicat (`ComWorker`) cu `CoInitialize/CoUninitialize`. Obiectele COM nu părăsesc
  thread-ul; spre UI circulă doar tipuri primitive (dataclass-uri). Timeout-ul este la nivel de UI: un apel COM blocat nu
  poate fi anulat forțat în siguranță, deci rezultatul tardiv este ignorat, iar cererile noi sunt refuzate până se termină
  apelul blocat (mesaj explicit).
* Operațiile pe workspace din workeri sunt doar citiri/I-O pe fișiere proprii (ex. `CheckpointService.create`,
  `FileService.copy_managed`); înregistrarea în model se face pe thread-ul UI.

## Decizii principale

| Decizie | Motiv |
|---|---|
| `node.json` autoritar, indexul doar cache | indexul poate fi șters; nu există a doua „bază de date” |
| Părinte unic (`parent_id`) + referințe prin UUID | fără duplicate fizice; `related_node_ids` ≠ `depends_on_ids` ≠ `parent_id` |
| Toate directoarele nodurilor direct în `nodes/` | ierarhia (orice adâncime) nu crește calea; mutarea = o singură scriere atomică de `node.json` |
| Coș/restaurare = operație în jurnal + pași idempotenți | mutarea mai multor directoare nu este o tranzacție atomică |
| Hash la scriere (detectare editare externă) | nu se suprascrie silențios o editare făcută din Explorer |
| Timp monoton + detectarea golurilor | repausul/suspendarea Windows nu devine timp lucrat |
| Planner determinist | suprapunerile și capacitatea se calculează exact |
| Outlook prin COM în worker, markeri proprii | idempotență (regăsire după UUID), fără a atinge evenimente străine |
| E-mail doar la acțiune explicită, cu confirmare | `Send()` rulează doar din dialogul de e-mail; destinatarii nerezolvați opresc trimiterea |
| Git prin `subprocess` cu liste de argumente | fără shell, fără `git add .`, fără push/reset/stash/checkout |

## Fluxuri-cheie

* **Scriere**: `Workspace.update_node` → validare Pydantic → `repository.write_node` (verifică hash, scrie atomic,
  incrementează `revision`) → eveniment către UI → refresh. Eroarea de scriere nu lasă starea în memorie schimbată.
* **Sesiune**: `TimerService.start` → sesiune `active` + `timer.json` persistat periodic; la `stop` se salvează timpul
  efectiv, jurnalul, următorul pas, timpul rămas și (opțional) un checkpoint. După crash, `timer.json` declanșează
  reconcilierea: se păstrează doar timpul înregistrat până la ultima salvare, nimic inventat.
* **Calendar**: sesiunea marcată `reserve_calendar` → `CalendarSyncService.prepare` scrie operația `pending` →
  `execute()` în `ComWorker` (regăsire după UUID → create/update/cancel) → `apply()` actualizează `sync` și închide
  operația; eșecurile rămân vizibile și se pot reîncerca fără duplicate.
* **E-mail**: dialogul din task (`MailDialog`) validează adresele (`services/mail.py`) → confirmare →
  `OutlookController.send_mail` în `ComWorker` (`CreateItem` → `Recipients.ResolveAll` → `Send`, sau `Display` pentru
  ciornă) → la succes se notează trimiterea în Activitatea taskului. La timeout nu se afirmă că mesajul a plecat sau nu.
* **Ierarhie**: lista centrală (`TaskList`) construiește arborele din `parent_id` (stramoșii task-urilor filtrate rămân
  vizibili); progresul pe noduri vine dintr-o singură trecere (`Queries.progress_map`).

## Interfață luminoasă FocusDesk

Tema, fonturile, paleta, dimensiunile și pictogramele locale sunt centralizate în
`ui/design.py`. Aspectul luminos se aplică inclusiv configurațiilor vechi dark.
Vezi [ghidul vizual și capturile reale](INTERFATA.md) pentru layout, scalare,
reproducerea capturilor și limitele verificării Windows.

## Compatibilitate după eliminarea extensiilor

`AppConfig` și `Settings` păstrează `extra="allow"`: cheile vechi neutilizate nu
sunt validate ca setări active și nu declanșează servicii. Nu există migrare care
șterge taskuri sau istoricul. `_system/mail/` rămâne neutilizat pe disc.
Citirea inboxului și toate modulele AI au fost eliminate, inclusiv pornirea,
IPC-ul, pollingul și controalele UI. `ComWorker` rămâne exclusiv pentru calendar
și e-mailul trimis/afișat la acțiunea explicită a utilizatorului.

## Documentare Markdown și statusuri

`ui/status_visuals.py` mapează tipul/statusul la resurse locale MIT și etichete.
`ui/markdown_editor.py` oferă formatarea asistată și previzualizarea inertă în Tk
Text. Fereastra extinsă este un peer Tcl al bufferului din inspector, cu grab modal
și snapshot de anulare; nu are o copie independentă a descrierii. Salvarea rămâne
în DetailsTab → Workspace.set_description, pe firul UI. Nu se schimbă formatul sau
schema datelor și nu se introduc HTML, execuție de cod ori servicii externe.

## Destinații și registrul activității

`ui/activity_page.py` folosește `services/activity.py` pentru agregări directe din
sesiuni: actual_seconds pentru lucrat, intervale pentru programat, fără adunarea
rollup-urilor. Paginile Astăzi și Activitate păstrează widgeturile, selecția și
viewportul. Maparea legacy inbox → etichetă/filtru todo nu este o migrare pe disc.
Configurația aplicației normalizează destinațiile și taburile vechi. Jurnalul este
acum tabul Activitate, cu protecție și pentru notițele încă nesalvate.

## Pagina taskului și starea comună

`ui/task_space.py` este o pagină centrală persistentă, fără servicii sau format de
date nou. Reutilizează MarkdownEditor prin peer Tk al bufferului DetailsTab și
aceleași StringVar pentru următorul pas și adăugările rapide. JournalTab poate
partaja bufferul notei și tipul acesteia. Salvarea este delegată Inspector.save,
apoi Workspace pe firul UI. Secțiunile reutilizează SubtasksTab, FilesTab, JournalTab,
PlanTab și VersionsTab. Un singur serviciu timer rămâne autoritar.

Istoricul paginii păstrează filtre, selecții, viewporturi și panouri; concentrarea
păstrează separat layoutul de revenire. Generația callbackurilor de sash invalidează
repoziționările amânate după restaurarea explicită a layoutului. Selecțiile arborelui
ascuns nu declanșează navigare. Schimbarea workspace-ului golește istoricul, pozițiile
și proprietarul bufferelor, inclusiv undo, după rezolvarea ciornelor nesalvate.

## Șabloane de structură locale

`domain/templates.py` definește schema strictă, chei locale și grafuri validate.
`services/templates.py` citește resursele implicite și catalogul personal; scrierile UI
intră prin metodele `Workspace.*template`. Capturarea folosește o listă explicită de
câmpuri, fără copierea modelului Node integral. Substituția literală `{{nume}}` este
limitată și nu evaluează conținutul. `ui/templates_ui.py` folosește dialoguri nemodale,
editorul Markdown existent și verificarea identității workspace-ului înainte de scriere.

Crearea validează întregul graf și destinația, generează UUID-uri, remapează referințele
și jurnalizează planul în `OperationRecord(type=template_create)` înainte de orice nod.
Planul se scrie pe firul UI prin repository, în ordine părinte-copil, apoi se marchează
`done`; indexul rămâne un cache. Cererea UUID + amprenta datelor previn aplicarea dublă.
La eșec sunt retrase doar directoarele lotului nou. Operațiile `pending` sunt recuperate
înainte de încărcarea nodurilor la deschiderea editabilă, prin `storage/template_operations.py`.
Dacă rollbackul nu poate termina, jurnalul rămâne pending și eroarea este explicită.

Șabloanele personale se scriu atomic în `_system/templates`; versiunile/amprentele
previn suprascrierea ciornelor concurente. Backupurile standard le includ fără alt
format de restaurare. Resursele `resources/templates/*.json` sunt incluse în pachet
prin setuptools și `collect_data_files` existent pentru PyInstaller; nu a fost construit EXE.
