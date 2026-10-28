# Activitate — dashboard local

Activitate rămâne una dintre cele patru destinații principale. Nu adaugă servicii,
SQL, telemetrie sau dependențe. Datele rămân în JSON/Markdown locale, inclusiv când
nu există Outlook sau conexiune la internet. Descrierea taskului rămâne câmpul simplu
editabil, fără formatare asistată sau previzualizare.

## Navigare și citire

Antetul oferă 7/30/90 zile, Luna curentă, Interval personalizat și Tot istoricul.
Luna curentă include întreaga lună, deci și rezervările viitoare din ea. Intervalul
personalizat este inclusiv la ambele capete; acceptă ZZ.LL.AAAA sau YYYY-MM-DD.
Filtrul de proiect include Fără proiect și diferențiază numele identice prin UUID.
Resetare filtre revine la 30 zile, toate proiectele, fără detaliu selectat.

Patru carduri: Lucrat înregistrat, Programat, Taskuri finalizate în perioadă și
**Restante acum**. Butonul `?` oferă definiția, inclusiv din tastatură. Restante acum
și distribuția **Situație curentă** nu sunt reconstrucții istorice; filtrul de dată
nu le schimbă. Filtrele de proiect li se aplică. Distribuția include și taskurile
arhivate; restantele exclud arhiva și taskurile închise.

Graficul pe zile compară lucratul salvat (violet) cu programatul (contur).
Până la 45 zile agregă zilnic, până la 180 zile săptămânal (luni–duminică), apoi lunar.
Granularitatea este afișată. Barele de proiect arată Top 5 după timp lucrat și Restul,
care reprezintă toate proiectele rămase, nu o categorie fictivă de date.

Click pe o bară aplică un filtru de detaliu vizibil: intervalul barei sau proiectele
respective. Elimină detaliul păstrează perioada/proiectul de bază. Nu se pierd
filtrele, tabul de detalii sau scrollul când deschizi un task și revii în Activitate.

- Tab navighează controalele native și graficele; săgețile selectează o bară;
  Enter/Space aplică filtrul. Textul de sub grafic descrie valoarea selectată.
- Tabelele Pe zile și Pe proiecte oferă aceleași informații, cu valori exacte,
  numele complete și filtrare prin Enter/dublu-click.
- În Sesiuni, Enter/dublu-click deschide taskul. Un task lipsă este afișat ca
  **Task indisponibil** și păstrează duratele, fără a deschide un nod inexistent.
- Statusuri actuale oferă o alternativă textuală la banda colorată.
- **Calendar lunar / Ctrl+D** reutilizează fereastra lunară existentă. Preia filtrul
  de proiect și gruparea de proiecte selectată (inclusiv Restul). Luna poate fi
  schimbată independent de perioada dashboardului. Zilele au acces prin Tab și Enter.

Cardurile trec din patru coloane în două, iar graficele se așază vertical când
spațiul scade. Pagina se derulează vertical; tabelele au scroll orizontal pentru
coloane. Nu este obligatorie micșorarea fonturilor pentru a încăpea conținutul.

## Modelul comun de calcul

`services/activity.py` definește `ActivityFilters`, `ActivityRow`, `ActivityReport`
și `ActivityModel`. Dashboardul, graficul, tabelele, calendarul lunar,
`Queries.worked_by_day`, adaptorul vechi `activity_ledger` și exportul consumă
același model. Nu însumează totalurile agregate ale părintelui și copilului.

**Lucrat înregistrat:** `actual_seconds` salvat, o singură dată pe sesiune.
Include munca taskurilor finalizate, anulate și arhivate și a nodurilor dispărute.
Data este `started_actual_at`, cu fallback `start_at`, în fusul workspace-ului.
O sesiune peste miezul nopții este atribuită integral zilei de început efectiv,
conform convenției existente; nu este împărțită artificial pe zile.

