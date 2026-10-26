# Distribuție Windows x64

FocusDesk se distribuie implicit ca folder **onedir**, fără model sau motor AI.
Utilizatorul final extrage întreg folderul și pornește `FocusDesk.exe`; nu instalează
Python sau compilatoare. Outlook Classic este necesar numai pentru calendar și
compunerea/trimiterea manuală prin COM. New Outlook nu oferă COM.

## Workflow GitHub Actions

1. Deschide repository-ul → **Actions → FocusDesk Windows x64**.
2. Apasă **Run workflow**, selectează ramura `main` și confirmă **Run workflow**.
3. Așteaptă jobul `windows` să se încheie cu succes. Rulează numai manual.
4. Deschide rularea și descarcă artifactul **FocusDesk-Windows-x64**.
5. Extrage ZIP-ul artifactului, apoi `FocusDesk-Windows-x64.zip` din interior.
6. Păstrează tot folderul `FocusDesk`: `FocusDesk.exe`, `_internal`, `licenses`,
   `build-info.json`, `CITESTE-MA.txt`. Pornește executabilul din folderul extras.

Artifactul include și `.zip.sha256`. Verificare opțională în PowerShell:

```powershell
Get-FileHash .\FocusDesk-Windows-x64.zip -Algorithm SHA256
Get-Content .\FocusDesk-Windows-x64.zip.sha256
```

Workflow-ul folosește Windows x64, Python **3.12.10 x64**, dependențe exact fixate și
hash-uri de wheel verificate înainte de instalare. Rulează testele, construiește
onedir, verifică EXE cu PATH gol pe date temporare, apoi auditează și arhivează numai
fișierele distribuției. Nu există download/cache/artifact pentru modele.
Artifactele sunt păstrate 7 zile; disponibilitatea depinde de cota/stocarea contului
GitHub Actions. Nu se publică automat GitHub Release.

**Configurația curentă nu a fost rulată pentru a construi un executabil în această
etapă.** Un succes al unei distribuții istorice nu validează această revizie.

## Build local pentru dezvoltatori

Din sursele extrase, într-un mediu Windows autorizat:

```powershell
py -3.12 -m venv .build-venv
$py = (Resolve-Path .build-venv\Scripts\python.exe).Path
& $py -m pip download --only-binary=:all: -r packaging/requirements-windows.lock --dest .wheelhouse
& $py scripts/verify_windows_wheels.py .wheelhouse
& $py -m pip install --no-index --no-deps --find-links .wheelhouse -r packaging/requirements-windows.lock
& $py -m pip install --no-deps --no-build-isolation -e .
& $py -m pip check
.\scripts\build.ps1 -Python $py
```

Acest mediu este necesar numai dezvoltatorului. Git nu este obligatoriu pentru un
build din ZIP-ul surselor. Rezultatul implicit:
`%LOCALAPPDATA%\focusdesk-build\dist\FocusDesk\FocusDesk.exe`.
`-OutDir` schimbă directorul rezultatului. `-OneFile` este opțional; distribuția
workflow-ului rămâne onedir. Nu copia workspace-uri sau configurații în pachet.
Spec-ul exclude explicit bibliotecile AI rămase eventual instalate în mediul local.
Licențele provin numai din dependențele declarate și din bundler, nu din toate
pachetele instalate pe calculatorul dezvoltatorului.

## Verificare locală

```powershell
& $py -m pytest -q
& $py -m focusdesk --smoke-test
& $py scripts/verify_distribution.py --exe "$env:LOCALAPPDATA\focusdesk-build\dist\FocusDesk\FocusDesk.exe" --reports "$env:TEMP\focusdesk-reports"
```

Smoke-ul folosește exclusiv configurație și workspace temporare, verifică pornirea
Tk, crearea proiect/task/subtask, notiță și sesiune, navigarea, închiderea și
redeschiderea datelor, plus compatibilitatea cheilor vechi. Verificatorul EXE
pornește aplicația cu PATH gol (acceptă doar directorul DLL privat adăugat de
PyInstaller) și fără PYTHONHOME/PYTHONPATH/VIRTUAL_ENV. Nu necesită Outlook și nu
trimite mesaje. Nu folosește model sau inferență.

Verificare manuală pe calculatorul țintă: fără Python instalat, pornire și salvare,
resurse/pictograme, redeschidere, timer/checkpoint, calendar și e-mail Outlook Classic
într-un mediu de test. Vezi [diagnosticul integrărilor](diagnostic-integrari.md).
Executabilul nu este semnat digital: politicile firmei pot cere aprobarea IT.

## Actualizare și date

Închide aplicația, extrage versiunea nouă într-un folder separat și deschide
workspace-ul existent. Nu înlocui folderul datelor. Setările sunt în
`%APPDATA%\FocusDesk`, separat de executabil. Taskurile, notițele și sesiunile create
anterior prin AI rămân date normale. Setările vechi sunt acceptate, iar cache-ul
istoric de analiză a mailurilor rămâne neutilizat pe disc, fără curățare automată.
