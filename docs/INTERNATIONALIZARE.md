# Limbile FocusDesk

FocusDesk include Română (`ro`), English (`en`), Deutsch (`de`), Français (`fr`) și Español (`es`). Interfața, mesajele proprii, statusurile/prioritățile afișate, textele generate la cerere, șabloanele incluse și cele 19 capitole ale ghidului sunt localizate. Brandul FocusDesk și denumirile produselor externe rămân neschimbate. Nu există dependențe runtime noi sau servicii de traducere apelate în utilizare.

## Alegerea limbii

**Setări → General → Limbă / Language** arată denumirile proprii ale celor cinci limbi. **Aplică limba la repornire** scrie atomic numai preferința `language` în profilul aplicației (`%APPDATA%/FocusDesk/app.json`), separat de workspace. Opțiunea funcționează fără workspace și într-un workspace read-only. Butonul Salvează al setărilor workspace-ului păstrează și alegerea limbii dacă salvarea reușește.

Schimbarea se aplică la **următoarea pornire manuală**, fără închidere automată, oprirea timerului sau decizii impuse asupra ciornelor. Același proces păstrează aceeași limbă inclusiv în dialoguri/worker-e. UI are tabele de opțiuni și valori implicite construite la import; reconstruirea lor în timpul editării ar risca pierderea contextului. Textul explică această regulă înainte de aplicare și confirmă limba păstrată pentru pornirea următoare. La eroare, preferința din memorie revine la valoarea anterioară și apare explicația cu detaliul tehnic.

Lipsa unei preferințe sau un cod necunoscut păstrează româna, inclusiv pentru utilizatorii existenți. Limba sistemului nu este folosită ca schimbare implicită. Fusul orar rămâne o setare distinctă a workspace-ului.

## Protecția datelor

Nu se traduc și nu se rescriu titluri, descrieri, nume, căi, nume de fișiere, minute/notițe, șabloane personale, mesaje compuse sau istoricul existent. Cataloagele nu primesc niciodată textul utilizatorului drept cheie. Parametrii sunt inserați ca valori, fără o a doua interpretare a acoladelor din conținutul lor.

Valorile persistate ale tipurilor, priorităților și statusurilor (`task`, `todo`, `done`, `normal` etc.), proprietățile COM/UUID, identificatorii de relații, categoriile evenimentelor și directoarele tehnice rămân stabile. Evenimentele deja structurate continuă să aibă cod și date separate; etichetele din jurnal sunt traduse la afișare. Texte libere vechi rămân exact cum au fost scrise.

Inspectorul și spațiul taskului folosesc ID-uri precum `details`, `journal`, `files`, `steps`, nu textele taburilor. Preferințele vechi `Detalii`, `Jurnal`, `Subtask-uri` etc. sunt migrate către ID-uri. Perioadele dashboardului și granularitatea folosesc `30d`/`custom` și `days`/`weeks`/`months`. Meniurile de acțiuni folosesc comenzi/poziții stabile, iar selectoarele de status/prioritate/proiect întorc ID-urile din modelele existente.

Taburile care nu încap au un selector cu etichete complete și acces prin tastatură. Acțiunile taskului trec pe mai multe rânduri, păstrând comenzile și focusul. Nu se reintroduc formatarea sau previzualizarea în descriere.

## Cataloage și formate

`src/focusdesk/i18n.py` încarcă numai JSON-urile locale din `resources/locales`. Fiecare limbă are un catalog separat. Cheile identifică sensul/contextul; nu se redenumesc când se schimbă doar formularea.

```python
from focusdesk.i18n import tr

tr('settings.language_saved', name='Deutsch')
tr('items.tasks', count=3)
```

Interpolarea folosește parametri numiți. Un mesaj poate reordona parametrii în fiecare limbă. Nu construi propoziții prin lipirea fragmentelor traduse. Numele și celelalte valori de utilizator se transmit ca parametri; nu se caută în catalog. Paragrafele/etichetele independente pot fi afișate separat.

Pluralurile sunt obiecte cu `one` și `other`, plus `few` pentru română. Română: 1 → one; 0, fracții și resturile 1–19 modulo 100 → few, celelalte → other. Franceză: valori de la 0 inclusiv până la 2 exclusiv → one; celelalte → other. Engleză, germană, spaniolă: 1 → one; restul → other. Regula este aplicată prin `count`, inclusiv în mesaje despre sesiuni, capitole găsite, întâlniri actualizate și atașamente. Nu se folosesc sufixe construite în callbackuri.

Cheie lipsă: se raportează o singură dată în log și se folosește româna, cu regulile ei de plural. Dacă lipsește și sursa apare `[cheie]`, nu un text gol. Parametrii lipsă sunt erori de programare și nu sunt ascunși. Testele blochează diferențele de chei, forme plurale și parametri între cataloage.

