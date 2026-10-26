# Plan de implementare și stare

Planul urmărește cele 7 etape din specificație; aplicația a fost pornibilă la finalul fiecărei etape.
Legendă: **Implementat** = scris și acoperit de teste automate sau verificat prin rulare; **De verificat pe Windows** =
scris, dar neverificat automat în acest mediu (vezi [diagnostic-integrari.md](diagnostic-integrari.md)); **Amânat** = nu este
în această versiune.

## Etapa 1 — Fundație și design real Tkinter — Implementat

| Funcție | Stare |
|---|---|
| Fereastră Tkinter+ttk (ttkbootstrap), panouri redimensionabile, meniu clasic, temă deschisă/întunecată persistentă, DPI | Implementat (verificat vizual prin capturi) |
| Workspace gol la prima pornire, workspace demonstrativ la cerere | Implementat |
| Modele Pydantic cu `schema_version`, scriere atomică, `.bak`, hash/revizie, lock real (portalocker) | Implementat, testat |
| Creare/editare/redenumire noduri, arbore `ttk.Treeview`, inspector „Detalii”, persistență la restart | Implementat, testat |
| Nume fizice Windows (slug + sufix UUID, nume rezervate, lungimea căilor) | Implementat, testat |

## Etapa 2 — Organizare completă — Implementat

Mutări recuperabile (jurnal de operații + recuperare la pornire), subtask-uri pe mai multe niveluri, checklist, legături
(`related_node_ids`) și dependențe (`depends_on_ids`) fără cicluri, filtre/căutare, vizualizări Inbox/Astăzi/În
așteptare/Restante/Calendar/Arhivă, jurnal, coș cu restaurare, arhivare cu alegerea pentru sesiunile viitoare, backup
(metadate/complet, zilnic, retenție, folder extern), verificare integritate. Testat.

## Etapa 3 — Execuție și fișiere — Implementat

Timer unic cu ceas monoton și reconciliere după repaus/crash, sesiuni, atașamente administrate/externe, folder de cod
moștenit, deschidere în Explorer/VS Code (fără shell, fără rularea scripturilor), checkpoint-uri ZIP cu manifest SHA-256,
diff, restaurare în folder separat, protecție la ZIP path traversal și junction. Testat. *Deschiderea efectivă a
Explorer/VS Code nu este verificată automat.* → De verificat pe Windows.

## Etapa 4 — Planificare — Implementat

Calendar local (agendă), programare manuală, planificator determinist (program, pauze, sesiuni locale, evenimente
externe, dependențe, termene, fragmentare, rezervă, ora de vară/iarnă), previzualizare cu motive pentru ore nealocate,
recurențe cu cheie unică și zile ratate la alegere, export ICS validat cu `icalendar`. Testat.

## Etapa 5 — Outlook Classic COM — De verificat pe Windows

Worker COM dedicat, diagnostic și alegerea calendarului, citire disponibilitate, creare/actualizare/anulare doar pentru
elemente proprii (markeri UserProperties), operații reluabile și conflicte. Logica este testată cu un backend fals;
**backend-ul COM real nu a fost rulat** (vezi diagnostic).

## Etapa 6 — E-mail din task — De verificat pe Windows (a înlocuit asistentul Ollama, eliminat la cererea utilizatorului)

Dialog „E-mail din task” (Ctrl+M, buton „✉ E-mail”, meniu contextual): destinatari/CC validate, subiect și text implicit
cu contextul task-ului, confirmare la trimitere, opțiune de ciornă în Outlook, înregistrare în Jurnal. Logica este testată cu
backend fals; **`send_mail` prin COM real nu a fost rulat**.

## Revizuire ierarhie și aspect — Implementat

Ierarhie de orice adâncime (directoare plate în `nodes/`, `parent_id` autoritar; migrare automată a layout-ului vechi), lista
centrală ca arbore cu adăugare rapidă, ▲▼◀▶ și progres pe noduri; aspect modern (temă, spațieri, antet de
inspector cu titlul).

## Etapa 7 — Automatizări și distribuție — Implementat (build verificat, vezi raport)

Checkpoint programat (cât rulează aplicația) cu raportarea orei ratate, checkpoint la finalul sesiunii, Git opțional
(status/log/diff/commit manual), build PyInstaller onedir (+ onefile opțional), README și documentație.

## Amânat / explicit în afara versiunii

* Drag-and-drop în arbore (opțional în specificație).
* Extensia VS Code „Save All” (fază viitoare).
* Programare prin Windows Task Scheduler (documentată ca opțiune viitoare).
* RAG/baze vectoriale, colaborare multiutilizator, autentificare, Microsoft Graph, servicii cloud.
* Implementare de adaptor email pentru ICS (există doar interfața documentată, dezactivată).
* `watchdog` (rescanarea este manuală: Fișier › Rescanează workspace).
