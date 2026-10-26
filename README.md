# FocusDesk

Organizator personal pentru proiecte, task-uri, subtask-uri, sesiuni de lucru, fișiere și versiuni de cod.
Aplicație desktop Windows (Python, **Tkinter + ttk**, aspect `ttkbootstrap`), interfața în limba română.
Datele sunt **într-un folder local ales de tine** (JSON, Markdown, fișiere, ZIP): fără SQL, fără cloud, fără server web.

Scop: să pui rapid backlog-ul în aplicație, să-l grupezi în foldere/proiecte/task-uri, să alegi realist ce faci azi,
să începi un task și să ajungi imediat la notițe, cod și fișiere, să închei sesiunea cu progresul și următorul pas
salvate și să regăsești o versiune de cod.

## Ce funcționează fără internet sau Outlook

Organizarea (ierarhie de orice adâncime: proiect › task › subtask › …, legături, dependențe, coș, arhivă, backup), „Astăzi”,
timerul de sesiuni, fișiere și VS Code, checkpoint-uri și restaurare, calendar local, planificator determinist, recurențe,
export `.ics`. **Outlook Classic (COM: calendar și e-mail din task) și Git sunt integrări opționale**; lipsa lor nu
împiedică pornirea sau editarea.

## Cerințe și rulare din surse

* Windows 10/11, Python 3.11+ pentru funcțiile de bază. Pentru AI și build-ul Windows: **Python 3.12 x64**.
* Mediul recomandat în afara OneDrive (evită sincronizarea fișierelor `.venv`):

```powershell
py -3.12 -m venv $env:LOCALAPPDATA\focusdesk-venv
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe -m pip install -e ".[dev]"
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe -m focusdesk                 # pornește aplicația
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe -m focusdesk --workspace C:\FocusDeskData
```

Dependențe (fixate în `pyproject.toml` cu intervale compatibile, verificate cu Python 3.14.6): ttkbootstrap, pydantic,
portalocker, tzdata, icalendar, pywin32 (doar Windows); dezvoltare: pytest, pyinstaller.

## AI local opțional

Motor integrat **llama-cpp-python 0.3.36**, CPU, într-un proces separat, fără Ollama, server AI sau GPU.
În **Setări › AI** activezi motorul, alegi GGUF-ul, contextul și firele CPU și testezi modelul.
**Instrumente › AI local — propuneri…** generează subtask-uri, notițe sau următorul pas, cu previzualizare
și confirmare; scrierile trec prin Workspace. Aplicația rămâne utilizabilă fără model sau motor nativ.

Butonul **Asistent** și tabul din inspector adaugă chat nemodal, context vizibil task/proiect/workspace,
„Unde am rămas?”, pași și checklist, rezumat de proiect, căutare după solicitant și ciorne e-mail.
Răspunsurile citează înregistrări navigabile. Propunerile se revizuiesc înainte/după, se pot modifica
sau respinge și au istoric persistent, detectarea conflictelor și protecție la dublă aplicare.
Vezi [docs/ASISTENT.md](docs/ASISTENT.md).

Pregătire explicită pentru dezvoltatori (nu pentru utilizatorul executabilului):

```powershell
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe -m pip install -r requirements-ai.txt
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe scripts\download_model.py
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe scripts\smoke_ai.py
```

Model: **Qwen/Qwen3-8B-GGUF / Qwen3-8B-Q4_K_M.gguf** (~5 GB), Apache 2.0, revizie și SHA256
fixate în manifestul versionat. Descărcarea arată progresul, se reia și verifică hash-ul înainte de redenumire.
În dezvoltare stă în `models/`; în distribuție, lângă executabil, în `models/`, separat de workspace și backupuri.
Utilizatorul final primește executabilul, modelul și licențele, fără Python sau instalări AI suplimentare.
Vezi [docs/AI.md](docs/AI.md) pentru build, distribuție, limite și testele efectiv disponibile.

La prima pornire alegi un folder pentru workspace (se creează **gol**; un workspace demonstrativ se creează separat, la
cerere, din ecranul de bun venit sau din meniul Fișier). Ierarhia task-urilor nu are limită de adâncime: fiecare nod are
propriul director direct în `nodes/`, deci calea nu crește cu nivelurile. O rădăcină scurtă (de ex. `C:\FocusDeskData`) rămâne
recomandată; căile Windows de peste 259 de caractere sunt refuzate explicit.

