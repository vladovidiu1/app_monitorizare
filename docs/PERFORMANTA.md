# Performanță: stocare locală, indexuri și încărcare la cerere

**Acesta este raportul etapei inițiale. Rezultatele finale, inclusiv 2.000 de întâlniri, memoria, regresiile măsurate și suita completă de 473 teste trecute, sunt în [VERIFICARE-INTEGRATA.md](VERIFICARE-INTEGRATA.md). Cele 14 erori Linux de căi menționate mai jos au fost remediate în etapele ulterioare.**

Datele autoritare rămân `node.json`, `description.md`, sesiunile, notițele și
înregistrările de istoric JSON existente. Nu există SQL, SQLite sau servicii externe.
Finalizarea/anularea nu mută directoare și nu șterge conținut. Arhivarea este distinctă.
Redeschiderea schimbă statusul prin Workspace și actualizează imediat setul activ;
nu creează automat o revenire sau un task pentru o cerință nouă.

## Cum funcționează

- `_system/index.json` păstrează schema veche pentru compatibilitate. Nu era citit
  pentru încărcarea nodurilor; vechiul format nu conținea suficiente metadate.
- `_system/cache/nodes.json`, versiunea proprie 1, conține metadatele de navigare,
  căile relative, hashurile surselor și semnăturile fișierelor. Nu conține atașamente,
  checklisturi sau câmpuri suplimentare necunoscute. Acestea se hidratează din
  `node.json` numai când sunt cerute; serializarea/scrierea unui nod hidratează mai
  întâi modelul integral, păstrând câmpurile necunoscute.
- Fiecare RecordStore are `.cache/index.json`, versiunea proprie 1, în directorul
  său: UUID, nod proprietar, datele relevante, status, secunde efective, hash și
  semnătură. Textele notițelor, rezumatele, datele evenimentelor și detaliile de
  sincronizare nu intră în index. Indexul în memorie localizează înregistrările
  după task și status; sesiunile au și liste cronologice sortate pentru perioade.
- Interogările de calendar folosesc intervalele indexate, inclusiv sesiuni care
  încep înaintea perioadei și o traversează. Limita inferioară ține cont de durata
  maximă a sesiunilor; o sesiune neobișnuit de lungă poate lărgi setul de candidați.
- RecordStore păstrează cel mult 128 de modele complete în cache. Returnează copii
  independente: modificarea unui model în serviciu nu schimbă indexul înaintea
  unei scrieri atomice reușite.
- Totalurile sesiunilor proprii se derivă o dată per revizie a sesiunilor; agregările
  de progres/timp se păstrează până la o schimbare relevantă. Redenumirea nu
  invalidează totalurile istorice. Ierarhia, setul activ și apartenența la proiect
  au indexuri în memorie.
- Astăzi și lista obișnuită folosesc taskuri deschise; filtrul Finalizate/Închise,
  căutarea globală și istoricul rămân disponibile. Arborele păstrează un părinte
  închis ca structură pentru descendenții deschiși. Preferința existentă pentru
  afișarea finalizatelor în arbore se păstrează; implicitul pentru configurații noi
  este ascunderea lor.
- Activitate filtrează sesiunile după perioada planificată **sau** data muncii
  efective, înainte să încarce detaliile. Include munca taskurilor finalizate,
  anulate sau arhivate și păstrează semantica totalurilor anterioare.

## Consistență, recuperare și modificări externe

Datele autoritare se salvează imediat, cu mecanismul atomic și verificările de
conflict existente. Înaintea primei scrieri după checkpoint se persistă atomic un
marker `dirty.json` pentru RecordStore, respectiv `nodes-dirty.json` pentru noduri.
Indexurile în memorie se schimbă după succesul scrierii. Checkpointul compact JSON
se face la închidere/reconciliere; nu se rescrie întregul catalog la fiecare câmp.
Operațiile recuperabile marchează catalogul înaintea mutărilor/patchurilor. Timerul,
calendarul, recurențele și recuperarea folosesc aceleași RecordStore/repository.

