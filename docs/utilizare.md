# Ghid de utilizare

Sidebar: **Astăzi · Proiecte și taskuri · Calendar · Activitate**.
[Ghidul navigării, filtrelor și activității](NAVIGARE.md).

## Fluxul zilnic

1. **Captură rapidă**: `Ctrl+N` (titlu + locație; restul în „Mai multe detalii”) sau „+ Nou”. Taskurile noi sunt „De făcut” și apar în Proiecte și taskuri.
2. **Organizare**: arborele din stânga (foldere/categorii, proiecte, task-uri, subtask-uri). Meniu contextual (clic
   dreapta): task/subtask nou, folder/proiect nou, redenumește (`F2`), mută…, legătură…, arhivează, în coș, deschide
   folderul nodului, deschide codul în VS Code. Un task poate fi **legat** de un proiect fără a fi copiat.
3. **Astăzi** (pagina inițială): maximum 3 priorități marcate de tine, sesiunile planificate, întârzierile și butonul
   „Reia lucrul”. Timp rămas necunoscut = „Neestimat”, nu 0.
4. **Începe sesiune** (`▶`): alegi, la cerere, ce se deschide (cod în VS Code, folder în Explorer, fișiere atașate —
   scripturile nu se deschid automat). Există un singur timer activ. Pauză/continuă/oprește din Organizare › Sesiune de
   lucru. La oprire: ce ai făcut, următorul pas, timp rămas, status; se poate salva un checkpoint al codului.
5. **Planificare**: Calendar (agendă), programare manuală, planificare asistată (determinist, cu previzualizare), export
   `.ics`, opțional Outlook Classic.
6. **Versiuni**: tabul „Versiuni” — checkpoint-uri, comparație, restaurare în folder separat; secțiune Git opțională.

## Inspector (dreapta)

Detalii · Subtaskuri (+ checklist) · Activitate (jurnal și sesiuni) · Fișiere · Planificare · Versiuni.
Modificările din „Detalii” se salvează cu `Ctrl+S` (nu la fiecare tastă).
Dacă schimbi selecția cu modificări nesalvate, aplicația întreabă.

## Scurtături

`Ctrl+N` task nou · `Ctrl+F` căutare globală (titlu, descriere, etichete, următorul pas) · `Ctrl+S` salvează · `Ctrl+M`
trimite e-mail din task · `Insert` în listă = câmpul de adăugare rapidă · `Alt+→` / `Alt+←` subtask / scoate un nivel · `F2`
redenumește · `F5` reîmprospătează · `Esc` în căutare golește · `Ctrl+Enter` în jurnal adaugă notița.

## Task-uri și subtask-uri la orice nivel

Selectează un proiect (sau folder) în arbore: lista din mijloc arată **ierarhia lui** (proiect › task › subtask › …), cu
sgeți de închidere/deschidere și progres (`făcute/total` pe frunze). Deasupra listei este câmpul de **adăugare rapidă**:

* scrii titlul și apăsi Enter → se creează un **subtask al task-ului selectat** (dacă nu e selectat niciun task, un task direct
  în proiect). Selecția rămâne pe loc, deci poți adăuga mai multe subtask-uri la rând; selectează subtask-ul nou ca să-i adaugi
  sub-subtask-uri, fără limită de adâncime;
* „Aici” / „La nivelul listei” creează task-ul direct sub proiectul afișat;
* ▲ ▼ schimbă ordinea, ▶ (`Alt+→`) face task-ul subtask al celui de deasupra, ◀ (`Alt+←`) îl scoate un nivel;
* „Mută…” (meniul contextual) mută un task oriunde, cu tot cu subtask-uri.

Clic pe titlul unei coloane sortează frații; al treilea clic revine la ordinea manuală.

## E-mail din task

Selectează un task → `Ctrl+M` sau „✉ E-mail”: completezi destinatarul (adrese separate prin `;` sau `,`), verifici subiectul și
textul (contextul task-ului este deja inclus) și alegi „Trimite” (cu confirmare) sau „Deschide ciorna în Outlook”. Necesită
Outlook Classic pornit/instalat; trimiterea se notează în Activitatea taskului. Vezi [diagnostic-integrari.md](diagnostic-integrari.md).

