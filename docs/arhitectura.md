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
  ciornă) → la succes se notează trimiterea în Jurnalul task-ului. La timeout nu se afirmă că mesajul a plecat sau nu.
* **Ierarhie**: lista centrală (`TaskList`) construiește arborele din `parent_id` (stramoșii task-urilor filtrate rămân
  vizibili); progresul pe noduri vine dintr-o singură trecere (`Queries.progress_map`).