La deschiderea nodurilor și la prima utilizare a unui RecordStore se verifică
schema, amprenta indexului și inventarul surselor. Se compară pentru fișiere
`mtime_ns`, dimensiunea și `ctime_ns`; doar sursele noi/modificate sunt recitite.
Inventarul detectează și intrările omise, adăugate sau șterse. Indexul lipsă,
corupt, incomplet sau cu marker de scriere întreruptă se reconstruiește din surse.
Prima construire poate citi toate sursele acelui catalog; conținutul greu nu se
păstrează integral în memorie. Un istoric vechi fără index are acest cost o singură
dată la prima cerere. În navigarea ulterioară nu se rescanează fiecare catalog la
fiecare click.

Editările externe ale unui fișier deschis sunt verificate și prin hash înainte de
suprascriere/ștergere. Nu există polling care să citească tot istoricul la fiecare
click. Pentru modificări externe noi, folosește **F5** sau Reîncarcă de pe disc.
F5 reîncarcă nodurile și invalidează cataloagele de înregistrări, păstrând ciornele
inspectorului și hashurile lor de conflict, selecția, filtrele și contextul.
Meniul de rescanare păstrează confirmarea existentă pentru ciorne.
În read-only nu se scriu indexuri sau markeri. Cache-urile pot fi șterse fără
pierdere de date; nu șterge directoarele autoritare `sessions`, `history`, `nodes`.

## Interfață

Evenimentele sunt grupate și refreshul este ales după tipul schimbării. O notiță
nu reconstruiește arborele, iar schimbările de sesiuni nu reconstruiesc metadatele
nodurilor. Redenumirea din Activitate actualizează etichetele fără refacerea
raportului. Inspectorul încarcă Detalii și tabul vizibil; Fișiere, Versiuni,
Planificare și jurnalul ascunse nu sunt citite la fiecare selecție. Proprietatea
ciornelor partajate este legată de task chiar când tabul nu a fost încă încărcat.
Spațiul de lucru folosește aceeași încărcare la cerere a secțiunilor.

TaskList, arborele lateral și tabelele Activitate reconciliază UUID-uri stabile:
inserare/mutare numai dacă este necesar, modificarea rândurilor schimbate și
eliminarea rândurilor ieșite din rezultat. Nu se șterge/recreează toată lista.
Filtrarea și sortarea se fac pe întregul rezultat înaintea afișării progresive,
în loturi de 200 de rânduri. O nouă cerere anulează continuarea celei vechi.
Jurnalul afișează progresiv câte 100 de înregistrări. Toate callbackurile de
randare rulează pe firul Tk; mecanismul existent UiBridge nu este înlocuit.
Descrierea rămâne un singur câmp editabil, fără toolbar și fără previzualizare.

## Reproducerea măsurătorilor

```bash
# Linux cu display virtual; workspace-ul de benchmark este temporar și se șterge.
xvfb-run -a python scripts/benchmark_performance.py --tasks 1000 --output /tmp/focusdesk-after.json
```

Baseline: `7708de22ed9fcc61b2cd60077915145dcdfa566e`. Același script rulează cu
sursele baseline extrase separat și selectate prin PYTHONPATH, fără resetarea
checkoutului de lucru. Fiecare măsurare folosește procese Python noi. Fixture-ul
conține 1.000 de taskuri, 50 deschise, un proiect, subtaskuri grupate pe părinți,
3.000 de sesiuni și 3.000 de evenimente. Generarea nu intră în timpi.

Sunt măsurate separat construirea UI, deschiderea workspace-ului, navigarea
Proiecte → Astăzi → Calendar → Proiecte, selecția, salvarea titlului, refreshul,
căutarea globală și Activitate pe 30 de zile. Se așteaptă terminarea loturilor UI.
Citirile și octeții sunt deschiderile de fișiere pentru citire prin Path.open în
workspace, nu apelurile stat sau I/O fizic al kernelului. RSS este maximul procesului,
tracemalloc măsoară maximul alocărilor Python în fluxul măsurat. Timpii sunt cu
instrumentarea activă. „Rece” înseamnă proces nou/cache în memorie gol, nu cache
filesystem al sistemului de operare golit. O singură probă per scenariu, Linux,
Python 3.12, Tk/Xvfb; nu sunt rezultate Windows sau garanții de latență.

