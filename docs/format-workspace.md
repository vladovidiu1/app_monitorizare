# Formatul workspace-ului FocusDesk

Un workspace este un folder local ales de utilizator. Nu există bază de date: doar JSON UTF-8, Markdown, fișiere și
arhive ZIP. Datele nu sunt niciodată în folderul executabilului sau în directoarele temporare PyInstaller.

## Structura pe disc

```
FocusDeskData/
  workspace.json                     identitate workspace (UUID, nume, demo)
  nodes/
    sap--1a2b3c4d/                     un nod: <slug>--<id scurt>; TOATE nodurile stau direct aici, indiferent de nivel
      node.json                        metadate (autoritar, inclusiv `parent_id`)
      description.md                   descriere (autoritar)
      notes/<uuid>.json                notițe de jurnal
      files/                           atașamente administrate (copii)
      snapshots/<uuid>.zip|.json       checkpoint-uri de cod + manifest
    validari-xml--5e6f7a8b/            un copil al lui `sap--1a2b3c4d`: același nivel pe disc, părintele e în `parent_id`
  _system/
    settings.json                      setări workspace (program, backup, Outlook...)
    colleagues.xlsx                    lista de colegi importată; înlocuită integral la următorul import
    index.json                         CACHE reconstructibil; poate fi șters oricând
    workspace.lock                     lock real de proces (portalocker)
    timer.json                         timerul activ (există doar cât timp rulează o sesiune)
    scheduler.json                     ultima zi în care a rulat checkpointul programat
    sessions/<uuid>.json               sesiuni de lucru (planificate / active / realizate / anulate / ratate)
    history/<uuid>.json                evenimente (creat, mutat, status schimbat, checkpoint...)
    operations/<uuid>.json             operații cu pași recuperabili (mutare, coș, restaurare, calendar)
    recurrences/<uuid>.json            șabloane recurente
    trash/<uuid-nod>/manifest.json     coș: manifest + `nodes/<director>` pentru fiecare nod din subarborele șters
    backups/                           backup-uri ZIP (metadate / complet)
    logs/
```

Doar directoarele din `nodes/` sunt noduri, și doar dacă au `node.json`. Directoarele `notes`,
`files`, `snapshots` nu sunt niciodată interpretate ca task-uri, chiar dacă ar conține `node.json`.

**Layout vechi (`children/`)**: versiunile anterioare imbricau directoarele copiilor în `children/`, iar adâncimea ierarhiei era
limitată de lungimea căii Windows (≈ 3–4 niveluri). La deschiderea unui workspace vechi (editabil) directoarele se scot
automat în `nodes/` (doar redenumiri de directoare; `node.json`, fișierele și ierarhia rămân neschimbate); operația este
idempotentă și apare ca mesaj la deschidere. Intrările vechi din coș se restaurează și ele în layout plat. Un workspace vechi
deschis doar pentru citire este încărcat tolerant, fără modificări.

## Nume fizice

`<slug>--<primele 8 caractere din UUID>`. Slug-ul are maximum 20 de caractere, fără diacritice, litere mici,
`a-z0-9-`. Se tratează numele rezervate Windows (`CON`, `NUL`, `COM1`...), caracterele interzise, punctele și spațiile
finale, coliziunile. Titlul poate avea orice diacritice; **UUID-ul complet din `node.json` este identitatea stabilă**.
Redenumirea schimbă titlul, nu directorul; „Aliniază numele directorului” este o acțiune explicită.

Lungimea căii se verifică la creare/restaurare/redenumire fizică: aplicația nu presupune că suportul Windows pentru căi lungi
este activ (limita internă 259 de caractere). Cum toate nodurile sunt direct în `nodes/`, calea unui nod nu depinde de
adâncimea ierarhiei, ci doar de lungimea rădăcinii workspace-ului: recomandat `C:\FocusDeskData` sau o cale scurtă.

## `node.json`

Câmpuri tehnice în engleză (schema_version = 1). Câmpurile necunoscute sunt păstrate la rescriere.

| Câmp | Tip | Observații |
|---|---|---|
| `schema_version`, `revision` | int | `revision` crește la fiecare scriere |
| `id` | UUID | identitate stabilă |
| `kind` | `folder` / `project` / `task` | regulile de părinte: task în orice; proiect doar în rădăcină/folder; folder în folder/proiect |
| `title` | text | |
| `parent_id` | UUID sau null | părintele logic (un singur părinte); singura sursă a ierarhiei |
| `status` | `inbox` `todo` `in_progress` `waiting` `testing` `done` `cancelled` | null la folder |
| `priority` | `urgent` `high` `normal` `low` | |
| `created_at`, `updated_at`, `completed_at`, `review_at`, `archived_at` | UTC `YYYY-MM-DDTHH:MM:SSZ` | |
| `due_date` | `YYYY-MM-DD` | termen fără oră; rămâne dată, nu miezul nopții UTC |
| `due_at` | UTC | termen cu oră (excludă `due_date`) |
| `estimated_minutes`, `remaining_minutes` | int sau null | `null` = neestimat (nu 0) |
| `next_action`, `waiting_reason` | text sau null | |
| `requested_by` | `{name, code}` sau null | solicitantul task-ului; codul generează adresa `code@eon.com` |
| `tags` | listă | |
| `related_node_ids` | listă UUID | referințe (legături), fără copii fizice |
| `depends_on_ids` | listă UUID | dependențe; fără cicluri |
| `sort_order` | int | |
| `pinned_today` | dată | prioritate marcată pentru acea zi (max. 3 pe zi) |
| `source_workspace` | `{path, mode}` sau null | `external` = cale absolută; `managed` = relativă la nod (ex. `files/cod`) |
| `checklist` | `[{text, done}]` | pași mici, fără identitate proprie |
| `attachments` | listă | `{id, name, mode: managed/external, path, is_dir, added_at}` |
| `recurrence_template_id`, `occurrence_date` | | pentru instanțe generate dintr-un șablon |

