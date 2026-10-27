# Descriere Markdown și statusuri vizuale

FocusDesk păstrează Tkinter + ttkbootstrap, tema luminoasă și fișierele locale.
Nu este necesară nicio dependență nouă pentru editor.

## Statusuri

Pictogramele originale locale au aceeași licență MIT ca restul pictogramelor.
Forma și eticheta identifică statusul; culoarea este un indiciu suplimentar:

| Status | Pictogramă |
|---|---|
| De făcut | Cerc necompletat |
| În lucru | Cerc cu simbol de pornire |
| În așteptare | Ceas |
| În testare | Recipient de laborator |
| Finalizat | Cerc cu bifă verde |
| Anulat | Cerc cu cruce |

Taskurile vechi cu status intern `inbox` folosesc pictograma și eticheta De făcut. Folderul și proiectul rămân
identificabile prin pictogramele lor, indiferent de status. Sistemul se aplică
arborelui, listei centrale și rezultatelor căutării, cardurilor/sesiunilor din
Astăzi și inspectorului (inclusiv subtaskurilor). O schimbare salvată de status
actualizează pictogramele prin refresh-ul UI, fără redeschiderea aplicației.

Taskurile închise au text estompat, cu contrast lizibil. În lista centrală folosește
**Arată finalizate** (include și Anulat); alegerea se păstrează la reîmprospătarea
aceleiași vizualizări. **Instrumente → Arată taskurile închise în arbore** controlează
arborele și se păstrează după restart. Un părinte închis cu descendenți deschiși
rămâne ca structură, astfel încât aceștia să nu fie ascunși accidental.

Inspectorul și meniul contextual oferă **Redeschide taskul** pentru stările închise.
Redeschiderea trece taskul la De făcut. Finalizarea subtaskurilor modifică progresul
agregat, fără a finaliza automat statusul părintelui.

## Editorul din inspector

În Detalii, separatorul orizontal permite redimensionarea zonei de metadate și a
zonei de documentare. Câmpurile de sus au scroll separat. Descrierea ocupă spațiul
rămas, are word wrap, scroll propriu și salvarea rămâne în subsolul fix.

Descrierea este un singur câmp editabil, fără bară de formatare și fără file de
editare/previzualizare. Aceeași interfață simplă este folosită în spațiul de lucru,
fereastra extinsă și editorul de șabloane. Textul Markdown existent rămâne intact,
afișat ca text obișnuit; Enter nu continuă automat listele.

- Ctrl+Z: Undo; Ctrl+Y sau Ctrl+Shift+Z: Redo.
- Ctrl+A: selectare integrală; Ctrl+C/X/V: copiere/tăiere/lipire native.
- Ctrl+S: salvează detaliile și descrierea prin Workspace.

Lipirea multilinie nu este reformulată automat. Diacriticele și textele vechi rămân
UTF-8 în `description.md`, fără conversie la HTML și fără migrare de conținut.

## Editorul extins și anularea

**Extinde descrierea** deschide o fereastră modală mare, redimensionabilă. Ea și
inspectorul sunt două vederi ale **aceluiași buffer Tk Text**, nu două copii care
se suprascriu. Schimbarea taskului/workspace-ului este blocată cât editorul extins
este deschis. Acest lucru este distinct de chatul nemodal eliminat anterior.

**Salvează / Ctrl+S** folosește salvarea existentă a detaliilor (inclusiv celelalte
câmpuri deja editate). La eroare, fereastra rămâne deschisă și textul nu se pierde.
**Anulează / Escape / închiderea ferestrei** restabilește descrierea și starea
„nesalvat” de la deschiderea ferestrei. Modificările făcute în inspector înainte de
extindere rămân; discul nu este modificat. La anulare se resetează istoricul
Undo/Redo al descrierii, astfel încât textul abandonat să nu reapară accidental.

În afara ferestrei extinse, schimbarea selecției cu modificări nesalvate păstrează
întrebarea existentă: Salvează, Renunță sau Rămâi aici.

## Conținutul existent

HTML-ul, codul și linkurile rămân text inert. Nu se execută cod și nu se descarcă
resurse externe. Descrierile existente nu sunt convertite sau rescrise automat.
Căsuțele `- [ ]` / `- [x]` din text nu schimbă checklistul funcțional din Subtaskuri.