Afișarea datelor/orelor, zilelor/lunilor, numerelor, procentelor și duratelor este centralizată. Nu se folosește `locale.setlocale`, care ar afecta global threadurile. Ora este în format 24h. Datele sunt zi-lună-an: punct în ro/de și bară în en/fr/es. Intrarea acceptă explicit zi-lună-an ori `YYYY-MM-DD`, cu ora `HH:MM`; `10/29/2026` este refuzat, nu ghicit. Convențiile existente pentru DST și fusul workspace-ului rămân neschimbate.

CSV are antete/explicații în limba activă, dar ordinea coloanelor, UUID-urile, momentele ISO cu offset, zilele ISO și secundele numerice rămân interoperabile. Nu aplica formatarea numerelor de afișare valorilor numerice CSV. Rămân UTF-8 cu BOM, separatorul `;` și protecția împotriva interpretării textelor ca formule Excel. Numele coloanelor sunt localizate: un consumator automat trebuie să știe limba antetelor sau să folosească schema/ordinea documentată în modelul de export.

## Ghid și texte generate

Ghidul românesc rămâne în `resources/guide`; variantele sunt în `guide/en`, `guide/de`, `guide/fr`, `guide/es`. Fiecare are index și 19 articole. Identificatorii capitolelor și ancorele sunt comune. În variante, un titlu poate preciza ancora stabilă:

```markdown
## Expected result {#rezultat-asteptat}
```

Alege ancora reală a secțiunii sursă; nu o deduce din titlul tradus. Linkurile `guide:capitol#ancora` sunt validate, inclusiv țintele F1. Căutarea citește numai ghidul limbii active, nu documentele personale. Rendererul rămâne Tk Text read-only, fără HTML executat/browser/rețea.

E-mailul implicit și descrierea ghidată folosesc limba procesului la generare. Aplicarea ghidului rămâne o operație Undo asupra PeerText și cere salvarea existentă. Mesajul compus este o copie editabilă, fără regenerare la refresh sau la schimbarea preferinței. Variantele șabloanelor incluse se aleg din `resources/templates/<limbă>`; șabloanele personale sunt citite fără traducere. UUID-urile, cheile structurii și variabilele rămân comune; numele variabilelor incluse au etichete UI localizate.

Erorile proprii sunt localizate. Detaliul tehnic extern rămâne original în mesajul explicativ pentru diagnostic. Nu se pretinde traducerea erorilor Windows/COM/Outlook ori a interfeței acelor programe.

## Adăugarea unei limbi

1. Adaugă un cod în `LANGUAGES`, validatorul `AppConfig.language` și lista acceptată a scenariului `scripts/i18n_smoke.py`. Alege denumirea proprie și o regulă de plural în modulul central.
2. Creează `resources/locales/<cod>.json` cu aceleași chei și parametri. Traduce în context, fără copii românești de umplutură. Păstrează produsul/identificatorii tehnici. Verifică mesajele cu 0/1/2/20 și texte lungi.
3. Adaugă formatele locale centrale pentru cod; nu introduce ramuri de limbă în componentele UI.
4. Creează cele 19 articole și indexul în `resources/guide/<cod>`, cu ancore comune, tutoriale actuale și denumirile reale ale comenzilor. Actualizează și testele parametrizate pentru noul cod.
5. Adaugă variantele șabloanelor incluse, păstrând structura/ID-urile; nu atinge șabloanele din workspace.
6. Rulează verificările de mai jos și inspectează capturile în ferestre mici. Nu adăuga etichete hardcodate noi; testul de UI permite doar branduri externe stabilite.
7. Construiește și inspectează wheel-ul. `pyproject.toml` include directoarele de cataloage/ghiduri/șabloane, iar `focusdesk.spec` reutilizează `collect_data_files('focusdesk')`. Verifică separat distribuția PyInstaller reală pe Windows; simularea `_MEIPASS` nu este un test de EXE.

## Reproducere și limite

```sh
xvfb-run -a python -m pytest -q
xvfb-run -a python scripts/i18n_smoke.py --language de --scale 1.5 --capture-dir artifacts/i18n/de-150 --report artifacts/i18n/de-150/manifest.json
python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir artifacts/wheel .
```

Scenariul folosește exclusiv profile/workspace-uri temporare. Verifică pornire fără workspace, Setări, cele patru pagini, filtre, secțiunile taskului/F1, descriere ghidată, Undo/Redo, salvare, PeerText, anulare extinsă, dialog modal, timer, preferință amânată, raport/CSV, finalizare/redeschidere și șabloane. Nu trimite mesaje și nu deschide integrări externe.

Rezultatele finale și capturile sunt în [raportul verificării limbilor](VERIFICARE-LIMBI.md). Scalarea Tk/Xvfb nu certifică DPI nativ Windows, afișarea între monitoare sau dialogurile native ale sistemului. Mesajele/butoanele furnizate de sistemul de operare pot urma limba acestuia. Nu s-au executat Outlook Classic real sau build/rulare EXE Windows pentru această etapă.
