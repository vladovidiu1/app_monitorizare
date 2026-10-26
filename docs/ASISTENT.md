# Asistent FocusDesk

Butonul **Asistent** din bara principală deschide o fereastră de chat **nemodală**: poți continua
editarea taskurilor în timpul generării. Același chat este disponibil în tabul **Asistent** din
inspectorul taskului/proiectului. AI se activează și se configurează în Setări → AI, folosind
motorul local și GGUF-ul descrise în [AI.md](AI.md).

## Context vizibil și acțiuni rapide

Selectorul **Context** arată explicit **Task selectat**, **Proiect** sau **Întreg workspace**,
împreună cu titlul și ID-ul țintei. Contextul de proiect se rezolvă la proiectul cel mai apropiat.
„Întreg workspace” permite căutarea în workspace, dar transmite numai înregistrări relevante,
nu toate datele. Schimbarea contextului anulează cererea în curs și golește memoria conversațională
trimisă modelului. Schimbarea workspace-ului invalidează și șterge conversațiile, iar rezultatele
ulterioare ale cererilor vechi sunt ignorate.

* **Unde am rămas?**: context task; ultimele notițe/sesiuni, următorul pas și blocajele.
  Interfața afișează și înregistrările concrete consultate, chiar dacă rezumatul modelului este foarte scurt.
* **Propune pași**: propuneri de subtaskuri și checklist/următor pas. Nu poate schimba statusul sau termenele.
* **Rezumă proiectul**: schimbă vizibil contextul la Proiect; progresul este calculat prin Queries.
* **Pregătește e-mail**: numai subiect/text de ciornă. Butonul E-mail deschide, după confirmare,
  editorul existent. Destinatarii rămân sub controlul utilizatorului; nimic nu se trimite automat.

Poți scrie întrebări și cereri proprii. De exemplu, alege **Întreg workspace** și întreabă
„Ce taskuri am de la colegul Ana Popescu?”. Căutarea solicitantului folosește numele/codul salvat
în task, ignorând diferențele de majuscule și diacritice. Căutarea lexicală prioritizează titlul,
etichetele, următorul pas, solicitantul și blocajele. Nu există bază vectorială sau căutare semantică
garantată în toate descrierile. Descrierile sunt recuperate pentru candidații selectați.

Pentru modificări scrise în chat, folosește o cerere explicită precum „Propune un task…”,
„Adaugă o notiță…”, „Actualizează…” sau „Leagă…”. Cererile de consultare au o schemă care interzice
acțiunile, iar răspunsul este verificat din nou în procesul aplicației. Contextul fără surse întoarce
un mesaj de clarificare, fără încărcarea modelului sau creare de taskuri fără fundament.

## Surse și buget

Recuperarea folosește **Queries**, **Workspace** și **SessionService**, în fundal prin UiBridge.
Sunt selectați maximum 8 candidați inițiali, plus dependențe până la 12 noduri, și maximum
12 înregistrări recente de jurnal/sesiuni/istoric de status. Descrierile și textele lungi sunt limitate.
Payload-ul de recuperare este plafonat la aproximativ 24 KB; nu sunt citite codul, atașamentele sau inboxul.
Citirea înregistrărilor verifică anularea între fișiere. Metadatele și stocurile existente pot fi scanate
pentru selecție/agregare; acest lucru nu înseamnă că întregul conținut ajunge în prompt.

Procesul AI randază template-ul Qwen3 fără thinking, **tokenizează promptul efectiv**, păstrează
o rezervă de **1024 tokeni pentru răspuns plus 16 de siguranță**, apoi elimină întâi mesajele vechi
și sursele cu prioritate mai mică până încape. Doar ID-urile surselor efectiv trimise rămân eligibile
pentru citare sau acțiuni. Răspunsul IPC include aceste ID-uri și numărul real de tokeni, stabilite
de runtime, nu de textul generat de model. La depășirea bugetului fără surse utile se cere un context mai mic.

Fiecare paragraf/acțiune/ciornă citează chei de sursă verificate. Legăturile afișează UUID-urile
și deschid taskul sau **înregistrarea exactă** din jurnal/sesiuni/istoric, într-o fereastră de citire.
Sursele sunt verificate pentru existență, proprietar, revizie/fingerprint și conținut neschimbat.
O sursă omisă din prompt nu este acceptată doar pentru că exista în selecția inițială.

Timpul afișat provine din `actual_seconds`, nu din durata planificată. Progresul proiectului provine
din agregarea Queries pe taskurile frunză. Datele deterministe sunt afișate lângă interpretarea AI.
Un filtru conservator respinge numere nesusținute de sursele citate și afirmații explicite că asistentul
ar fi verificat cod necitit. Acesta **nu demonstrează adevărul semantic al fiecărei fraze**: verifică sursele;
modelul poate greși sau omite detalii. Nu se afirmă că datele nevăzute într-un context parțial au fost analizate.