**Programat:** durata în minute întregi a intervalului salvat `start_at`–`end_at`,
atribuită zilei `start_at`, cu excluderea statusurilor cancelled/missed.
Se păstrează convenția existentă pentru intervalele sesiunilor, inclusiv realizate;
nu este muncă efectuată. Calculul duratei folosește momente UTC, astfel încât orele
repetate/lipsă la schimbările DST nu inventează sau elimină timp.
O sesiune poate avea ziua programată în afara perioadei, dar ziua lucrată înăuntru,
sau invers; coloanele eligibile reflectă separat perioada aleasă.

**Live nesalvat:** separat de cardul Lucrat și de barele salvate. Pentru sesiunea
activă este `max(0, secunde_timer - actual_seconds_deja_salvat_pentru_acea_sesiune)`.
Se atribuie aceleiași zile de început efectiv și respectă aceleași filtre.
Timerul aflat în recuperare nu este declarat muncă nouă până la reconciliere.
Valoarea separată se actualizează și în tabele; CSV preia un snapshot curent la
export. Calendarul lunar arată separat salvat/live. Coloana de timp din lista de
taskuri arată acum explicit **Lucrat salvat**; timpul live rămâne separat în timer.
Nu se dublează secundele salvate când sesiunea este încă activă.

**Proiect:** cel mai apropiat strămoș de tip proiect din ierarhia actuală.
Legăturile simple nu modifică apartenența. Mutarea unui task regrupează sesiunile,
fără să le rescrie. Sesiunile cu nod lipsă intră în Fără proiect.

**Finalizate:** UUID-uri distincte de taskuri identificabile care au o tranziție
`status_changed → done` în istoricul perioadei. Redeschiderea nu șterge finalizarea
istorică; refinalizările aceluiași task se numără o singură dată în interval.
Tranzițiile proiectelor nu sunt numărate ca taskuri. Nu se folosesc `updated_at`
sau `completed_at` pentru a inventa evenimente. Datele vechi fără istoric suficient
pot subestima numărul; pagina indică și câte taskuri finalizate curent nu au o
tranziție done disponibilă. Evenimentele fără un task identificabil nu sunt
atribuite artificial unui proiect sau unui tip de nod.

Nu există scor de productivitate derivat din ore.

## Indexuri, încărcare și erori

Se reutilizează RecordStore și indexurile etapei de performanță. Rezumatele
sesiunilor și evenimentelor sunt normalizate în memorie la schimbarea reviziei,
apoi sunt selectate cronologic prin bisect înainte de calculul raportului.
Schimbarea filtrelor nu recitește toate fișierele JSON. Cache-ul rapoartelor este
limitat la 12 intrări și este restrâns suplimentar când rezultatele sunt mari.
Descrierile, notițele și rezumatele complete ale sesiunilor nu sunt necesare aici.

Indexul **history/.cache/index.json** trece la versiunea 2 pentru a include numai
ținta tranziției de status (`transition_to`), nu întregul payload al evenimentului.
Cache-ul de versiune 1 este reconstruit la prima cerere; sursele rămân autoritare.
Indexurile nodurilor și celorlalte RecordStore își păstrează versiunile.
Read-only permite calculul în memorie și exportul, fără scrierea cache-urilor.

Reconcilierea inițială și rapoartele mari folosesc UiBridge existent. Workerul nu
atinge widgeturi Tk. Cererile au generații; rezultatele pentru filtre, workspace,
revizii sau fus orar depășite sunt ignorate/recalculate. Rândurile se afișează
progresiv folosind infrastructura incrementală existentă, după filtrare/sortare.
Timpul live nu rescanează fișiere. Indicatorii curenți se reîmprospătează și la minut.

Stările sunt distincte: Se încarcă, fără sesiuni în filtrele alese, eroare de
interval/raport/export. Sursele corupte omise sunt semnalate ca avertisment, nu
prezentate ca raport complet. F5 păstrează reconcilierea și protecția ciornelor din
etapa anterioară. Nu se scriu date autoritare din callbackuri UI.

## CSV

Export local UTF-8 cu BOM, separator `;`, delimitare/escaping prin modulul standard
`csv`. Nu folosește Excel COM. Conține:

