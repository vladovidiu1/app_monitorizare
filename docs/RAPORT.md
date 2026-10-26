# Raport de verificare

## Distribuție Windows x64 — CONSTRUITĂ ȘI VERIFICATĂ, 2026-10-26

[Job GitHub Actions reușit](https://github.com/vladovidiu1/app_monitorizare/actions/runs/40352492139),
commit de build `e505a01f6cffa5330199fe63d01f74360534f560`, Windows 2025 x64,
CPython **3.12.10**, llama-cpp-python **0.3.36 CPU**, GGUF-ul real din manifest.
Toate modificările aplicației și configurația de build sunt publicate pe `main`.

| Verificare executată pe Windows | Rezultat |
|---|---|
| Testele aplicației | **282 trecute, 1 omis, 0 eșecuri**, 283 în total |
| Build PyInstaller | **onedir reușit**, modelul extern în `models/`, DLL-uri CPU și licențe incluse |
| EXE real, lansat cu PATH gol | Pornit fără Python extern; pywin32 adaugă numai propriul director DLL din `_internal`, verificat explicit |
| Inferență offline GGUF real | **Reușită**, cu firewall outbound blocat pentru EXE și procesul copil |
| Propunere de task | Generată de modelul real și aplicată prin mecanismul comun într-un workspace temporar |
| Proces copil / închidere | PID separat, procesul și supervisorul oprite la închiderea aplicației |
| Model absent | Eroare controlată; UI rămâne utilizabilă și permite creare manuală de task |
| Workspace / preferințe | Redeschidere și câmpuri păstrate în profilul temporar izolat; pachetul nu conține configurații personale |
| ZIP64 | Audit, SHA256 model, CRC al arhivei și checksum ZIP reușite înainte de upload |
| Artifact complet | **FocusDesk-Windows-x64-cu-model**, 5.138.382.795 octeți (aprox. 5,14 GB) |
| Artifact update | **FocusDesk-Windows-x64-fara-model**, 110.598.912 octeți (aprox. 111 MB) |
| Outlook Classic real | **Neexecutat**; integrarea rămâne opțională și verificarea manuală este documentată |

Descărcare: [pachet complet](https://github.com/vladovidiu1/app_monitorizare/actions/runs/40352492139/artifacts/12664103443),
[update fără model](https://github.com/vladovidiu1/app_monitorizare/actions/runs/40352492139/artifacts/12665522388),
[rapoarte JUnit/JSON](https://github.com/vladovidiu1/app_monitorizare/actions/runs/40352492139/artifacts/12665321880).
Pachetul complet expiră **27 octombrie 2026, 17:59, Europe/Bucharest** (retenție o zi).
După expirare poate fi regenerat prin Run workflow. [Pași exacți](DISTRIBUTIE-WINDOWS.md).
Metadatele și digest-urile oficiale ale artifactelor sunt versionate în
`packaging/windows-build-verification.json`. Au fost inspectate concluzia jobului,
rapoartele JSON din adnotările GitHub și metadatele artifactelor publicate.

Cazul real a rulat cu PID părinte 5972 și PID copil 3348; cazul modelului absent cu
PID părinte 5716 și PID copil 5288. Fiecare a confirmat închiderea copilului și
păstrarea datelor temporare. Nu au fost folosite workspace-uri sau mailuri reale.

Pregătirea a identificat două diferențe Windows: catalogul GitHub nu oferă 3.12.14
pentru Windows (a fost ales 3.12.10 disponibil), iar hook-ul pywin32 adaugă legitim
propriul folder DLL în PATH după lansare. Validatorul permite strict directoarele
pachetului, fără a cere sau permite Python extern. Licențele cu același basename
sunt păstrate în subdirectoare distincte. Rulările intermediare eșuate nu au publicat
pachete de distribuție.

Semnarea digitală nu este configurată. Verificarea manuală Outlook real și DPI pe
monitoare Windows diferite rămâne separată de smoke-ul automat al executabilului.


## Distribuție Windows x64 — pregătire 2026-10-26

Adăugate workflow manual Windows, lock cu 32 wheel-uri Windows verificate SHA256,
build onedir cu DLL-uri CPU, licențe și model extern, arhivare ZIP64 și pachet mic
fără model. Cache-ul GGUF include revizia și SHA256; modelul nu intră în Git.

Verificări locale executate pe Linux:

- **267 teste trec, 14 eșecuri preexistente, 1 omis**; patru teste noi pentru audit,
  ZIP64, excluderea modelului din update și izolarea profilului de diagnostic.
- Descărcate efectiv cele 32 wheel-uri pentru CPython 3.12 Windows x64; hash-uri
  salvate și reverificate prin `scripts/verify_windows_wheels.py`.
- `actionlint 1.7.12` trece pentru workflow; compileall și diff-check trec.
- Diagnosticul nou de model absent a fost rulat din surse cu Tk real: UI utilizabilă,
  proces copil separat, închidere verificată și date/setări temporare păstrate.

**Aceste verificări locale nu reprezintă un build Windows verificat.** Starea rulării
GitHub Actions este consemnată în secțiunea de rezultat reușit de mai sus. Testul
Outlook Classic real rămâne manual. [Pași și limite](DISTRIBUTIE-WINDOWS.md).


## Modernizare FocusDesk Light — 2026-10-26

Interfață exclusiv luminoasă în Tkinter + ttkbootstrap; configurațiile vechi dark
pornesc luminos fără pierderea celorlalte preferințe. Nu s-a generat executabilul.

| Verificare executată | Rezultat |
|---|---|
| Suita completă | **263 trec, 14 eșuează, 1 omis**; aceleași 14 eșecuri preexistente de căi Windows pe Linux, baseline 259/14/1 |
| 4 teste UI noi | Migrare dark, păstrarea setărilor AI, contrast minimum 4,5:1 pentru text/selecție/accent, pictograme locale, salvare vizibilă la minim, acces la coloane, focus și stilul dialogurilor create ulterior |
| Suita UI în ordine alternativă | **38 trec, 1 eșuează** (același test preexistent de cale Linux), fără erorile de inițializare a unei instanțe noi; cleanup-ul callbackurilor copil este verificat |
| Capturi reale | 10 ecrane pentru fiecare configurație: 1440×900 la 100%, 1100×700, 1800×1125 la 125% Tk și 2160×1350 la 150% Tk; fără erori de callback |
| Ecrane inspectate | Astăzi, proiect/subtaskuri, inspector, Calendar, Asistent, Setări, AI, E-mail, Mailuri de analizat, Dashboard; inspector și dialoguri verificate și la scalare simulată |
| Modificări nesalvate și fluxuri AI/Outlook | Păstrate; testele UI existente trec, cu excepția eșecului preexistent de cale externă Linux |
| Windows DPI / Outlook real | **Neexecutate**; Tk/Xvfb Linux nu certifică DPI Windows, High Contrast sau monitoare cu DPI diferit |

Capturile sunt imagini reale din aplicație, într-un workspace demonstrativ temporar,
nu mockup-uri: [galerie și instrucțiuni](INTERFATA.md), [manifest](capturi-ui/manifest.json).
Fontul sans disponibil și rasterizarea X11 diferă de Segoe UI Windows; fallback-ul
unor semne tipografice este limitat. Pictogramele principale sunt PNG locale originale
cu licență MIT, la șase dimensiuni; nicio resursă UI nu se descarcă la utilizare.
Nu s-au modificat schema workspace-ului, logica Planner sau calculele timpului lucrat.


## Productivitate AI: e-mail, zi și raport — 2026-10-26

Implementată pe aceeași ramură, folosind motorul și validarea comună a propunerilor.

| Verificare executată | Rezultat |
|---|---|
| 13 teste noi | Trec: lipsa datelor, cifre actual_seconds fără rollup dublu, fus/zi, finalizări, surse învechite, maximum trei priorități, taskuri neestimate, dependențe blocate, plan fără suprapuneri, ciornă editabilă, raport fără AI, anulare și absența trimiterii/salvării automate |
| Smoke real `scripts/smoke_productivity.py --mode all` | **GGUF Qwen3 real pe CPU**, proces spawn, trei operații în același motor, fără Outlook |
| Ciornă reală | Propunere email validată, 1409 tokeni prompt + 253 răspuns, 3 surse |
| Selecția zilei reală | Un task selectat cu sursă validată, 923 tokeni prompt + 127 răspuns; fără intervale calculate de AI |
| Raport real | Explicație validată pe totalurile calculate în cod, 1211 tokeni prompt + 202 răspuns, 2 surse |
| Efecte ale smoke-ului | Zero acțiuni aplicate, zero mailuri trimise; numai date de test într-un workspace temporar |
| Suita completă după extensie | **259 trec, 14 eșuează, 1 omis**; aceleași 14 eșecuri preexistente de căi Windows pe Linux; baseline anterior 246/14/1 |

Mediu: Linux, Python 3.12, llama-cpp-python 0.3.36, GGUF din manifest, UI Tk cu Xvfb.
Cifrele din smoke descriu exemplele executate, nu garantează calitatea oricărei redactări.
Validarea numerică și a surselor nu dovedește corectitudinea semantică a fiecărei fraze;
previzualizarea editabilă și confirmarea utilizatorului rămân obligatorii.
Nu au fost executate trimitere reală Outlook, sincronizare Windows sau build Windows
nou pentru această extensie. Rezervările personale de timp rămân distincte de întâlniri
cu invitați/Teams. Ghid și limite: [PRODUCTIVITATE-AI.md](PRODUCTIVITATE-AI.md).


## Monitorizare mailuri și analiză locală — 2026-10-26

Implementată pe aceeași ramură, peste ComWorker și mecanismul comun de propuneri.

| Verificare executată | Rezultat |
|---|---|
| 25 teste noi mail | Trec: prima scanare limitată, paginare/restart, dedup/mutare, ignorare/respingere persistentă, COM indisponibil/blocat, SMTP Exchange simulat, metadate atașamente, informare/cerere/răspuns, termene și citate, buget, rezultate parțiale, UI Tk |
| Smoke `scripts/smoke_mail.py` | **GGUF real CPU**, transport **Outlook fals** prin ComWorker; clasificare `request`, o propunere validată, 977 tokeni prompt + 132 răspuns; zero taskuri create, zero mailuri trimise |
| Suita completă | **246 trec, 14 eșuează, 1 omis**; aceleași 14 eșecuri preexistente de căi Windows pe Linux; baseline anterior 221/14/1 |
| Outlook Classic real / build Windows pentru extensia mail | **Neexecutate** în mediul Linux |

Nu se declară verificată citirea inboxului pe Outlook real. Testele native COM
folosesc obiecte simulate, distinct de inferența GGUF reală. Checklist-ul manual
Windows și limitele de identitate, paginare și timeout sunt în [MAILURI.md](MAILURI.md).
Un apel COM blocat rămâne neîntrerupt până răspunde; workerul refuză suprapunerea.


## Extensie Asistent conversațional — 2026-10-26

Implementată pe aceeași ramură, peste motorul local existent. Mediu executat: **Linux x86_64,
CPython 3.12.14, llama-cpp-python 0.3.36 CPU, GGUF Qwen3 din manifest**, Tk real cu Xvfb.

| Verificare efectivă | Rezultat |
|---|---|
| **34 teste noi de asistent** | Trec: context/requester, surse/ID-uri/proprietari, buget exact cu rezervă, intenții de consultare, câmpuri interzise, cicluri, revizii, editare/respingere, replay după redeschidere, erori după scriere și rezultate parțiale |
| UI Tk real | Buton și chat fără grab modal, tab în inspector, context vizibil, recuperare în fundal, link la notița exactă, previzualizare fără aplicare, confirmare și ignorarea rezultatului după schimbarea workspace-ului |
| „Unde am rămas?” cu **model real** | Răspuns cu task și notiță citate, `1099` tokeni de intrare + `129` generați; `actions=[]`, fără aplicare |
| Subtask + checklist cu **model real** | Acțiune `create_task` validată, părinte/citări cunoscute și pași nebifați; propunere neaplicată |
| E-mail cu **model real** | Subiect/corp de ciornă și surse validate; fără trimitere sau apel Outlook |
| Build PyInstaller **onedir Linux** pentru extensie | Reușit |
| Asistent în executabil cu **PATH gol**, model real | Răspuns valid cu surse: `1109` tokeni de intrare + `86` generați; proces spawn, fără Python extern și fără aplicări |
| Propunere structurată în executabil cu **PATH gol**, model real | Subtask/checklist validat: `1104` tokeni de intrare + `194` generați, aproximativ `88,7 s`; fără aplicare |
| Suita completă după extensie | **221 trec, 14 eșuează, 1 omis** |

Intrările reale de mai sus au respectat limita de 4096 tokeni inclusiv rezerva explicită de 1024
și marja de 16. Testul cu tokenizer conservator și multe surse verifică și eliminarea istoricului/surselor
când bugetul nu încape. Cifrele observate nu reprezintă o garanție de timp de răspuns pe alt procesor.

Aplicarea este verificată în teste pe workspace-uri temporare reale: aceeași propunere nu se repetă
după redeschidere, o scriere urmată de eroare rămâne incertă, un receipt `started` blochează replay,
iar un istoric ilizibil la mijlocul lotului nu pierde rezultatele deja aplicate. Actualizările proprii de
revizie/progres/blocaje dintr-un lot nu produc conflicte false pentru operația următoare.

Cele **14 eșecuri** sunt cele preexistente de validare a căilor Windows pe Linux, enumerate în secțiunea
motorului de mai jos. Baseline-ul înaintea acestei extensii era **187 trecute, 14 eșuate, 1 omis**;
cele 34 de teste noi trec. Așteptarea testului care enumera taburile inspectorului a fost actualizată
pentru tabul Asistent cerut; validarea căilor și testele aferente nu au fost relaxate.

**Nu s-au executat în această extensie:** build/exe Windows, un nou build onefile, Outlook COM real sau
trimitere reală de e-mail. Build-urile onefile ale motorului din etapa anterioară sunt dovezi istorice,
nu verificarea noului chat pe Windows. Ciornele AI au fost testate până la transferul în editorul existent
cu backend/UI controlate; transportul păstrează traseul existent prin ComWorker.

Detalii funcționale, limitele căutării lexicale și protocolul de confirmare/istoric: [ASISTENT.md](ASISTENT.md).

## Actualizare AI local — 2026-10-26

Mediu executat: **Linux x86_64, CPython 3.12.14, llama-cpp-python 0.3.36 CPU**, NumPy 2.2.6,
Tk 9 cu Xvfb. Testele Windows istorice de mai jos nu reprezintă verificarea acestei integrări AI pe Windows.

| Verificare efectivă | Rezultat |
|---|---|
| API Hugging Face: nume exact, revizie, dimensiune și SHA256 LFS | `Qwen3-8B-Q4_K_M.gguf`, revizie `7c41481f57cb95916b40956ab2f0b139b296d974`; manifest versionat, licență și model card de la aceeași revizie |
| Descărcare reală a unui singur GGUF, SHA256 complet înainte de redenumire | **5 027 783 488 octeți**, hash `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785`; fișier local ignorat de Git |
| Repetarea downloader-ului cu fișier final valid | Reutilizat după verificare, fără o nouă descărcare |
| **38 teste AI**: proces real cu backend fals, crash, timeout, anulare, copil care nu citește Pipe, reutilizare și cleanup, callback tardiv, validare semantică, HTTP simulat, template/gramatică, UI Tk real | **38 trec**; recuperarea download-ului întrerupt este testată cu fluxuri simulate, nu prin întreruperea intenționată a transferului de 5 GB |
| Smoke **real din surse**, proces spawn, template Qwen3 fără thinking, gramatică JSON și Pydantic | **Trece**, răspuns `Salut!`, aproximativ **21,11 s**, inclusiv verificarea și încărcarea modelului |
| Build PyInstaller **onedir Linux**, apoi executabil cu `PATH` gol și GGUF real | **Trece**, spawn + încărcare + inferență, aproximativ **27,57 s** |
| Build PyInstaller **onefile Linux**, apoi executabil cu `PATH` gol și GGUF real extern | **Trece**, spawn + încărcare + inferență, aproximativ **22,20 s** |
| Executabil fără model, cu `PATH` gol | Eroare controlată și ieșire curată, fără buclă de pornire a aplicației |
| Suita completă actualizată, inclusiv AI | **187 trec, 14 eșuează, 1 omis** |
| Integritatea dependențelor | `pip check` trece |

Cele **14 eșecuri** sunt aceleași ca înaintea modificărilor AI: `validate_external_path` folosește
`PureWindowsPath.is_absolute()` și respinge căi Linux. Afectează fișiere externe/checkpoint-uri,
scheduler și fluxul UI fișiere/checkpoint. Baseline-ul măsurat înaintea modificărilor era
**149 trecute, 14 eșuate, 1 omis**; toate cele 38 de teste adăugate trec. Testul omis cere junction Windows.
Nu s-a modificat validarea de căi sau testele existente pentru a masca aceste rezultate.

Smoke-ul real a detectat o incompatibilitate a parserului nativ cu gramatica expandată pentru
`maxLength=2000`. Corecția păstrează gramatica pentru structura/enum-urile JSON și validează limitele
de text în Pydantic, cu buget nativ de maximum 512 tokeni. Verificările reale reușite de mai sus
sunt executate după această corecție; rezultatele nu provin din mock-uri.

### Windows: verificat disponibilitatea, nu execuția

Au fost descărcate wheel-ul CPU oficial **0.3.36 Windows x64** și toate dependențele sale pentru
**CPython 3.12 x64**, numai în formă binară. SHA256-ul wheel-ului coincide cu digestul publicat de
GitHub Releases. Dovezi: `packaging/ai-windows-artifacts.json`. Importurile PE ale DLL-urilor au fost
inspectate: necesită MSVC/OpenMP, fără CUDA. Spec-ul colectează explicit runtime-urile Microsoft;
build-ul se oprește dacă nu le găsește pe mașina de build.

**Nu s-au executat aici** build-ul Windows, exe Windows pe un calculator curat, Outlook COM real,
sau verificarea tuturor procesoarelor/combinațiilor Windows. Build-urile și smoke-urile Linux nu
demonstrează aceste rezultate. `scripts/build.ps1 -ModelPath ...` împachetează modelul extern și
verifică executabilul cu `PATH` gol; `scripts/verify_ai_exe.py` permite repetarea separată a testului
pe Windows. Vezi [AI.md](AI.md) pentru instalarea exclusiv pe mașina dezvoltatorului și distribuția
cu model, licențe și DLL-uri, fără instalări AI suplimentare pentru utilizatorul final.

## Raport istoric al aplicației înainte de AI

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
