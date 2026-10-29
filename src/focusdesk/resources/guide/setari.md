# Setări și integrări

## La ce folosește
Setările descriu mediul tău de lucru și integrările opționale. Funcțiile locale nu cer Outlook sau conectare cloud.

## Unde îl găsești
**Setări** în stânga sau **Instrumente → Setări…**. Secțiunile existente includ **General**, **Colegi**, **Program de lucru**, **Backup**, **Versiuni & VS Code** și configurarea Outlook.

## Pași pentru configurare
1. Verifică numele workspace-ului, fusul orar și numărul maxim de priorități zilnice în **General**.
2. În **Program de lucru** verifică zilele, intervalele, pauzele și excepțiile; acestea influențează planificarea, nu pornesc lucrul automat.
3. Configurează **Backup** și **Versiuni & VS Code** numai pentru locații pe care le poți accesa.
4. Salvează prin **Salvează**. Citește confirmările/erorile și verifică rezultatul în funcția relevantă.

## Colegi și solicitant
**Colegi → Încarcă Excel colegi…** importă un .xlsx local, prima foaie cu numele în coloana A și codul în B. Codul nu conține domeniul; selectorul existent formează adresa conform convenției aplicației. Importul înlocuiește lista locală imediat, separat de butonul Salvează al setărilor; un import invalid păstrează lista veche. Alegerea solicitantului în task se salvează împreună cu taskul. Nu presupune că importul trimite mesaje.

## Outlook Classic și lucru offline
Integrarea COM necesită Outlook Classic și componentele pywin32 în distribuție. New Outlook nu suportă acest mecanism. Importul întâlnirilor citește doar calendarul ales și păstrează notițele local; trimiterea e-mailului este explicită și separată.

Calendarul rezervărilor și sursa importului întâlnirilor sunt alegeri distincte. Un export ICS necesită import și nu este sincronizare garantată. FocusDesk nu confirmă livrarea e-mailului sau sincronizarea serverului Exchange după un apel local reușit.

Fără Outlook poți organiza taskuri, lucra cu timerul, consulta Activitate, edita notițe locale și crea întâlniri manuale. Pentru e-mailurile Outlook și un import nou din Outlook, absența integrării trebuie remediată; nu există un backend cloud ascuns.

## Greșeli frecvente
Nu schimba fusul orar ca să repari arbitrar un total istoric. Nu confunda importul listei de colegi, care se salvează imediat, cu o ciornă de Setări. La erori COM sau module lipsă vezi [Probleme și limitări](guide:probleme).
