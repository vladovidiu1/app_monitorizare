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

* Windows 10/11, Python 3.11+; build Windows reproductibil: Python 3.12.10 x64.
* Mediul recomandat în afara OneDrive (evită sincronizarea fișierelor `.venv`):

```powershell
py -3.12 -m venv $env:LOCALAPPDATA\focusdesk-venv
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe -m pip install -e ".[dev]"
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe -m focusdesk                 # pornește aplicația
& $env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe -m focusdesk --workspace C:\FocusDeskData
```

Dependențe (intervale în `pyproject.toml`, versiuni Windows fixate în `packaging/requirements-windows.lock`): ttkbootstrap, pydantic,
portalocker, tzdata, icalendar, openpyxl, pywin32 (doar Windows); dezvoltare: pytest, pyinstaller.

La prima pornire alegi un folder pentru workspace (se creează **gol**; un workspace demonstrativ se creează separat, la
cerere, din ecranul de bun venit sau din meniul Fișier). Ierarhia task-urilor nu are limită de adâncime: fiecare nod are
propriul director direct în `nodes/`, deci calea nu crește cu nivelurile. O rădăcină scurtă (de ex. `C:\FocusDeskData`) rămâne
recomandată; căile Windows de peste 259 de caractere sunt refuzate explicit.

## Executabil Windows (PyInstaller)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1            # onedir (implicit) -> %LOCALAPPDATA%\focusdesk-build\dist\FocusDesk\FocusDesk.exe
powershell -ExecutionPolicy Bypass -File scripts\build.ps1 -OneFile   # opțional: un singur .exe
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

## Interfață luminoasă FocusDesk

Tema, fonturile, paleta, dimensiunile și pictogramele locale sunt centralizate în
`ui/design.py`. Aspectul luminos se aplică inclusiv configurațiilor vechi dark.
Vezi [ghidul vizual și capturile reale](docs/INTERFATA.md) pentru layout, scalare,
reproducerea capturilor și limitele verificării Windows.

## Distribuție Windows x64

Workflow manual: **Actions → FocusDesk Windows x64 → Run workflow → main**.
Artifact: **FocusDesk-Windows-x64**, cu arhiva aplicației și SHA256. Extrage ambele
arhive și păstrează întreg folderul `FocusDesk`, inclusiv `_internal` și `licenses`.
Pornește `FocusDesk.exe`; utilizatorul final nu instalează Python.
Vezi [pașii de build și verificare](docs/DISTRIBUTIE-WINDOWS.md).
**Pentru revizia curentă nu s-a construit încă executabilul.**

## Compatibilitatea datelor existente

Funcțiile AI și monitorizarea/citirea inboxului au fost eliminate. Nu există motor,
model, chat, propuneri sau scanări de mail în fundal. Inbox-ul taskurilor rămâne.
Taskurile, subtaskurile, descrierile, checklisturile, notițele și sesiunile create
anterior rămân date obișnuite, editabile. Setările vechi sunt acceptate ca date
necunoscute, fără activarea serviciilor eliminate. Cache-ul istoric `_system/mail/`
și istoricul existent sunt lăsate pe disc; aplicația nu le curăță automat.
Outlook Classic rămâne opțional pentru calendar și e-mailul manual cu confirmare.
Evenimentele sunt rezervări personale de timp, fără invitați sau Teams.

## Statusuri și descrieri

Taskurile au pictograme locale distincte pentru fiecare status, etichete text și
redeschidere explicită. Descrierea are editor Markdown redimensionabil, fereastră
extinsă și previzualizare locală sigură; `description.md` rămâne autoritar.
Vezi [ghidul editorului și al statusurilor](docs/DESCRIERE-MARKDOWN.md).