Conținutul taskurilor, notițelor, conversației anterioare și ciornelor este date, nu autoritate pentru
schimbarea regulilor. Tokenii de control Qwen sunt neutralizați în date. Modelul nu primește API-uri
pentru shell, rulare de cod, ștergere, restaurări, trimitere de mesaje sau scriere directă în workspace.

## Propuneri comune și rezultate parțiale

Butonul **Propuneri…** deschide lista de revizuire cu **înainte/după**, motiv, surse și țintă.
Poți **Accepta**, **Modifica** sau **Respinge** fiecare propunere; există și acceptare pentru lot.
Editorul folosește câmpuri și opțiuni, nu JSON de editat manual.

Operațiile permise sunt tipizate:

| Operație | Limite |
|---|---|
| Creare task | Părinte existent în context; creare la rădăcină numai în context workspace; descriere/checklist |
| Actualizare task | titlu, status, prioritate, următor pas, motiv blocaj, termen fără oră, estimări, etichete, checklist |
| Notiță | adăugare în jurnalul unui task/nod validat |
| Legături | între taskuri existente din context; relație sau dependență, fără cicluri |

Pașii noi generați pornesc nebifați. Actualizarea checklistului păstrează elementele existente și starea
lor, adăugând pașii noi; nu șterge progresul existent. Modificările făcute explicit de utilizator în
editor sunt validate din nou. Ciclurile între mai multe propuneri sunt verificate înainte de aplicare.
Nu există operații pentru ștergerea/mutarea nodurilor, restaurări, căi de fișiere, comenzi sau ID-uri arbitrare.

Identitatea workspace-ului, țintele, sursele, dependențele și reviziile se verifică înainte de aplicare.
O editare ulterioară, inclusiv externă, invalidează propunerea: **recalculează**, nu suprascrie.
Modificările produse chiar de operațiile deja acceptate în același lot sunt recunoscute separat,
astfel încât următoarea operație pe același nod să nu fie respinsă fals ca învechită.

Fiecare operație primește un UUID de la aplicație. La acceptare, **Workspace scrie mai întâi o rezervare
în istoricul persistent**, cu operația și previzualizarea, apoi efectuează operația pe firul Tk și salvează
rezultatul. O rezervare existentă nu se execută din nou, inclusiv după repornire. Dacă aplicația cade
între scriere și confirmarea rezultatului, starea rămâne **incertă** și necesită verificare manuală;
nu se reia automat. Nu există promisiune de rollback atomic pentru un lot.

Rezultatele sunt raportate per operație: aplicată, respinsă, conflict, neexecutată sau incertă.
Succesele anterioare rămân raportate ca succese. După un rezultat incert, restul lotului se oprește;
nu se declară greșit că nimic nu s-a modificat. **Istoric propuneri…** arată rezultatele și rezervările
incomplete, inclusiv după repornire. Evenimentele sunt în stocul existent `_system/history`, deci intră
în backupurile obișnuite. Dialogul AI inițial folosește acum același mecanism de aplicare/istoric.

Ciorna de e-mail rămâne text de revizuit în chat și apoi în editorul de e-mail existent. Trimiterea
reală continuă exclusiv prin OutlookController/ComWorker și confirmările existente; jurnalul trimiterii
se actualizează numai după succesul raportat de integrarea existentă.

## Verificare

```powershell
python -m pytest -q tests/test_assistant_services.py tests/test_assistant_ui.py tests/test_assistant_runtime.py tests/test_assistant_additional.py tests/test_assistant_receipt_failure.py
# Opțional, cu GGUF real; lucrează doar în workspace temporar, fără acceptarea propunerilor:
python scripts/smoke_assistant.py --mode answer
python scripts/smoke_assistant.py --mode steps
python scripts/smoke_assistant.py --mode email
# Aceeași cale din executabil, cu PATH gol:
python scripts/verify_ai_exe.py --exe <FocusDesk.exe> --model <GGUF> --assistant-mode answer
```

Testele acoperă surse și proprietari falși, surse eliminate din prompt, buget exact, intenții numai
pentru consultare, câmpuri interzise, cicluri, conflicte, editare/respingere, repetare după redeschidere,
scriere urmată de eroare, pierderea confirmării din istoric și ignorarea răspunsurilor după schimbarea
workspace-ului. Vezi [RAPORT.md](RAPORT.md) pentru ce s-a rulat efectiv și limitele Windows/Outlook.

## E-mail, ziua și rapoarte cu AI

Editorul de mail oferă patru moduri de redactare AI. În Astăzi găsești
„Pregătește-mi ziua” (selecție AI, calcul Planner) și raport zilnic/săptămânal
cu cifre calculate din timpul efectiv înregistrat. Toate au previzualizare;
trimiterea și salvarea rămân explicite. Vezi [ghidul funcțiilor](PRODUCTIVITATE-AI.md).
Evenimentele Outlook/ICS sunt rezervări personale de timp, fără invitați sau Teams.
