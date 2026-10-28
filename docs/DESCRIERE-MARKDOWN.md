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

## Completează cu ghid…

Lângă **Descriere**, în inspector, spațiul de lucru și editorul extins, butonul
**Completează cu ghid…** deschide un formular modal redimensionabil. Editorul
principal rămâne un singur câmp: nu reapar toolbarul Bold/Italic sau filele de
editare/previzualizare. Editorul de șabloane își păstrează fluxul separat existent;
ghidul se oferă numai în contextele unei descrieri de task/nod disponibile.

Formularul pornește gol de fiecare dată, fără interpretarea automată a textului
vechi. Are **Scop**, inițial **Pasul 1** și **Pasul 2**, **+ Adaugă pas**, comenzi
**Sus/Jos/Șterge pasul** și **Rezultat așteptat**, toate cu text multilinie.
Pașii se renumerotează la reordonare/ștergere. La mulți pași se derulează formularul;
Aplică și Anulează rămân în subsolul fix.

Tastarea modifică numai ciorna temporară a ghidului. **Aplică în descriere** cere
cel puțin o secțiune completată, omite secțiunile și pașii care conțin numai spații,
taburi sau linii goale și renumerotează pașii rămași. Conținutul completat își
păstrează diacriticele, liniile, spațiile și indentarea. Rezultatul este text simplu:

```text
Scop
Verificarea datelor primite.

Pasul 1
Încarcă fișierele.
    Notează separat înregistrările incomplete.

Pasul 2
Compară valorile.

Rezultat așteptat
Un raport cu diferențele explicate.
```

Dacă descrierea conține deja orice text, apare o alegere explicită:

- **Adaugă la final** este alegerea implicită, inclusiv pentru Enter inițial.
  Păstrează exact textul existent și separă noul conținut prin linii libere.
- **Înlocuiește descrierea** necesită alegerea explicită a acestui buton.
- **Anulează** revine la ghid cu ciorna lui intactă, fără să modifice descrierea.

Aplicarea schimbă bufferul comun PeerText într-o singură operație Undo și marchează
nodul ca nesalvat, inclusiv când textul rezultat este identic. Apare mesajul:
**„Aplicat în descriere. Salvează taskul pentru păstrare.”**
Nu se scrie pe disc și nu se salvează alte metadate la aplicare. Persistența rămâne
la **Salvează / Ctrl+S** existent, care salvează explicit și celelalte detalii deja
editate conform fluxului actual. Ctrl+S în interiorul ghidului sau al alegerii nu
salvează taskul. Undo/Redo din oricare vedere PeerText lucrează pe același document.

**Anulează / Escape / închiderea ghidului** abandonează doar formularul temporar,
fără a modifica textul, selecția, istoricul Undo, dirty state-ul sau discul.
Anularea editorului extins continuă să restabilească textul și dirty state-ul de
la deschiderea lui, inclusiv dacă în interior s-a aplicat ghidul; istoricul editării
extinse abandonate se resetează ca înainte. Focusul și grab-ul revin câte un nivel:
alegere → ghid → editor extins → editorul principal. Escape închide doar nivelul curent.

În read-only butonul este dezactivat. Aplicarea verifică din nou workspace-ul,
identitatea nodului și existența lui; dacă nodul a dispărut sau contextul s-a
schimbat, ciorna rămâne în ghid și nu se aplică. Dacă descrierea s-a schimbat între
deschiderea alegerii și confirmare, se cere reluarea aplicării, fără suprascriere.
Navigarea și închiderea obișnuită nu ocolesc un ghid deschis.

Ghidul nu are fișier sau copie persistentă proprie. Pașii lui nu creează checklist,
subtaskuri sau alte date. Formatarea textului este testabilă separat în
`ui/description_guide.py`; salvarea continuă prin DetailsTab și Workspace.

[Captură reală Tk pe date temporare demonstrative](capturi-ui/descriere-cu-ghid.png).

Verificare Linux/Xvfb: cele **30 de cazuri noi** pentru ghid sunt incluse în suita
completă: **339 trecute, 14 eșecuri preexistente pentru căi Windows, 1 omis**.
S-au verificat generarea, indentarea, pașii goi/reordonați/șterși, adăugarea și
înlocuirea explicită, ciorna izolată, anularea, Undo/Redo, PeerText, Ctrl+S existent,
read-only, nod dispărut inclusiv extern și restaurarea grab/focus în dialoguri
imbricate. Smoke-testul aplicației trece. Fără dependențe noi sau validare Windows.
