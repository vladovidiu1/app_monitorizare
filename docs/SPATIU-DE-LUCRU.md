# Spațiul de lucru al taskului

Selectează un task și apasă **Deschide spațiul de lucru** în inspector sau în meniul
contextual. Pagina se deschide în centrul aplicației, fără dialog modal. Dublul clic
existent în arbore/listă își păstrează comportamentul; nu este înlocuit.

**Înapoi** revine la pagina anterioară, cu filtrele, selecția, derularea și lățimile
panourilor păstrate. Din Pași poți deschide un subtask; Înapoi revine la taskul părinte.
La schimbarea taskului, ciornele nesalvate cer salvare, renunțare sau anulare.
Întoarcerea la inspectorul aceluiași task păstrează ciorna fără o copie separată.

## Lucru și salvare

Antetul arată calea proiect/task, statusul, prioritatea, termenul și timerul. Comenzile
pentru sesiune, finalizare/redeschidere și salvare sunt vizibile. **Mai multe** oferă
compunerea manuală de e-mail, mutarea, arhivarea, codul în VS Code și copierea descrierii.
Nu pornește o sesiune prin simpla deschidere a paginii.

Editorul amplu este același editor Markdown asistat ca în inspector: toolbar,
undo/redo, continuarea listelor, șablon la cerere și previzualizare locală. Inspectorul
și pagina împart bufferul descrierii, următorul pas și ciornele rapide; nu se pot
suprascrie reciproc. `description.md` rămâne sursa autoritară la salvare. HTML și codul
nu se execută și imaginile externe nu se descarcă automat.

**Ctrl+S** salvează contextul activ prin serviciile existente: descrierea, detaliile,
următorul pas, nota în curs și câmpurile completate de adăugare rapidă subtask/checklist.
Starea Salvat/Modificări nesalvate este vizibilă. O eroare păstrează ciorna. Schimbarea
workspace-ului și închiderea folosesc aceeași protecție a modificărilor nesalvate.
Poziția și modul editorului se păstrează pe task în sesiunea curentă a aplicației.

Panoul secundar este redimensionabil și poate fi ascuns din buton. **Pași** oferă
checklistul funcțional și subtaskurile cu progres, deschidere și comenzile existente.
Checklistul funcțional rămâne separat de căsuțele Markdown ale descrierii. **Fișiere**,
**Activitate** (notă rapidă, jurnal și sesiuni), **Planificare** și **Versiuni** reutilizează
funcțiile existente; nu încarcă toate informațiile simultan.

## Concentrare

**Concentrare** sau **F11**, cât timp pagina taskului este activă, ascunde temporar
sidebarul și inspectorul și deschide secțiunea Pași. **Ieși din concentrare · F11**
rămâne vizibil. La ieșire se restaurează panourile, lățimile, secțiunea secundară și
starea ascuns/afișat anterioare. Navigarea în altă pagină iese din concentrare.
Timerul existent continuă independent: concentrarea nu îl pornește, nu îl pune pe
pauză și nu îl oprește. Rămâne permis un singur timer activ.

## Date protejate

În workspace doar pentru citire poți consulta descrierea și secțiunile; salvarea și
modificările sunt dezactivate. Arhivarea actualizează antetul fără să piardă ciorna.
Dacă taskul dispare, pagina afișează explicit indisponibilitatea, oprește editarea și
păstrează descrierea recuperabilă prin **Mai multe → Copiază descrierea**. Nu salvează
într-un task diferit. Renunțarea la ciornă necesită alegerea utilizatorului.

Nu se schimbă formatul datelor. Nu există AI, citire sau analiză de inbox. Outlook
Classic rămâne opțional pentru calendar și e-mail manual cu confirmare.

## Verificare locală

`python -m pytest -q tests/test_task_space.py` necesită un display Tk (pe Linux poate
fi folosit Xvfb). Cazurile includ ciorne comune, Ctrl+S, revenire cu filtre/derulare,
subtaskuri, F11, timer, doar citire, arhivare/ștergere/restaurare, eșec la salvare,
schimbarea workspace-ului, descriere lungă și multe subtaskuri.

Capturi reale din workspace demonstrativ temporar:
[spațiu de lucru](capturi-ui/15-spatiu-lucru.png),
[concentrare](capturi-ui/16-concentrare.png),
[fereastră minimă](capturi-ui/task-space-min.png),
[scalare Tk 125%](capturi-ui/task-space-125.png).
Scalarea Tk pe Linux nu echivalează cu verificarea DPI nativă Windows.

## Completarea asistată a descrierii

Butonul **Completează cu ghid…**, lângă Descriere, folosește aceeași ciornă și
același Undo/Redo ca inspectorul și editorul extins. Formularul are ciornă proprie;
Aplică nu salvează taskul și nu transformă pașii în checklist sau subtaskuri.
[Aplicare, adăugare/înlocuire și anulare](DESCRIERE-MARKDOWN.md#completează-cu-ghid).

## Update-uri ulterioare ale scriptului

Folosește Redeschide pentru continuarea cerinței inițiale sau Adaugă cerință nouă… pentru muncă independentă. Folderul de cod poate fi comun, cu checkpointuri proprii fiecărei cerințe. [Ghid](CERINTE-ULTERIOARE.md).

Indicatorul permanent al sesiunii rămâne vizibil și în Concentrare. Începe pe alt task oferă continuarea sesiunii existente, încheierea ei înaintea noului task sau anulare. [Ghidul sesiunilor](SESIUNI.md).

## Contextul întâlnirilor

Taskurile legate de o întâlnire au meniul compact Întâlniri legate, navigabil spre notițe. Acțiunile se transformă numai explicit în taskuri/proiecte sau cerințe noi; deschiderea contextului nu pornește o sesiune. [Ghid](INTALNIRI.md).
