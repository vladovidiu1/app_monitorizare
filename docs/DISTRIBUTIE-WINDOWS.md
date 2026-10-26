# Distribuție Windows x64 cu AI și model

Workflow manual: **Actions → FocusDesk Windows x64 cu model → Run workflow**.
Alege ramura `main`, lasă bifată opțiunea pentru pachetul mic dacă dorești și apasă
**Run workflow**. Nu sunt necesare secrete Hugging Face sau date Outlook.

Workflow-ul folosește Windows 2025 x64 și CPython 3.12.10, cu versiunile exacte din
`packaging/requirements-windows.lock`. Cele 32 de wheel-uri Windows au fost descărcate
și SHA256-urile lor sunt fixate în `packaging/windows-wheels.json`; se verifică înainte
de instalare. Nu se compilează llama.cpp și nu se instalează CUDA. Acțiunile GitHub
sunt fixate la commituri, nu doar la taguri mobile.

## Descărcare și pornire

1. Așteaptă finalizarea **cu succes** a jobului Windows, inclusiv smoke-ul GGUF real.
2. Deschide rularea și secțiunea **Artifacts**. Descarcă
   **FocusDesk-Windows-x64-cu-model**. Artifactul complet este păstrat o zi; descarcă-l
   înainte de expirare sau pornește din nou workflow-ul.
3. Dezarhivează artifactul GitHub (container de transport). În interior găsești
   `FocusDesk-Windows-x64-cu-model.zip` și checksum-ul `.sha256`.
4. Dezarhivează acest **ZIP64**, cu Windows Explorer sau 7-Zip actual, într-un folder
   local. Nu folosi un dezarhivator vechi cu limita de 4 GB sau `Expand-Archive` vechi
   care are limitări pentru intrări foarte mari.
5. Deschide folderul `FocusDesk` și pornește **FocusDesk.exe**. Nu muta doar EXE-ul:
   `_internal/`, `models/` și `licenses/` fac parte din distribuție.
6. Creează/alege un workspace separat. În Setări → AI activează motorul local;
   calea implicită este `models/Qwen3-8B-Q4_K_M.gguf` lângă executabil.

Structură:

```text
FocusDesk/
  FocusDesk.exe
  _internal/               # Python și DLL-urile incluse, fără instalare separată
  models/Qwen3-8B-Q4_K_M.gguf
  licenses/                # Qwen Apache-2.0, biblioteci, Python, runtime MSVC, iconuri MIT
  build-info.json
  CITESTE-MA.txt
```

Modelul are **5.027.783.488 octeți**, peste limita de 4 GiB a ZIP clasic. Pachetul
folosește explicit ZIP64, cu CRC verificat după scriere și SHA256 al întregii arhive.
Checksum local:

```powershell
Get-FileHash .\FocusDesk-Windows-x64-cu-model.zip -Algorithm SHA256
```

Nu instalezi Python, Ollama, LM Studio, compilatoare sau server AI. Inferența este
CPU; pentru modelul 8B se recomandă 12–16 GB RAM liberă. Outlook Classic este necesar
numai pentru integrarea COM; lipsa lui nu blochează organizatorul sau AI. New Outlook
nu este considerat furnizor COM. După descărcare aplicația și AI funcționează local.

## Verificările obligatorii ale jobului

- Testele aplicabile întregii aplicații, cu backenduri false unde este cazul.
- Descărcarea unui singur GGUF, prin scriptul existent și manifestul versionat;
  inclusiv cache hit este reverificat SHA256 înainte de build.
- PyInstaller **onedir**, biblioteci CPU, runtime MSVC redistribuibil și resurse locale;
  modelul nu intră în EXE sau directorul temporar onefile.
- Executabilul este lansat cu **PATH gol**, fără PYTHONPATH/PYTHONHOME și cu profil
  temporar; CLI-ul de diagnostic izolează suplimentar propriul profil și workspace.
- Firewall Windows blochează traficul outbound al EXE-ului, inclusiv al procesului
  copil identic. Se cere succesul inferenței cu **modelul GGUF real**, nu un mock.
- O propunere reală de subtask este validată și aplicată prin mecanismul comun,
  exclusiv în workspace-ul temporar creat de diagnostic.
- Lipsa modelului produce eroare controlată; UI rămâne editabil. Outlook este
  dezactivat și nu este necesar pentru aceste verificări.
- Închiderea aplicației oprește supervisorul și procesul AI copil. Datele salvate se
  redeschid și setările temporare își păstrează câmpurile.
- Auditul pachetului admite numai EXE, `_internal`, modele verificate, licențe și
  informațiile de build. Nu sunt împachetate workspace-uri, `app.json`, mailuri,
  credențiale sau configurația mașinii de build.

