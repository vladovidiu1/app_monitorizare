# AI local în FocusDesk

AI este opțional și dezactivat inițial. Aplicația pornește fără model și fără biblioteca nativă.
Inferența este directă prin **llama-cpp-python 0.3.36**, pe CPU (`n_gpu_layers=0`), într-un proces
`multiprocessing` cu metoda **spawn**. Nu există server HTTP, Ollama, LM Studio sau Docker.

## Utilizare

**Asistentul extins** se deschide din butonul **Asistent** sau tabul omonim din inspector:
chat nemodal, context task/proiect/workspace, surse navigabile, pași, rezumate, căutare după solicitant
și ciorne e-mail. Propunerile multiple au revizuire, editare, respingere, istoric persistent și protecție
la aplicare repetată. Fluxul complet și limitele sunt descrise în [ASISTENT.md](ASISTENT.md).

În **Instrumente → Setări → AI**: activează AI, alege GGUF-ul, contextul (implicit 4096 tokeni),
firele CPU (implicit 4) și timeout-ul (implicit 180 secunde). „Testează modelul” verifică întregul
SHA256, încarcă modelul și generează un răspuns scurt fără să scrie în workspace. Testul folosește
valorile vizibile, inclusiv înainte de salvare. „Anulează testul” oprește procesul nativ.
„Oprește motorul” eliberează și modelul păstrat în memorie între cereri.

Din **Instrumente → AI local — propuneri…**, selectează un nod și cere un subtask, o notiță sau
următorul pas. Se transmite numai titlul, descrierea limitată și următorul pas al acelui nod,
plus cererea tastată. Nu sunt citite atașamentele, e-mailurile sau alte fișiere. Contextul și
răspunsurile rămân locale. Motorul nu are acces la obiectul Workspace sau la operații Outlook.

Rezultatul este o **propunere**: verifică textul și folosește „Aplică propunerea…”, cu confirmare.
Ținta este fixată de aplicație, nu aleasă de model. O propunere expiră dacă nodul/descrierea
s-au schimbat, inclusiv prin editare externă. Fiecare propunere este o operație separată;
chatul poate grupa operații cu rezultate raportate individual. Operațiile
nu pot executa shell, trimite e-mail sau modifica arbitrar căi, ID-uri ori alte câmpuri.
JSON valid nu garantează adevărul sau utilitatea propunerii; judecata utilizatorului rămâne necesară.

Prima încărcare și inferența 8B pe CPU pot dura. Pentru modelul de aproximativ 5 GB, sunt
recomandați minimum 12–16 GB RAM disponibili; consumul crește cu contextul. Anularea și timeout-ul
opresc forțat procesul în timpul încărcării/inferenței; următoarea cerere pornește unul nou.
În funcționare normală, același proces păstrează modelul încărcat între cereri. Închiderea aplicației
sau schimbarea configurației eliberează procesul; schimbarea workspace-ului anulează cererea activă.

## Model și manifest