Datele brute și rezultatele sunt în [benchmarks](benchmarks/), iar comparația de
mai jos este generată din acele fișiere.

### 1.000 taskuri — Prima deschidere. fără indexurile noi

| Operație | Înainte (ms) | După (ms) | Fișiere citite înainte → după | MiB citiți înainte → după |
|---|---:|---:|---:|---:|
| Construire UI | 262.90 | 249.33 | 0 → 0 | 0.000 → 0.000 |
| Deschidere workspace | 1497.22 | 1910.00 | 4003 → 4003 | 3.937 → 3.937 |
| Navigare (4 ecrane) | 3713.45 | 151.78 | 15000 → 18 | 15.907 → 0.019 |
| Selectare task | 1973.29 | 10.96 | 9001 → 1 | 6.997 → 0.002 |
| Salvare titlu | 124.47 | 2.12 | 1 → 1 | 0.001 → 0.001 |
| Refresh după salvare | 6154.20 | 21.86 | 24004 → 1 | 20.358 → 0.002 |
| Căutare globală | 155.56 | 150.53 | 1000 → 1000 | 2.210 → 2.210 |
| Activitate (30 zile) | 780.78 | 174.27 | 3000 → 241 | 3.181 → 0.256 |

Memorie Python de vârf: **27.25 → 19.11 MiB**. RSS maxim: **111.08 → 102.03 MiB**.

Totaluri identice: **226800 secunde lucrate**, **453600 secunde programate**.

### 1.000 taskuri — Proces nou. indexuri păstrate

| Operație | Înainte (ms) | După (ms) | Fișiere citite înainte → după | MiB citiți înainte → după |
|---|---:|---:|---:|---:|
| Construire UI | 275.40 | 293.58 | 0 → 0 | 0.000 → 0.000 |
| Deschidere workspace | 1476.73 | 966.62 | 4003 → 5 | 3.937 → 2.104 |
| Navigare (4 ecrane) | 3704.90 | 167.30 | 15000 → 18 | 15.907 → 0.019 |
| Selectare task | 1897.60 | 13.87 | 9002 → 2 | 6.998 → 0.003 |
| Salvare titlu | 119.76 | 1.64 | 1 → 1 | 0.001 → 0.001 |
| Refresh după salvare | 5954.89 | 32.43 | 24004 → 1 | 20.358 → 0.002 |
| Căutare globală | 153.96 | 159.65 | 1000 → 1000 | 2.210 → 2.210 |
| Activitate (30 zile) | 784.34 | 177.04 | 3000 → 241 | 3.181 → 0.256 |

Memorie Python de vârf: **27.27 → 20.05 MiB**. RSS maxim: **110.35 → 103.94 MiB**.

Totaluri identice: **226800 secunde lucrate**, **453600 secunde programate**.

### 5.000 taskuri — Prima deschidere. fără indexurile noi

| Operație | Înainte (ms) | După (ms) | Fișiere citite înainte → după | MiB citiți înainte → după |
|---|---:|---:|---:|---:|
| Construire UI | 299.77 | 273.93 | 0 → 0 | 0.000 → 0.000 |
| Deschidere workspace | 12350.15 | 9611.44 | 20003 → 20003 | 19.676 → 19.676 |
| Navigare (4 ecrane) | 18624.48 | 269.32 | 75000 → 84 | 79.536 → 0.089 |
| Selectare task | 10128.68 | 15.05 | 45001 → 1 | 34.978 → 0.002 |
| Salvare titlu | 602.95 | 2.36 | 1 → 1 | 0.001 → 0.001 |
| Refresh după salvare | 41390.91 | 42.77 | 120004 → 1 | 101.772 → 0.002 |
| Căutare globală | 746.52 | 776.46 | 5000 → 5000 | 11.060 → 11.060 |
| Activitate (30 zile) | 4140.67 | 895.86 | 15000 → 1174 | 15.907 → 1.245 |

