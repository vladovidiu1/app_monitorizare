# Verificarea integrată FocusDesk

Validare pe date temporare, în Linux/Xvfb. Baseline: `7708de22ed9fcc61b2cd60077915145dcdfa566e`. Nu s-au folosit date reale.

## Rezultat și corecții

Etapele sunt integrate: indexuri locale și încărcare la cerere, dashboard/calendar/export cu calcul comun, ghid pentru descriere în bufferul PeerText, redeschidere și cerințe ulterioare independente, timer unic și întâlniri cu notițe/acțiuni.

Verificarea a găsit și remediat punctual două probleme de UI: butoanele listei întâlnirilor puteau ieși sub fereastra minimă, iar un eveniment întârziat din lista ascunsă de taskuri putea readuce inspectorul peste Activitate. Footerul are acum spațiu rezervat, iar selecțiile listei sunt procesate numai în ruta căreia îi aparțin. Ambele cazuri au teste de regresie.

Importul întâlnirilor folosește ComWorker pentru citire și aplicare locală progresivă; schimbarea workspace-ului oprește loturile rămase înaintea eliberării lockului. A fost remediat și cazul în care un checkpoint, backup sau o copiere de fundal putea continua după eliberarea workspace-ului. Schimbarea/închiderea așteaptă în mod neblocant terminarea operației locale și a callbackului său de înregistrare, inclusiv dacă încheierea sesiunii tocmai a lansat un checkpoint. Interfața rămâne utilizabilă; comanda de schimbare poate fi repetată după terminare. Corecțiile pentru timer, conflicte externe, dialoguri și idempotenta operațiilor sunt incluse în suita finală.

## Fluxuri parcurse

`tests/test_integrated_workflow.py` parcurge într-un singur workspace: ghid → salvare → buffer comun → anulare extinsă; rezervare fără start automat → start explicit → alt task în pauză → anulare/schimbare cu rezumat → restart/recuperare fără interval offline; corecție → dashboard/agregate/export; finalizare → filtrul Finalizate → redeschidere → refinalizare → cerință nouă cu cod managed comun și timp propriu; import repetat/modificat → autosalvare efectivă cu debounce → acțiune → task → navigare bidirecțională; întrerupere/retry → eliminarea indexurilor → reconstruire → backup complet/restaurare.

Testele existente și cele noi acoperă suplimentar părinți/subtaskuri fără dublarea duratelor, lanțuri/cicluri, read-only și a doua instanță, arhivare/coș/restaurare, scrieri eșuate, conflicte externe, recuperare la etapele intermediare, DST/miezul nopții, rezultate COM întârziate/parțiale, note păstrate la import și istoric mare fără citirea tuturor Markdown-urilor.

## Verificări executate

- Suita completă: **473 passed, 1 skipped**, 36,38 s în rularea finală înregistrată; omis este testul de junction specific Windows.
- Smoke test GUI: exit 0, `status=ok`, workspace și setări păstrate, spațiul taskului verificat.
- `compileall`, `pip check`, `git diff --check`: reușite.
- Revizuire statică în `src`, `pyproject.toml`, `packaging`: fără introducerea sqlite3, SQLAlchemy, psycopg, pymysql, DuckDB sau instrucțiuni SQL de stocare.
- Tk real la minimum 1100×700 logic și scalare 100%/125%/150%: **45 verificări de geometrie**; timer activ și comenzi în Concentrare, editor, salvare, footer, export și filtre. Au fost parcurse Enter, Ctrl+S, Undo/Redo, anularea editorului, titluri/acțiuni lungi, 70 de proiecte, lipsă date și eroare de salvare cu ciornă păstrată.

Capturi și rezultate geometrice: [100%](capturi-ui/integrare/ui-100.json), [125%](capturi-ui/integrare/ui-125.json), [150%](capturi-ui/integrare/ui-150.json). Exemple: [task și timer la 150%](capturi-ui/integrare/integrare-task-150.png), [Activitate la 125%](capturi-ui/integrare/integrare-activitate-125.png), [întâlnire la 150%](capturi-ui/integrare/integrare-intalnire-150.png).

## Benchmark înainte/după

Rulări secvențiale, în procese noi, același script și același tip de date: **5.000 taskuri, 50 active (99% închise), un proiect și ierarhii, 15.000 sesiuni, 15.000 evenimente, 2.000 întâlniri cu notițe**. Generarea nu intră în timpi. Baseline-ul a fost extras separat cu git archive, fără resetarea checkoutului. Cache-ul OS nu a fost golit; „prima deschidere” înseamnă prima construire a indexurilor aplicației pentru datele generate, nu un disc rece fizic.

Baseline-ul nu are pagina Întâlniri și nu citește datele ei; același fixture include fișierele, dar funcționalitatea suplimentară consumă memorie numai în versiunea finală. Dashboardul final calculează și finalizările din istoricul done, indicator absent din raportul vechi. Valorile sunt probe punctuale per mod, nu mediane statistice. Măsurătorile includ tracemalloc, citiri și așteptarea randării progresive; nu reprezintă latențe native Windows.

### Prima deschidere / construire indexuri

| Operație | Înainte (ms) | Final (ms) | Deschideri pentru citire: înainte → final | MiB citiți: înainte → final |
|---|---:|---:|---:|---:|
| Deschidere workspace | 12634.24 | 12353.83 | 20003 → 24004 | 19.676 → 20.899 |
| Navigare: 4 ecrane | 19467.02 | 284.93 | 75000 → 84 | 79.536 → 0.091 |
| Selectare task | 10264.70 | 18.32 | 45001 → 1 | 34.978 → 0.002 |
| Salvare titlu | 619.39 | 2.69 | 1 → 1 | 0.001 → 0.001 |
| Refresh după salvare | 42578.03 | 45.61 | 120004 → 1 | 101.772 → 0.002 |
| Căutare globală | 744.36 | 784.29 | 5000 → 5000 | 11.060 → 11.060 |
| Activitate | 3970.24 | 8018.03 | 15000 → 15001 | 15.907 → 3.162 |

