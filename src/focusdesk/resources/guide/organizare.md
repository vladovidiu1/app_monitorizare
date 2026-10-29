# Proiecte, taskuri și subtaskuri

## La ce folosește
Un proiect grupează cerințe. Un task are status, descriere și muncă proprie; subtaskurile permit descompunerea. Folderele/categoriile organizează containerele. Nu este obligatoriu să creezi un proiect pentru fiecare task independent.

## Unde îl găsești
**Proiecte și taskuri**, **+ Nou**, meniul **Organizare** și meniul contextual. Filtrele rapide includ **Toate**, **În așteptare**, **Restante** și **Finalizate**. Comutatorul **Închise** include finalizatele/anulatele; arhivarea rămâne separată.

## Tutorial A: proiect SAP și primul task
1. Alege **+ Nou → Proiect**.
2. Scrie `Automatizare raport SAP` la **Titlu**, verifică **Locație** și apasă **Creează**.
3. Selectează proiectul și alege **+ Nou → Task** sau **Ctrl+N**.
4. Scrie `Verifică extragerea raportului`, alege proiectul la **Locație** și apasă **Creează**. **Mai multe detalii** oferă câmpuri opționale.
5. Pentru un subtask selectează taskul și alege **+ Nou → Subtask în selecția curentă**. Exemplu: `Verifică regulile de filtrare`.
6. Selectează taskul, completează **Următorul pas**, apoi salvează cu **Ctrl+S**.

## Rezultatul și salvarea
Arborele/lista arată proiectul și cerințele în ierarhie. **Creează** salvează nodul nou imediat; schimbările ulterioare din Detalii cer salvare. Câmpul de adăugare rapidă afișează destinația; Enter poate crea subtaskul taskului selectat, iar **La nivelul listei** alege containerul afișat.

## Mutare, legături și solicitant
**Organizare → Mută…** schimbă părintele/apartenența; **Adaugă legătură…** este o referință și nu mută taskul în proiect. **Fără proiect** verifică apartenența actuală, nu legăturile. **Alt+→** face subtask al celui de deasupra când este valid; **Alt+←** scoate un nivel.

În **Detalii → Cine a solicitat**, selectorul permite alegerea unui coleg. Importul listei este în [Setări](guide:setari#colegi-si-solicitant), iar alegerea solicitantului în task se păstrează prin salvarea taskului.

## Greșeli frecvente
Pașii scriși în descriere nu creează subtaskuri. Checklistul este o structură separată. Finalizarea nu înseamnă ștergere; vezi [finalizare și cerințe ulterioare](guide:cerinte).