Memorie Python de vârf: **113.07 → 78.8 MiB**. RSS maxim: **265.64 → 215.54 MiB**.

Totaluri identice: **1058400 secunde lucrate**, **2116800 secunde programate**.

### 5.000 taskuri — Proces nou. indexuri păstrate

| Operație | Înainte (ms) | După (ms) | Fișiere citite înainte → după | MiB citiți înainte → după |
|---|---:|---:|---:|---:|
| Construire UI | 262.09 | 250.11 | 0 → 0 | 0.000 → 0.000 |
| Deschidere workspace | 12352.41 | 4888.58 | 20003 → 5 | 19.676 → 10.512 |
| Navigare (4 ecrane) | 18949.40 | 308.61 | 75000 → 84 | 79.536 → 0.089 |
| Selectare task | 10026.17 | 31.82 | 45002 → 2 | 34.978 → 0.003 |
| Salvare titlu | 595.68 | 1.54 | 1 → 1 | 0.001 → 0.001 |
| Refresh după salvare | 43079.21 | 81.79 | 120004 → 1 | 101.772 → 0.002 |
| Căutare globală | 750.93 | 806.06 | 5000 → 5000 | 11.060 → 11.060 |
| Activitate (30 zile) | 4041.10 | 846.84 | 15000 → 1174 | 15.907 → 1.245 |

Memorie Python de vârf: **113.08 → 83.43 MiB**. RSS maxim: **265.43 → 226.18 MiB**.

Totaluri identice: **1058400 secunde lucrate**, **2116800 secunde programate**.

## Limite și verificări

Construirea inițială a indexului are un cost: pe proba de 1.000 de taskuri,
deschiderea fără cache este mai lentă decât baseline-ul. Catalogul de noduri și
verificarea semnăturilor rămân proporționale cu numărul de fișiere la deschidere;
această etapă nu promite pornire independentă de dimensiunea workspace-ului.

Căutarea globală își păstrează semantica: poate găsi text din descrierile vechi și
finalizate. Prima căutare completă poate citi toate descrierile; cache-ul de text
este în memorie, invalidat prin semnătură și la reîncărcare. Nu s-a introdus un
index persistent de text integral și nu se pretinde accelerarea acestui caz.
La „Tot istoricul”, Activitate trebuie să solicite toate sesiunile relevante;
progresivitatea interfeței nu elimină costul unui raport asupra tuturor datelor.

Testele de regresie verifică: citire doar pentru taskul cerut, indexare la scriere,
încărcare la cerere, redeschidere, ierarhie/context activ, mutare/coș/restaurare,
ștergerea cache-urilor, index corupt/incomplet, marker de crash, read-only,
conflicte externe inclusiv F5 repetat cu ciornă, copierea modelelor înainte de
editare, scriere eșuată, perioade/intervale și totaluri istorice, selecție/rânduri
progresive. Testele existente pentru timer, calendar, recuperare, editor simplu și
spațiul taskului sunt incluse în suita completă. S-a rulat și smoke-testul real Tk
al aplicației, pe date temporare.

Validarea este Linux/Xvfb. Nu s-a construit sau validat executabilul Windows și
nu s-a testat Outlook COM real. Cele 14 eșecuri existente pe Linux provin din
validarea căilor externe cu PureWindowsPath; testul de junction Windows este omis.

Comenzi executate pe revizia locală finală:

- `xvfb-run -a python -m pytest -q`: **291 trecute, 14 eșuate, 1 omis**.
  Cele 14 eșecuri au aceleași teste/cauze ca baseline-ul, fără regresii noi.
- `xvfb-run -a python -m focusdesk --smoke-test --smoke-report <fișier temporar>`:
  exit 0, `status=ok`, pornire GUI, salvare/recitire și spațiul taskului verificate.
- `python -m pip check`: fără dependențe incompatibile.
- `python -m compileall -q src scripts/benchmark_performance.py tests/test_performance_indexes.py`:
  fără erori.
- `git -c core.whitespace=cr-at-eol diff --check`: fără erori.

Nu s-au folosit date reale și nu s-a efectuat push, merge sau release.
