# Descriere Markdown și statusuri vizuale

FocusDesk păstrează Tkinter + ttkbootstrap, tema luminoasă și fișierele locale.
Nu este necesară nicio dependență nouă pentru editor sau previzualizare.

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

**Editează Markdown** afișează sintaxa sursă; acesta nu este un editor WYSIWYG.
Toolbarul aplică titluri (nivelurile 1–3 din meniu), bold, italic, liste cu bulleturi/numerotate, căsuțe
Markdown, linkuri și blocuri de cod. Formatarea folosește selecția sau poziția
cursorului și readuce focusul în text. Formatarea unui text este o operație Undo.

- Ctrl+B / Ctrl+I: bold / italic.
- Ctrl+Z: Undo; Ctrl+Y sau Ctrl+Shift+Z: Redo.
- Ctrl+A: selectare integrală; Ctrl+C/X/V: copiere/tăiere/lipire native.
- Tab / Shift+Tab: indentare/dezindentare a liniilor selectate cu patru spații.
- Enter: continuă lista și incrementarea numărului; un element gol încheie lista.
  Căsuțele noi sunt nebifate, chiar dacă elementul anterior era bifat.
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

## Previzualizare sigură

Tabul **Previzualizare** folosește exclusiv etichete de formatare într-un widget Tk
Text read-only. Redă titluri ATX (nivelurile 1–6), liste și indentare, căsuțe
Markdown, bold/italic, linkuri cu adresa vizibilă, cod inline și blocuri delimitate
cu trei backtick-uri. Este un subset Markdown practic, nu un parser CommonMark
complet (de exemplu nu oferă tabele sau interpretarea tuturor combinațiilor imbricate).

HTML-ul rămâne text inert; codul nu se execută. Linkurile se afișează fără accesare
automată. Imaginile nu se încarcă, iar resursele externe nu se descarcă. Nu este
folosit un browser pentru previzualizare. Editarea nu reface previzualizarea ascunsă
la fiecare tastă; aceasta se calculează când este afișată.

## Șablon și checklist

**Descriere structurată** inserează numai la cerere, într-o descriere goală:
Obiectiv, Context, Pași / cerințe, Rezultat așteptat, Criterii de finalizare, Observații.
Nu înlocuiește descrieri existente.

Căsuțele `- [ ]` / `- [x]` sunt exclusiv documentare Markdown. Nu schimbă checklistul
funcțional din **Subtaskuri**, progresul sau statusul taskului. Toolbarul și
secțiunea checklist precizează diferența.

Exemple capturate din Tk real: [statusuri](capturi-ui/11-statusuri.png),
[previzualizare extinsă](capturi-ui/12-descriere-previzualizare.png).