### Colegi și solicitant

1. Deschide **Setări › Colegi › Încarcă Excel colegi…** și alege un fișier `.xlsx`. Prima foaie trebuie să aibă numele
   complet în coloana A și codul în coloana B (fără `@eon.com`). Poți include antetul `Nume complet` / `Cod`.
2. Lista se salvează imediat în workspace, independent de butonul „Salvează” al setărilor. Rămâne disponibilă după
   repornire; luna următoare încarci noul Excel din același loc, iar lista veche este înlocuită. Un import invalid nu
   modifică lista existentă. Formatul vechi `.xls` trebuie salvat mai întâi ca `.xlsx` în Excel.
3. În **Detalii › Cine a solicitat**, apasă „…” și caută după nume sau cod, apoi selectează colegul. Salvează task-ul cu
   `Ctrl+S`. „✕” elimină solicitantul. Câmpul există și în „Task nou › Mai multe detalii”.
4. La deschiderea mailului, câmpul „Către” este completat cu `cod@eon.com` pentru solicitant. Butoanele „…” de lângă
   „Către” și „CC” permit adăugarea altor colegi din listă; adresele pot fi și editate manual. Nu se trimite nimic automat.

## Statusuri și priorități

Statusuri: De făcut, În lucru, În așteptare, În testare, Finalizat, Anulat. Arhivarea este separată de status. Priorități:
Urgentă, Ridicată, Normală, Redusă (afișate ca text, nu doar culoare). Un task blocat are motiv, dependențe și dată de
revenire; dependențele nu pot forma cicluri, iar un task cu dependențe nefinalizate se programează doar prin suprascriere
explicită.

## Fișiere

* **Copie administrată**: fișierul se copiază în `files/` al nodului (intră în backup-ul complet).
* **Legătură externă**: se memorează doar calea; dacă lipsește apare „Lipsește” și poate fi relocalizată. Ștergerea
  legăturii nu șterge fișierul original.
* **Folder de cod**: asociat unui proiect, este moștenit de subtask-uri fără a copia sursele; un task poate seta altul.

## Backup

Fișier › Backup acum (metadate sau complet); zilnic la prima pornire a zilei (configurabil), cu retenție. Un folder extern
opțional (alt disc/partajare) — un backup pe același disc nu protejează de defectarea discului. „Restaurează backup într-un
folder nou” nu suprascrie niciodată workspace-ul curent.

## Instrumente

* Verificare integritate (probleme detectate la încărcare; nimic nu se șterge automat).
* Setări: program de lucru (fus `Europe/Bucharest`, pauze, zile nelucrătoare, durate sesiune, rezervă zilnică), backup,
  checkpoint-uri, Outlook, VS Code.
* Aspect luminos FocusDesk (configurațiile dark vechi sunt acceptate), arată/ascunde inspectorul, arată elemente arhivate.
## Modificări făcute în Explorer

Aplicația nu urmărește folderele în timp real. După modificări externe: Fișier › Rescanează workspace. Dacă un `node.json`
a fost editat extern și apoi încerci să-l salvezi din aplicație, ți se cere reîncărcarea (nu se suprascrie silențios).


Evenimentele Outlook/ICS sunt rezervări personale de timp, fără invitați sau Teams.

## Descriere și identificarea statusului

În Detalii poți redimensiona descrierea sau folosi **Extinde descrierea**. Toolbarul
editează Markdown, iar tabul Previzualizare îl formatează local. Ctrl+S salvează;
anularea ferestrei extinse revine la textul de la deschidere. Căsuțele Markdown
sunt documentare, distincte de checklistul funcțional al taskului.
Pictogramele și etichetele disting statusurile; inspectorul oferă Redeschide taskul.
[Ghid complet și scurtături](DESCRIERE-MARKDOWN.md).