- rânduri **Sesiune**, cu UUID-uri, nume, proiect, status, început ISO cu offset,
  zi lucrată și secunde eligibile salvate/programate/live;
- rânduri **Indicator**, care reproduc cele patru carduri și live, cu definițiile
  complete și contextul perioadei/proiectelor aplicate;
- un rând **Definiție** pentru limitarea istoricului și situația curentă.

La agregarea externă, selectează `Tip=Sesiune` pentru coloanele de durată sau
`Tip=Indicator` pentru indicatori; nu însuma tipurile diferite ca înregistrări de
muncă. Antetele precizează unitățile. Numele cu diacritice sunt păstrate.
Textele care pot începe formule Excel (`=`, `+`, `-`, `@`, inclusiv după spații,
sau prefixe tab/CR/LF) primesc apostrof înainte de escaping CSV. Valorile numerice
rămân numerice. Un interval fără sesiuni exportă totuși indicatorii și definițiile.

## Capturi și validare

Capturi **reale Tk**, exclusiv cu date demonstrative temporare:

- [Dashboard complet, 100%](capturi-ui/activitate-dashboard-100.png)
- [Detalii și explicații](capturi-ui/activitate-detalii-100.png)
- [Calendar lunar](capturi-ui/activitate-calendar-lunar.png)
- [Dimensiunea minimă, scalare Tk 125%](capturi-ui/activitate-dashboard-125.png)
- [Dimensiunea minimă, scalare Tk 150%](capturi-ui/activitate-dashboard-150.png)

Reproducere pe Linux cu Xvfb și Pillow deja prezent prin ttkbootstrap:

```bash
xvfb-run -a -s '-screen 0 2600x1900x24' python scripts/capture_activity_dashboard.py
xvfb-run -a -s '-screen 0 2600x1900x24' python scripts/capture_activity_dashboard.py --minimum --scale 1.25
xvfb-run -a -s '-screen 0 2600x1900x24' python scripts/capture_activity_dashboard.py --minimum --scale 1.5
```

Nu există dependențe noi sau hookuri PyInstaller noi. Canvas, CSV, dataclass,
zoneinfo și mecanismul de workers sunt deja disponibile în runtime/pachet.
Capturile din documentație nu intră în resursele executabilului. Verificările de
scalare sunt pe Tk/Xvfb Linux, nu validare de DPI nativ Windows. Executabilul și
Outlook COM real nu au fost construite/testate în această etapă.

Verificări executate în această etapă:

- `xvfb-run -a python -m pytest -q`: **309 trecute, 14 eșuate preexistent pe
  Linux, 1 omis**. Eșecurile sunt aceleași validări de căi Windows/PureWindowsPath
  din etapa precedentă; nu sunt mascate sau dezactivate.
- `xvfb-run -a python -m pytest -q tests/test_activity_dashboard.py`: **18 trecute**.
  Include egalitatea cardurilor/seriilor/tabelelor/CSV, părinți/subtaskuri, taskuri
  redeschise/refinalizate, apartenență actuală, canceled/missed, timp live parțial
  salvat și în afara perioadei, interval gol, midnight/DST, CSV sigur, migrarea
  indexului, erori de sursă și aplicarea rezultatelor workerului numai pe firul Tk.
- Smoke-testul real al aplicației: exit 0, `status=ok`.
- `pip check`, `compileall` și verificarea whitespace: fără erori.
- Capturi reale și verificarea încadrării orizontale la 100%, 125%, 150% Tk/Xvfb.

Exportul include și avertismentele privind sursele necitibile, când există.
Modificările sunt locale; nu s-a făcut push, merge sau release.

## Precizare pentru sesiunile directe

Programat exclude intervalele tehnice `origin=timer`, care nu sunt rezervări. Pornirea dintr-o rezervare reutilizează ID-ul ei. Corectează timpul… modifică durata/intervalul efectiv cu audit, iar toate vizualizările folosesc același model. [Reguli](SESIUNI.md).