## Executabil Windows (PyInstaller)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1            # onedir (implicit) -> %LOCALAPPDATA%\focusdesk-build\dist\FocusDesk\FocusDesk.exe
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -OneFile   # opțional: un singur .exe
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -ModelPath "$PWD\models\Qwen3-8B-Q4_K_M.gguf"  # include model verificat lângă .exe
```

Utilizatorul final nu are nevoie de Python. Datele sunt
în folderul workspace-ului, iar configurația aplicației în `%APPDATA%\FocusDesk` — actualizarea executabilului nu le șterge.

## Teste

```powershell
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe -m pytest -q
```

Testele folosesc workspace-uri temporare (nu ating folderele tale) și un backend Outlook fals.
Vezi [docs/RAPORT.md](docs/RAPORT.md) pentru ce s-a verificat efectiv și ce rămâne de verificat pe calculatorul țintă.

## Documentație

* [docs/utilizare.md](docs/utilizare.md) — ghid de utilizare, scurtături, fluxul zilnic
* [docs/format-workspace.md](docs/format-workspace.md) — structura datelor, schema `node.json`, recuperare
* [docs/arhitectura.md](docs/arhitectura.md) — module, fire de execuție, decizii
* [docs/diagnostic-integrari.md](docs/diagnostic-integrari.md) — Outlook (calendar și e-mail), Git, VS Code, ICS: diagnostic și teste manuale
* [docs/AI.md](docs/AI.md) — motor local, model verificat, descărcare, build și smoke test real
* [docs/PLAN.md](docs/PLAN.md) — planul pe etape și starea fiecărei funcții

## Limite cunoscute (pe scurt)

* Integrarea Outlook COM este implementată și testată doar cu un backend fals; **trebuie verificată pe un Outlook Classic
  real**, într-un calendar de test ales explicit (vezi diagnosticul). „Salvat în Outlook” înseamnă salvare locală; aplicația
  nu confirmă sincronizarea Exchange sau prezența în Teams. New Outlook nu suportă COM: folosește exportul `.ics`.
* Trimiterea de e-mail din task folosește Outlook Classic prin COM și este **netestată pe un Outlook real** (doar cu backend
  fals); pentru o primă verificare folosește „Deschide ciorna în Outlook” sau trimite-ți ție un mesaj de test.
* Checkpoint-urile văd doar fișierele salvate pe disc, nu textul nesalvat din VS Code.
* Programarea checkpoint-urilor funcționează doar cât timp aplicația rulează.
* Drag-and-drop în arbore nu este implementat: ordinea și nivelul se schimbă din butoanele ▲▼◀▶ (Alt+→ / Alt+←) sau
  din „Mută…”.

## Mailuri de analizat

Monitorizarea opțională **Outlook Classic COM** este dezactivată implicit și are
interval inițial/plafon configurabile. Pagina separată „Mailuri de analizat” oferă
analiză locală GGUF și propuneri cu confirmare, fără modificarea mailurilor originale.
Vezi [configurare, identitate și limite](docs/MAILURI.md) și
[verificările efectiv executate](docs/RAPORT.md). New Outlook nu este suportat prin COM.

## E-mail, ziua și rapoarte cu AI

Editorul de mail oferă patru moduri de redactare AI. În Astăzi găsești
„Pregătește-mi ziua” (selecție AI, calcul Planner) și raport zilnic/săptămânal
cu cifre calculate din timpul efectiv înregistrat. Toate au previzualizare;
trimiterea și salvarea rămân explicite. Vezi [ghidul funcțiilor](docs/PRODUCTIVITATE-AI.md).
Evenimentele Outlook/ICS sunt rezervări personale de timp, fără invitați sau Teams.

## Interfață luminoasă FocusDesk

Tema, fonturile, paleta, dimensiunile și pictogramele locale sunt centralizate în
`ui/design.py`. Aspectul luminos se aplică inclusiv configurațiilor vechi dark.
Vezi [ghidul vizual și capturile reale](docs/INTERFATA.md) pentru layout, scalare,
reproducerea capturilor și limitele verificării Windows.

## Pachet Windows x64 cu AI și model inclus

În GitHub: **Actions → FocusDesk Windows x64 cu model → Run workflow → main**.
După succes, descarcă artifactul **FocusDesk-Windows-x64-cu-model** (retenție o zi).
Extrage containerul artifactului, apoi ZIP64-ul din interior și pornește
`FocusDesk/FocusDesk.exe`. Nu instalezi Python, Ollama, CUDA sau un server AI.
Modelul verificat se află în `models/` lângă executabil. Outlook Classic este opțional.

[Pași exacți, verificări, actualizări fără model și limitele de stocare](docs/DISTRIBUTIE-WINDOWS.md).
Build-ul este validat numai dacă jobul Windows și smoke-ul GGUF real au reușit;
starea efectivă este în [raport](docs/RAPORT.md).
