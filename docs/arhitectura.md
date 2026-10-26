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
  ai/            protocol JSON IPC, supervisor spawn, backend llama.cpp CPU, manifest/download și smoke real
                 assistant_protocol: răspunsuri cu surse și operații tipizate
```

## Fire de execuție

* **Thread-ul Tk** este singurul care atinge widgeturile și singurul care scrie în `Workspace` (UI + servicii).
* `UiBridge` rulează lucrări lungi (backup, checkpoint, copiere fișiere) în thread-uri; rezultatele ajung înapoi
  printr-o coadă golită cu `root.after`. O lucrare anulată (`CancelToken`) nu mai aplică rezultatul la sosire.
* **COM** rulează într-un singur thread dedicat (`ComWorker`) cu `CoInitialize/CoUninitialize`. Obiectele COM nu părăsesc
  thread-ul; spre UI circulă doar tipuri primitive (dataclass-uri). Timeout-ul este la nivel de UI: un apel COM blocat nu
  poate fi anulat forțat în siguranță, deci rezultatul tardiv este ignorat, iar cererile noi sunt refuzate până se termină
  apelul blocat (mesaj explicit).
* **AI**: un proces `spawn` separat deține biblioteca nativă și un singur model încărcat la cerere.
  Supervisor-ul și sender-ul IPC lucrează în fundal; mesajele JSON cu UUID ajung în Tk prin `UiBridge.post`.
  Procesul nu primește Workspace sau widgeturi. Anularea/timeout-ul termină procesul nativ și invalidează callback-ul;
  pornirea următoare este automată. La oprire normală se trimite `stop`, cu escaladare la terminate/kill dacă este necesar.
  Bootstrap-ul apelează `freeze_support` înainte de importul aplicației și pregătește stdout/stderr pentru executabilul fără consolă.
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
  ciornă) → la succes se notează trimiterea în Jurnalul task-ului. La timeout nu se afirmă că mesajul a plecat sau nu.
* **Ierarhie**: lista centrală (`TaskList`) construiește arborele din `parent_id` (stramoșii task-urilor filtrate rămân
  vizibili); progresul pe noduri vine dintr-o singură trecere (`Queries.progress_map`).
* **Propunere AI**: context limitat al nodului selectat → GGUF Qwen3, template cu `enable_thinking=False`
  → gramatică din JSON Schema → validare Pydantic → verificare semantică și fingerprint al sursei
  → previzualizare și confirmare → o singură scriere prin `Workspace`, exclusiv pe firul Tk.
  Nu se generează/comandă operații Outlook sau shell. Vezi [AI.md](AI.md).

Asistentul extins folosește `assistant_context` pentru recuperare lexicală prin Queries/serviciile existente,
într-un job anulabil UiBridge. Procesul modelului măsoară tokenii reali și returnează separat ID-urile
surselor folosite efectiv. `assistant_proposals` verifică surse/fingerprint-uri, simulează înainte/după
și dependențele întregului lot și aplică fiecare operație numai pe firul Tk. Rezervările UUID și rezultatele
se scriu prin Workspace în istoricul existent înainte/după efect; `started` rămas după crash blochează replay.
Nu există tranzacție atomică pentru lot: incertitudinea oprește operațiile următoare și este raportată distinct.
Ferestrele și tabul folosesc un epoch de workspace și o generație de cerere; callback-urile vechi nu se aplică.
Vezi [ASISTENT.md](ASISTENT.md).

## Monitorizarea mailurilor

`MailWatchController` serializează scanările pe `ComWorker` comun. `mail_read`
returnează exclusiv DTO-uri; `MailMonitorService` gestionează ferestrele, deduplicarea
și checkpoint-urile persistente. `mail_analysis` recuperează candidați prin Queries,
validează citate/date și proiectează estimarea în mecanismul comun de propuneri.
Firul UI persistă prin Workspace; inferența rulează în procesul AI existent.
Detalii și limite: [MAILURI.md](MAILURI.md).

## Fluxuri de productivitate AI

`services/ai_productivity.py` recuperează candidații zilei, calculează raportul din
Queries.worked_by_day și validează ciornele/selectarea prin ProposalBatch. Sursele
`report` au fingerprint recalculabil din cifrele și taskurile perioadei; sursele
zilei expiră la schimbarea datei locale/fusului. `ui/productivity_ui.py` recuperează
în fundal, apelează motorul existent și oferă previzualizare, copiere și transfer
explicit către MailDialog/PlannerDialog. Raportul complet este calculat în cod,
independent de reducerea detaliilor din prompt. Nu există operații IPC noi de
trimitere sau programare; salvarea rămâne în fluxurile manuale existente.

## Interfață luminoasă FocusDesk

Tema, fonturile, paleta, dimensiunile și pictogramele locale sunt centralizate în
`ui/design.py`. Aspectul luminos se aplică inclusiv configurațiilor vechi dark.
Vezi [ghidul vizual și capturile reale](INTERFATA.md) pentru layout, scalare,
reproducerea capturilor și limitele verificării Windows.
