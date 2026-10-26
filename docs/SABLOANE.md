# Șabloane locale pentru proiecte și taskuri

Șabloanele sunt structuri reutilizabile, fără AI, conexiuni externe sau servicii în
fundal. Nu sunt recurențe: crearea din șablon este o acțiune explicită, o singură dată.
Niciun proiect demonstrativ nu este creat automat în workspace.

## Creează dintr-un șablon

1. În **+ Nou → Din șablon…**, alege un șablon implicit sau personal.
2. Completează titlul, destinația și variabilele declarate. Lista destinațiilor include
   numai părinți permiși pentru tipul rădăcinii; rădăcina workspace-ului este disponibilă.
3. Apasă **Actualizează previzualizarea**. Selectează elementele arborelui pentru a
   consulta descrierea Markdown, checklistul, estimarea, etichetele și referințele.
4. Apasă **Creează structura**. Dacă schimbi câmpurile după previzualizare, trebuie
   să previzualizezi din nou. Confirmarea apare numai după salvarea întregii structuri.
5. **Deschide elementul creat** îl selectează în aplicație. Dialogul nu pornește timerul.

Fiecare element primește UUID nou, taskurile pornesc **De făcut**, checklisturile
sunt nebifate. Estimarea inițială, dacă există, devine și timpul rămas estimat; nu este
timp lucrat. Agregările și regulile ierarhiei existente sunt păstrate. Finalizarea
subtaskurilor nu închide automat părintele. Nu există date Outlook de sincronizat
în noile elemente.

Butonul se dezactivează după creare; ID-ul cererii previne repetarea aceleiași operații
inclusiv după restart. O eroare retrage elementele noi. Dacă rollbackul este blocat de
disc/permisiuni, apare explicit o eroare de creare incompletă, iar la următoarea
redeschidere editabilă se reîncearcă recuperarea. Nu se raportează succes complet.
Datele existente, din afara lotului nou, nu sunt șterse de recuperare.

## Salvează și gestionează

Meniul contextual al unui proiect/task oferă **Salvează ca șablon…**. Mai întâi se
rezolvă modificările nesalvate ale taskului, apoi se citește structura salvată. Editorul
primește o ciornă separată; proiectul/taskul-sursă nu se modifică.

**Instrumente → Gestionare șabloane…** oferă:

- Șablon nou, editare și duplicare.
- Ștergere cu confirmare (nu afectează proiectele/taskurile deja create).
- Import/export al unui singur fișier JSON, ales explicit de utilizator.
- Previzualizare și creare din șablon.

Editorul are arbore și taburi **Conținut** / **Structură și opțiuni**. Poți modifica
numele șablonului, titlurile, descrierile cu editorul Markdown existent, checklisturile,
următorul pas, prioritățile, etichetele și estimările opționale; poți adăuga subtaskuri
sau elimina o ramură din șablon. Cheile locale afișate în arbore se folosesc pentru
părinte, dependențe și legături. Dependențele și ierarhia trebuie să fie fără cicluri;
legăturile sunt referințe, nu părinți sau dependențe. Validarea împiedică referințele
inexistente și regulile de părinte nepermise. **Ctrl+S** salvează șablonul din editor.
Închiderea editorului cu modificări cere confirmarea renunțării. Două editoare nu se
pot suprascrie silențios: o versiune schimbată trebuie redeschisă.

În workspace doar pentru citire, catalogul și exportul sunt disponibile; crearea,
salvarea, importul, duplicarea și ștergerea sunt interzise. Dialogurile rămân legate de
workspace-ul de la deschidere; schimbarea workspace-ului blochează aplicarea lor.

## Ce se păstrează și ce se exclude

Se păstrează tipurile și ordinea ierarhiei, titlurile, descrierile Markdown,
checklisturile ca text, prioritățile, etichetele, estimările, următorul pas și numai
legăturile/dependențele interne structurii. Folderele interne existente sunt acceptate,
cu aceleași reguli ca în Workspace; rădăcina trebuie să fie proiect sau task.

Nu se copiază ID-urile originale, istoric, note, sesiuni, timp lucrat, sincronizări
Outlook, checkpointuri/Git, solicitant/adrese de colegi, fișiere/căi/foldere de cod,
referințe externe structurii, termene originale, prioritate azi sau statusuri/bife.
Lista excluderilor apare și în previzualizare. **Textul liber din titlu, descriere,
checklist și următorul pas se păstrează**: verifică și elimină manual eventuale date
personale scrise acolo înainte de a exporta un șablon.

## Variabile simple

Declară numele în câmpul Variabile, separate prin virgulă: de exemplu
`nume_proiect, sistem_sap, tranzactie, rezultat_asteptat`. Numele conțin litere ASCII,
cifre și underscore, încep cu literă și sunt distincte (maximum 40).
În titluri și descrieri folosește `{{nume_proiect}}`. La creare, toate variabilele
declarate cer text nevid, maximum 10000 caractere fiecare.

Înlocuirea este literală, o singură trecere, fără expresii, `eval`, cod sau shell.
Se înlocuiesc numai numele declarate, inclusiv un placeholder declarat dintr-un bloc
Markdown de cod. Acolade obișnuite (`{"cheie": 1}`), `{nume}` și `{{nedeclarat}}` rămân
intacte. Textul introdus nu este reevaluat. Checklistul și următorul pas rămân text
literal; variabilele se aplică doar titlurilor și descrierilor.

## Persistență și compatibilitate

Șabloanele personale: `_system/templates/<uuid>.json`, UTF-8, `schema_version: 1` și
`revision`. Scrierile sunt atomice, cu copie `.bak` la editare. Catalogul raportează
fișierele invalide și le ignoră; nu împiedică deschiderea taskurilor existente.
Directorul se creează la prima salvare/importare, fără migrarea datelor vechi.
Backupurile de metadate și cele complete includ șabloanele personale; restaurarea
standard într-un folder nou le păstrează.

Șabloanele implicite sunt resurse ale aplicației, distribuite împreună cu aceasta:
**Automatizare SAP**, **Investigare incident**, **Dezvoltare aplicație Python** și
**Task simplu**. Nu au durate sau dependențe impuse. Pentru editare folosește **Duplică**;
copia personală are alt ID și nu este suprascrisă la actualizarea aplicației.

Importul validează strict un singur șablon, cu maximum **2 MiB**, **500 elemente** și
schemă compatibilă. Cheile sunt locale, referințele trebuie să fie interne; câmpurile
necunoscute (inclusiv căi sau comenzi) sunt respinse. Nicio cale din JSON nu este
interpretată. Expansiunea variabilelor este și ea limitată. Fișierul importat primește
ID personal nou, evitând suprascrierea unui șablon existent. Exportul nu include
resurse sau fișiere ale proiectelor.

## Verificare

```powershell
python -m pytest -q tests/test_templates.py tests/test_templates_ui.py
```

Testele UI necesită Tk/display. Capturi reale cu date demonstrative temporare:
[gestionare](capturi-ui/17-gestionare-sabloane.png),
[creare și previzualizare](capturi-ui/18-din-sablon.png),
[editor](capturi-ui/19-editor-sablon.png). Limitele verificărilor sunt în
[RAPORT.md](RAPORT.md).