Rapoartele JSON și JUnit se publică separat în
**FocusDesk-Windows-x64-verificari**, inclusiv la eșec. Un artifact de distribuție
este publicat numai după verificări reușite. Testarea Outlook Classic real rămâne
**manuală**: [MAILURI.md](MAILURI.md) și [diagnostic-integrari.md](diagnostic-integrari.md).

## Actualizări

Artifactul opțional **FocusDesk-Windows-x64-fara-model** conține aceeași aplicație,
cu toate funcțiile AI, dar exclude GGUF-ul. Închide FocusDesk, extrage într-un folder
nou și păstrează/copierează `models/` din versiunea anterioară sau selectează calea
modelului în Setări. Redeschide workspace-ul existent. Datele nu sunt în EXE sau în
pachet; preferințele sunt în `%APPDATA%\FocusDesk`. Nu există un installer/updater
care șterge workspace-ul sau setările.

## Build și test local pentru dezvoltatori

Pe o mașină Windows x64 cu Python 3.12.10, runtime-ul redistribuibil MSVC pe hostul de
build și Git:

```powershell
python -m venv .build-venv
$py = (Resolve-Path .build-venv\Scripts\python.exe).Path
& $py -m pip download --only-binary=:all: -r packaging/requirements-windows.lock --dest .wheelhouse
& $py scripts/verify_windows_wheels.py .wheelhouse
& $py -m pip install --no-index --no-deps --find-links .wheelhouse -r packaging/requirements-windows.lock
& $py -m pip install --no-deps --no-build-isolation -e .
& $py scripts/download_model.py --directory models
.\scripts\build.ps1 -Python $py -OutDir D:\FocusDeskBuild -ModelPath (Resolve-Path models\Qwen3-8B-Q4_K_M.gguf)
& $py scripts/package_windows.py --bundle D:\FocusDeskBuild\dist\FocusDesk --output D:\FocusDeskPackages --with-update
```

Build-ul local cu model rulează diagnosticul executabilului; pentru verificarea
fără rețea la nivelul sistemului folosește și regula firewall din workflow, într-un
PowerShell cu drepturile necesare. Diagnosticul este disponibil separat:

```powershell
& $py scripts/verify_distribution.py --exe D:\FocusDeskBuild\dist\FocusDesk\FocusDesk.exe --reports D:\FocusDeskBuild\reports
```

`-LinkModel` este opțional și necesită modelul și build-ul pe același volum NTFS.
CI folosește hardlink pentru a evita două copii fizice de 5 GB; zip-ul rămâne complet
independent de cache. `-SkipSmoke` este folosit doar de workflow înaintea smoke-ului
separat cu firewall. Nu trebuie interpretat drept verificare reușită.

## Limitele GitHub verificate la 2026-10-26

Documentația oficială curentă a fost consultată inclusiv prin sursele sale versionate:

- [Runnere standard](https://docs.github.com/en/actions/reference/runners/github-hosted-runners):
  Windows x64 standard are 14 GB SSD; în repository-uri private tabelul curent indică
  8 GB RAM, iar publice 16 GB. Discul efectiv liber poate fi mai mic. Jobul verifică
  spațiul înainte de model și înainte de arhivare și nu presupune capacitate nelimitată.
- [Cache](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching):
  allowance inclus de 10 GB/repository, separat de artifacts. Cache-ul nostru este
  legat de revizia exactă și SHA256, fără fallback la alte modele/revizii. Revizii
  multiple pot provoca evacuare sau pot depăși limita configurată.
- [Stocare Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions):
  Free include 500 MB pentru artifacts, Pro 1 GB, Team 2 GB, Enterprise 50 GB; această
  stocare este partajată cu Packages. Pachetul complet de circa 5 GB depășește cota
  inclusă a unor planuri. Este necesară capacitate/buget disponibil în cont; nu se
  modifică automat billing-ul. Retenția de o zi limitează acumularea, nu anulează
  consumul deja înregistrat. Publicarea poate fi refuzată de cotă/buget.
- [Upload artifact](https://github.com/actions/upload-artifact): limita documentată
  este 500 artifacts/job; aici sunt cel mult trei. Nu este documentată acolo o
  limită universală fixă per artifact care să înlocuiască cota contului. ZIP64
  rezolvă formatul fișierului, nu cota de stocare.
- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases):
  un asset individual trebuie să fie **sub 2 GiB**. Acest pachet nu este publicat ca
  asset Release unic. Workflow-ul folosește Actions artifacts, fără release automat.

Măsurarea spațiului, mărimile pachetelor și concluzia fiecărui test sunt în logul
rulării. Starea construcției efective, inclusiv orice blocaj de acces sau cotă, este
consemnată în [RAPORT.md](RAPORT.md). Nu se declară verificat Windows numai pe baza
unui test Linux sau a backendurilor false.