Reguli validate (Pydantic): un folder nu are status, estimări sau termen; un proiect nu are estimări directe (se agregă);
un nod nu poate fi propriul părinte sau să se refere la sine; căile administrate nu conțin `..` și nu sunt absolute;
căile externe sunt absolute.

### Agregare

Progresul unui proiect/task cu copii folosește **task-urile frunză** (fără copii-task), exclude `cancelled`, raportează
numărul celor neestimate și nu adună estimarea părintelui cu a copiilor. Închiderea tuturor copiilor nu finalizează
părintele.

## Colegi (`_system/colleagues.xlsx`)

Registrul se importă din Setări › Colegi. Fișierul `.xlsx` este copiat în workspace și inclus atât în backup-ul de
metadate, cât și în cel complet; nu mai este necesar fișierul original. Se citește prima foaie: coloana A = nume complet,
coloana B = cod, fără domeniu. Antetul `Nume complet` / `Cod` este opțional. Rândurile goale se ignoră; numele identice
cu coduri diferite sunt permise. Codurile se normalizează la litere mici; codurile duplicate, rândurile incomplete,
formulele și fișierele goale sunt respinse înainte de înlocuirea atomică a listei salvate.

Task-ul păstrează numele și codul solicitantului la momentul selecției. La compunerea mailului se folosește înregistrarea
curentă cu același cod; dacă acel coleg a dispărut din lista nouă, datele salvate în task rămân disponibile. Task-urile
vechi, fără `requested_by`, se încarcă fără migrare. Importul nu este permis în modul doar pentru citire.

## Sesiuni (`_system/sessions/<uuid>.json`)

`id`, `node_id`, `workspace_id`, `start_at`/`end_at` (UTC), `tz` (fusul de afișare), `status`, `origin`,
`actual_seconds` (timp lucrat efectiv, din timer), `started_actual_at`, `stopped_actual_at`, `summary`,
`reserve_calendar` și obiectul separat `sync`:

`sync = {provider, state, entry_id, store_id, calendar_folder_id, last_synced_at, signature, error, sequence,
exported_at, ics_uid}`; `state` ∈ `none, pending, saved_locally, failed, conflict, exported, detached, cancelled`.

Timpul planificat nu este timp lucrat: doar `actual_seconds` contează.

## Integritate și recuperare

* **Scriere atomică**: fișier temporar în același director, `flush` + `fsync`, `os.replace`; ultima versiune validă a
  metadatelor importante se păstrează ca `.bak`. O eroare la scriere nu se afișează ca „Salvat”.
* **Detectarea editărilor externe**: la fiecare scriere se compară hash-ul fișierului cu cel citit; dacă s-a schimbat din
  afară, aplicația cere reîncărcare, nu suprascrie.
* **Lock**: un singur proces scriitor per workspace; a doua instanță deschide doar pentru citire.
* **Operații recuperabile**: mutare, coș, restaurare și redenumire fizică scriu o înregistrare în `_system/operations`
  înainte de efect; la pornire, operațiile întrerupte se finalizează (dacă directorul a fost mutat) sau se anulează
  (dacă nu s-a mutat nimic); stările ambigue sunt raportate, nu modificate.
* **Încărcare tolerantă**: JSON corupt, UUID duplicat, părinte lipsă, cicluri, referințe invalide sunt raportate în
  „Instrumente › Verificare integritate”; un nod corupt nu blochează restul și nimic nu se șterge automat.
* **Coș**: ștergerea mută nodul și descendenții în `_system/trash`; restaurarea păstrează UUID-urile și legăturile.
* **Symlink/junction**: nu se urmăresc la scanări și copii recursive; căile administrate nu pot ieși din nod.
* **ZIP**: la import/restaurare se validează fiecare intrare (fără `..`, fără căi absolute, fără symlink, limită de mărime)
  înainte de extragere.

## Checkpoint-uri (`snapshots/`)

`<uuid>.zip` conține `manifest.json` și fișierele sub `files/<cale relativă>`; `<uuid>.json` este manifestul lângă
arhivă (pentru listare rapidă). Manifest: `id`, `node_id`, `owner_node_id`, `project_id`, `session_id`, `created_at`,
`description`, `trigger`, `source_root`, `files[{path, size, sha256, mtime_ns}]`, `total_size`, `excluded_count`,
`complete`. Este un snapshot complet filtrat (nu incremental): se creează doar dacă hash-urile s-au schimbat, cu limite de
mărime și retenție. Excluderi implicite: `.git`, `.venv`, `venv`, `__pycache__`, `node_modules`, `build`, `dist`,
`snapshots`, `backups`, `.env`, chei private și fișiere de credențiale. Dacă sursa se modifică în timpul capturii,
checkpoint-ul NU se păstrează.

## Date istorice ale extensiilor eliminate

În workspace-urile vechi pot exista `_system/mail/` și evenimente istorice
`ai_proposal`. Aceste fișiere rămân pe disc, fără citire a inboxului, procesare,
reconciliere sau ștergere automată. Backupurile obișnuite le pot păstra în continuare.
Setările necunoscute sunt păstrate inert prin `extra="allow"`.
Taskurile și subtaskurile create anterior, notițele, sesiunile și descrierile nu au
un tratament special în funcție de origine: rămân date normale ale utilizatorului.