Furnizor: **Qwen / Alibaba Cloud**, [Qwen/Qwen3-8B-GGUF](https://huggingface.co/Qwen/Qwen3-8B-GGUF),
licență **Apache 2.0**. Numele real, sensibil la majuscule, este **Qwen3-8B-Q4_K_M.gguf**,
nu numele cu litere mici din cererea inițială.

Manifestul versionat `src/focusdesk/resources/ai-model.json` provine din API-ul Hugging Face,
inclusiv metadatele LFS ale acelui fișier:

* revizie: `7c41481f57cb95916b40956ab2f0b139b296d974`;
* SHA256: `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785`;
* dimensiune: **5 027 783 488 octeți**.

Licența integrală și model card-ul de la aceeași revizie sunt păstrate în resources și distribuite
lângă executabil, în `licenses/`. Modelul nu a fost modificat. Șablonul din
`tests/fixtures/qwen3_chat_template.jinja` este extras din metadatele aceluiași GGUF, sub aceeași licență.

Dezvoltatorul descarcă explicit **un singur fișier**, nu repository-ul complet:

```powershell
python scripts/download_model.py
# Numai pentru actualizarea deliberată a manifestului, înainte de release și review:
python scripts/download_model.py --resolve-manifest --metadata-only
```

Scriptul arată progresul, folosește fișier `.part` asociat hash-ului, reia prin HTTP Range,
verifică SHA256 și dimensiunea, apoi redenumește atomic. Dacă serverul ignoră Range, reia de la zero,
fără a concatena greșit. Un fișier final valid este reutilizat. Un fișier existent invalid este
păstrat până când înlocuitorul este verificat. TLS și verificarea integrității rămân active.
Metadate absente/inconsistente sau un catalog fără fișierul cerut produc eroare, fără hash-uri inventate.

În surse, locația implicită este `models/` din repository (fișierele GGUF/part sunt ignorate de Git).
În executabil, este `models/` **lângă executabil**, inclusiv pentru onefile, niciodată `_MEIPASS`.
Poți selecta altă cale în Setări. Scriptul și selectorul refuză directoare din workspace sau
subdirectoarele sale, astfel încât modelul să nu intre în backupurile workspace-ului.
Nu există descărcare automată la pornire și nici descărcare din UI în această versiune.

## Build Windows fără instalări pe calculatorul utilizatorului

Configurația de build aleasă: **CPython 3.12 x64**, Windows 10/11 x64. Python 3.14 nu este necesar.
Wheel-ul CPU oficial `llama_cpp_python-0.3.36-py3-none-win_amd64.whl` și dependențele native
pentru CPython 3.12 au fost descărcate pentru verificarea disponibilității. Fișierele și SHA256-urile
sunt în `packaging/ai-windows-artifacts.json`. Marcajul `py3-none` nu elimină DLL-urile native;
wheel-ul conține llama/ggml CPU/mtmd. Importurile PE includ MSVC și OpenMP (`vcomp140.dll`).

```powershell
py -3.12 -m venv $env:LOCALAPPDATA\focusdesk-venv
$python = "$env:LOCALAPPDATA\focusdesk-venv\Scripts\python.exe"
& $python -m pip install -r requirements-ai.txt
& $python -m pip install -e ".[dev]"
& $python scripts/download_model.py
& $python scripts/smoke_ai.py
powershell -File scripts/build.ps1 -Python $python -ModelPath "$PWD\models\Qwen3-8B-Q4_K_M.gguf"
```

Pip instalează numai wheel-uri pentru AI, fără compilare accidentală sau CUDA. Mașina de build
trebuie să aibă DLL-urile Microsoft redistribuibile x64: `msvcp140`, `vcruntime140`, `vcruntime140_1`,
`vcomp140`. Spec-ul le colectează din Python/System32/PATH sau din directoarele de redistribuire
Visual Studio. `FOCUSDESK_VC_REDIST` permite o locație explicită. Build-ul se oprește dacă lipsesc;
nu produce silențios un executabil care le-ar cere utilizatorilor să instaleze separat.
Redistribuirea se face conform licenței Microsoft a uneltelor de build.

Distribuie **întregul folder onedir**, inclusiv `_internal`, `models` și `licenses`.
Opțiunea `-OneFile` produce executabilul și păstrează modelul/licențele alături. Fără `-ModelPath`,
build-ul conține motorul și poate porni, dar utilizatorul trebuie să aleagă un GGUF compatibil furnizat separat.
Niciun GGUF nu se include în executabil. Utilizatorul final nu are nevoie de Python sau unelte AI.
Scriptul de build verifică executabilul cu `PATH` gol: inferență reală când primește `-ModelPath`,
altfel numai tratarea modelului absent. Pentru verificare separată:
`python scripts/verify_ai_exe.py --exe <FocusDesk.exe> --model <GGUF>`.

## Thinking și siguranța acțiunilor

În versiunea fixată, `Llama.create_chat_completion` nu primește `enable_thinking`.
API-ul public `Jinja2ChatFormatter.__call__` transmite însă keyword-urile către template.
FocusDesk randază **template-ul din GGUF** cu `enable_thinking=False`, verifică sufixul
`<|im_start|>assistant\n<think>\n\n</think>\n\n`, apoi tokenizează cu `special=True`,
`add_bos=False` și folosește `create_completion` cu gramatică JSON. Aceasta este închiderea
thinking **în prompt**, înainte de generare, nu eliminarea textului generat.
Un template incompatibil este respins. Nu există fallback către inferență neconstrânsă.
Limitele de lungime ale textelor se validează în Pydantic după generare; ele nu sunt expandate în
gramatica nativă, deoarece conversia `maxLength=2000` produce reguli prea complexe pentru parser.
Bugetul dialogului inițial este plafonat la 512 tokeni. Chatul folosește o rezervă explicită de 1024 tokeni
și reduce sursele pe baza tokenizerului real; vezi [ASISTENT.md](ASISTENT.md).

Schema JSON Pydantic limitează forma și operația; rezultatul este apoi validat strict, verificat
semantic și comparat cu operația, identitatea workspace-ului, revizia și fingerprint-ul sursei.
Doar firul Tk aplică rezultatul, prin `Workspace`. Outlook continuă să folosească exclusiv `ComWorker`.
IPC folosește mesaje JSON limitate, versiune și UUID de cerere. Răspunsurile cu ID greșit, anulate
sau întârziate sunt respinse. Modelul, contextul nativ și Pipe-urile sunt deținute de proces/supervisor.

## Verificări

```powershell
python -m pytest -q tests/test_ai_process.py tests/test_ai_actions.py tests/test_ai_download.py tests/test_ai_runtime.py tests/test_ai_ui.py
# Smoke real, opțional; necesită GGUF-ul de mai sus:
python scripts/smoke_ai.py --timeout 300
# Aceeași cale, inclusiv bootstrap spawn, din executabilul fără consolă:
FocusDesk.exe --ai-smoke "models\Qwen3-8B-Q4_K_M.gguf" --ai-smoke-report ai-smoke.json
```

Testele cu backend fals verifică lifecycle, crash, timeout, anulare, recuperare și suprimarea
callback-urilor tardive. Testele downloader-ului folosesc fluxuri HTTP simulate; testul native
grammar/template folosește biblioteca reală, dar nu face inferență. Un model lipsă este testat
și în procesul real și în UI. Smoke-ul opțional este singurul care pretinde încărcarea GGUF și inferență reală.
Rezultatele efectiv executate și limitele platformei sunt în `docs/RAPORT.md`.
