# Raport de verificare

Data: 2026-10-20. Mediu: Windows 10/11, Python 3.14.6 (singurul interpretor disponibil; `pyproject.toml` cere ≥ 3.11,
dar versiunile 3.11–3.13 **nu au fost rulate**). Toate dependențele au avut wheel-uri pentru 3.14.

## Verificat efectiv

| Ce | Cum | Rezultat |
|---|---|---|
| Logica de date: ierarhie, persistență la restart, ordine, legături fără duplicate fizice, mutări (UUID-uri/fișiere/notițe păstrate), **ierarhie de 40 de niveluri fără creșterea căii** (directoare plate), **migrarea automată a layout-ului vechi `children/`** (idempotentă), coș/restaurare (inclusiv intrări vechi din coș), coș întrerupt (finalizat la redeschidere), cicluri ierarhice și de dependențe, nume Windows rezervate, escaping din workspace, junction | pytest pe workspace-uri temporare | trece |
| Scriere atomică, scriere întreruptă (versiunea validă rămâne), JSON corupt, index lipsă, UUID duplicat, editare externă nesuprascrisă, a doua instanță doar citire | pytest | trece |
| Timer: doar timp activ, un singur timer, repaus/suspendare fără timp inventat, crash → reconciliere, timp planificat ≠ lucrat | pytest cu ceas fals | trece |
| Fișiere: copie administrată (conflict de nume), legătură externă (ștergerea nu șterge originalul), relocalizare, folder de cod moștenit, scripturi neexecutate | pytest | trece |
| Checkpoint-uri: manifest SHA-256, excluderi (`.env`, `.git`, chei…), dedup, sursă modificată în timpul capturii (nu se păstrează), diff, restaurare separată, suprascriere cu copie de siguranță, ZIP path traversal | pytest | trece |
| Planner: fără suprapuneri, pauze/program/zile libere, rezervă, task neestimat, dependențe blocate, termene, evenimente externe, ora de vară/iarnă (capacități 180/240/300 min), recurențe fără duplicate | pytest | trece |
| ICS: parsat cu `icalendar`, UTC, UID stabil, escaping, line folding, `TRANSP:OPAQUE`, anulare, „Exportat — necesită import” | pytest | trece |
| Outlook: creare personală cu markeri, retry fără duplicat (inclusiv crash între Save și JSON), update, conflict (mutat/șters în Outlook), cele trei rezolvări, anulare, evenimente străine neatinse, eșec parțial raportat, politici de disponibilitate, ComWorker (thread dedicat, timeout, rezultat tardiv ignorat) | pytest cu **backend Outlook fals** | trece |
| E-mail din task: adrese (separatori, `Nume <adresa>`, invalide, dedup), reguli de trimitere vs. ciornă, text implicit cu contextul task-ului, trimitere/ciornă prin `OutlookController` cu **backend fals**, înregistrare în Jurnal doar la trimitere reușită, eșec → nimic jurnalizat | pytest | trece |
| Progres agregat pe toate nodurile (`progress_map`) identic cu `progress` pe fiecare nod | pytest | trece |
| Git: status/log/diff/commit doar pentru fișierele alese; nu există operații periculoase | pytest cu `git` real | trece |
| Checkpoint programat: decizii, ora ratată raportată, dedup pe sursă | pytest | trece |
| UI Tkinter real (fereastră invizibilă): toate vizualizările, fiecare nod × fiecare tab, căutare/filtre, salvare Detalii, subtask/checklist/jurnal, **arbore ierarhic cu adăugare rapidă la 3 niveluri sub un task + indent/outdent**, fișiere + checkpoint + diff, timer, calendar + planificare, setări, temă, fluxuri Outlook și **e-mail** (backend fals), coș/restaurare | pytest (`tests/test_ui_integration.py`) | trece, fără excepții în callback-uri |
| Aspect: arbore de proiect cu ierarhie, temă deschisă și întunecată (pornit direct în dark), dialogul de e-mail | capturi ale ferestrei aplicației (PrintWindow) | inspectat vizual |
| Build PyInstaller **onedir** | `scripts/build.ps1` | reușit |
| Executabilul pornește, încarcă un workspace demo și afișează fereastra principală (cu `PATH` fără Python), nu scrie date în folderul executabilului | `scripts/verify_exe.ps1` | reușit |