Vârf memorie Python: **113.17 → 115.32 MiB**. RSS maxim: **266.04 → 326.93 MiB**.

Listă întâlniri (prima pagină, filtrare globală): **58.35 ms**, 0 deschideri pentru citire, 0.000 MiB. Fără echivalent în baseline.
Deschidere notițe pentru o întâlnire: **13.92 ms**, 4 deschideri pentru citire, 0.011 MiB. Fără echivalent în baseline.

### Proces nou, indexuri păstrate

| Operație | Înainte (ms) | Final (ms) | Deschideri pentru citire: înainte → final | MiB citiți: înainte → final |
|---|---:|---:|---:|---:|
| Deschidere workspace | 12349.66 | 6319.41 | 20003 → 6 | 19.676 → 12.185 |
| Navigare: 4 ecrane | 19151.19 | 389.33 | 75000 → 84 | 79.536 → 0.091 |
| Selectare task | 10309.40 | 36.90 | 45002 → 2 | 34.978 → 0.003 |
| Salvare titlu | 607.20 | 1.64 | 1 → 1 | 0.001 → 0.001 |
| Refresh după salvare | 43603.38 | 91.92 | 120004 → 1 | 101.772 → 0.002 |
| Căutare globală | 787.18 | 802.87 | 5000 → 5000 | 11.060 → 11.060 |
| Activitate | 4326.06 | 2512.40 | 15000 → 1 | 15.907 → 5.022 |

Vârf memorie Python: **113.24 → 121.75 MiB**. RSS maxim: **265.76 → 338.57 MiB**.

Listă întâlniri (prima pagină, filtrare globală): **133.14 ms**, 0 deschideri pentru citire, 0.000 MiB. Fără echivalent în baseline.
Deschidere notițe pentru o întâlnire: **13.19 ms**, 4 deschideri pentru citire, 0.011 MiB. Fără echivalent în baseline.

Totaluri identice înainte/după: **1.058.400 secunde lucrate și 2.116.800 secunde programate**. Întâlnirile nu adaugă timp lucrat/programat de sesiune. În listarea celor 2.000 de întâlniri nu s-a deschis niciun Markdown; la deschiderea uneia sunt citite numai datele acelei întâlniri.

Date brute: [baseline](benchmarks/review-before-5000-2000.json), [final](benchmarks/review-final-5000-2000.json). Reproducere: `xvfb-run -a python scripts/benchmark_performance.py --tasks 5000 --meetings 2000 --output <json>`. Pentru baseline: PYTHONPATH către `src` extras din commitul indicat. Capturi/verificări: `xvfb-run -a python scripts/verify_integrated_ui.py --scale 1.25 --output <folder>` (Pillow opțional pentru capturi).

## Confirmări și limite

- **Fără SQL/SQLite**; datele autoritare rămân JSON/Markdown și directoare locale. Cache-urile sunt reconstructibile.
- Navigarea curentă și selecția nu citesc întregul istoric sau toate notițele. Prima construire a unui index absent trebuie să citească metadatele autoritare ale catalogului. Căutarea globală păstrează căutarea în descrieri, inclusiv închise: prima căutare completă poate citi toate descrierile. Nu o prezentăm drept operație fără scanare.
- Finalizatele rămân căutabile/filtrabile; redeschiderea actualizează imediat setul activ, fără ștergerea muncii sau istoricului. Rapoartele includ sesiunile istorice ale acestora.
- Maximum un timer curent, inclusiv în pauză. Programat, lucrat salvat, live nesalvat și contextul întâlnirilor sunt distincte. Nu se inventează lucru în intervalul offline.
- Nu s-au reintrodus bara Bold/Italic sau filele Editare/Previzualizare. Ghidul modifică numai bufferul comun până la salvarea explicită.
- Cerințele ulterioare sunt taskuri independente, nu reveniri programate sau recurențe. Codul comun este preluat numai explicit.
- Actualizarea calendarului nu scrie notițele locale. Operațiile compuse, inclusiv crearea și legarea, au retry/recuperare fără duplicate; referințele indisponibile sunt păstrate.

**Costuri rămase măsurate:** primul Activitate fără index de istoric este mai lent (8.018,03 ms față de 3.970,24 ms), deoarece construiește și indexul necesar finalizărilor istorice. Cu index păstrat este 2.512,40 ms față de 4.326,06 ms. Memoria este mai mare în această probă extinsă: RSS 338,57 MiB față de 265,76 MiB la proces nou/indexuri păstrate; nu pretindem reducerea ei. Pornirea și reconstrucția rămân proporționale cu inventarul de fișiere/metadate. Nu s-au măsurat rezidența după garbage collection, latențe pe disc Windows sau pornire cu page cache OS golit.

**Outlook:** importurile, recurențele/excepțiile, erorile, anulările și workerul au fost verificate cu backend fals. Nu s-a executat integrare Outlook Classic reală, monitor DPI Windows real, build PyInstaller, release sau merge. Scalarea este Tk în Linux/Xvfb. Verificările necesare pe profilul Outlook real și limitele proprietăților MAPI sunt separate în [INTALNIRI.md](INTALNIRI.md).
