# Descriere, ghid de completare și salvare

## La ce folosește
Descrierea păstrează scopul și cerințele într-un singur câmp editabil. Poți scrie text și Markdown literal; nu există bara Bold/Italic sau file Editare/Previzualizare. Inspectorul, spațiul taskului și editorul extins împart același buffer.

## Unde îl găsești
**Detalii → Descriere**, **Deschide spațiul de lucru** și **Extinde descrierea**. Lângă Descriere este **Completează cu ghid…**; acest formular este diferit de ghidul general de utilizare.

## Tutorial B: descriere ghidată
1. Deschide taskul `Verifică extragerea raportului` și apasă **Completează cu ghid…**.
2. La **Scop** scrie `Verificarea datelor exportate din SAP`.
3. Completează **Pasul 1** cu `Compară filtrul cu cerința` și **Pasul 2** cu `Verifică valorile din documentul exemplu`.
4. Folosește **+ Adaugă pas**, ștergerea și mutarea sus/jos dacă ai nevoie. Pașii complet goi sunt eliminați și numerotarea se reface.
5. La **Rezultat așteptat** scrie `Reguli confirmate și diferențe documentate`.
6. Apasă **Aplică în descriere**. Dacă există text, alege explicit adăugarea la final, înlocuirea sau anularea; implicit se adaugă.
7. La mesajul **Aplicat în descriere. Salvează taskul pentru păstrare.**, apasă **Salvează** sau **Ctrl+S**.

## Ce trebuie să vezi
Textul simplu are secțiuni Scop, Pasul 1, Pasul 2 și Rezultat așteptat. Aplicarea este o singură operație Undo. Tastarea în formular nu modifică descrierea până la aplicare; anularea ghidului nu schimbă bufferul sau discul.

## Ce se salvează și când
Aplicarea modifică doar ciorna comună. **Ctrl+S** folosește salvarea existentă a taskului și poate salva și celelalte metadate editate din Detalii: verifică-le înainte. Deschiderea ghidului general nu le salvează. Anularea editorului extins revine la snapshotul de la deschidere, inclusiv după folosirea formularului ghidat în interior.

## Greșeli frecvente
Nu confunda descrierea cu checklistul funcțional sau cu subtaskurile. Undo/Redo modifică textul din buffer; o schimbare salvată pe disc nu se șterge prin închiderea ghidului general. [E-mailul folosește un snapshot separat](guide:email).