Total: **151 de teste automate** trec (aprox. 43 s). Față de versiunea anterioară: testele asistentului Ollama au fost eliminate
cu funcția; s-au adăugat teste pentru ierarhie, migrare și e-mail.

## NU a fost verificat (rămâne pentru calculatorul țintă)

* **Outlook Classic real prin COM** — backend-ul `outlook_com.py` nu a rulat (doar logica de deasupra lui, cu backend fals).
  Pași în [diagnostic-integrari.md](diagnostic-integrari.md); de testat într-un calendar de test ales explicit
  (format regional al filtrului `Restrict`, conversia fusului orar, `UserProperties`, politici de securitate).
* **Trimiterea de e-mail prin Outlook COM real** (`send_mail`: `CreateItem`, `Recipients.ResolveAll`, `Send`, `Display`) — doar
  logica din jur a fost testată, cu backend fals. De verificat: ciorna, un mesaj către tine însuți, destinatar inexistent,
  comportamentul semnăturii și eventualele avertismente de securitate Outlook (vezi diagnostic-integrari.md).
* **Migrarea unui workspace real vechi** (layout `children/`) — verificat pe workspace-uri create în test, nu pe datele tale.
  Fă un backup (Fișier › Backup acum) înainte de prima deschidere a unui workspace existent cu versiunea nouă.
* **Executabilul pe un calculator fără Python** — verificat doar cu `PATH` fără Python pe aceeași mașină. Build-ul
  **onefile** nu a fost construit.
* Deschiderea efectivă a Explorer/VS Code și a fișierelor cu aplicația asociată.
* Repaus/hibernare reală Windows (timerul este testat cu ceas simulat), scalăre DPI pe alte monitoare, navigarea doar cu
  tastatura, fluiditatea joburilor lungi pe workspace-uri mari, aspectul tuturor dialogurilor în tema întunecată (inspectate
  doar fereastra principală și dialogul de e-mail în deschis).
* Python 3.11–3.13.

## Probleme găsite și corectate în timpul verificării

* Scriere/mutare: reîncercări la „acces refuzat” tranzitoriu (antivirus/OneDrive) la redenumirea directoarelor.
* `SessionRecord`: setarea separată a capetelor intervalului încălca validarea; adăugat `set_interval`.
* Fus orar invalid în setări ridica o excepție nevalidată; acum este o eroare de validare afișată.
* Parsarea duratelor (`1h30`, `3 ore`) nu acoperea formatele afișate în aplicație.
* Bucle de evenimente în sidebar (evenimentele virtuale Tk sunt asincrone) — rezolvat prin comparare de stare.
* **Adâncimea ierarhiei era limitată la ~3–4 niveluri** de lungimea căii Windows (directoare imbricate `children/`, ~40 de
  caractere/nivel), incompatibil cu task-uri în task-uri fără limită. Rezolvat: toate nodurile stau direct în `nodes/`.
* ttkbootstrap 2.x ignoră numele de stil de tip `primary.TButton` pe widgeturi ttk obișnuite: butoanele accent folosesc
  acum `ttkbootstrap.Button(bootstyle=...)`. Culorile câmpurilor `tk.Text`/`Listbox` și fundalul gol al listelor urmăresc
  acum tema (în tema întunecată erau albe).

## Observații de securitate și confidențialitate

Argumente de proces ca liste (`shell=False`), fără executarea scripturilor utilizatorului, ZIP validat înainte de extragere,
fără symlink/junction în copii și scanări; e-mailul se trimite doar la acțiune explicită (confirmare, validare de adrese, subiect pe o
singură linie, nimic trimis dacă un destinatar nu se rezolvă). Evenimentele Outlook nu conțin căi locale decât dacă activezi
explicit includerea detaliilor.
