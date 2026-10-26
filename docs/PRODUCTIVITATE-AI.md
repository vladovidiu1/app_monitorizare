# E-mail, pregătirea zilei și rapoarte

Funcțiile folosesc motorul GGUF local, bugetul de context cu rezervă pentru răspuns,
sursele validate și `ProposalBatch` existente. Niciun răspuns AI nu trimite mailuri,
nu salvează sesiuni și nu modifică taskuri automat. Inferența rămâne în proces separat;
recuperarea datelor se face în fundal, iar UI validează rezultatul. Anularea și
schimbarea workspace-ului invalidează cererile și ignoră răspunsurile întârziate.

## Redactare e-mail

În **E-mail din task**, alege Actualizare progres, Solicitare clarificări, Follow-up
sau Anunț de finalizare și apasă **Generează cu AI**. Contextul include taskul,
jurnalul și sesiunile relevante, cu limitele de recuperare ale asistentului.
Finalizarea poate fi anunțată numai dacă taskul are status Finalizat. Ciornele care
sugerează finalizare pentru un task deschis sau introduc promisiuni sunt respinse
conservator. Referințele și cifrele trec prin validatorul comun; acestea nu reprezintă
o garanție semantică a textului generat. Citește sursele și verifică formulările.

Fereastra AI oferă o previzualizare editabilă și surse navigabile. **Folosește ciorna**
cere confirmare înainte de înlocuirea subiectului/corpului din editor. Destinatarii
nu sunt aleși sau modificați de AI. Editorul păstrează validarea adreselor și
confirmarea existentă înainte de **Trimite**. **Deschide ciorna în Outlook** păstrează
fluxul existent de ciornă. Se creează un **mesaj nou**, nu Reply/ReplyAll în firul
original; interfața precizează această distincție.

## Pregătește-mi ziua

În **Astăzi → Pregătește-mi ziua**, scrie cererea. Queries selectează un set limitat
de candidați deschiși (maximum 12), cu termene, timp rămas și blocaje. Modelul alege
maximum trei taskuri, fiecare cu justificare și sursa sa. ID-uri necunoscute,
duplicate sau o listă mai mare sunt respinse. Se revalidează reviziile și blocajele
înainte de continuare.

**Previzualizează în Planner** deschide planificatorul existent, cu selecția AI și
perioada limitată inițial la azi. Poți schimba selecția/perioada explicit. Planner,
nu modelul, calculează intervalele, pauzele, capacitatea, termenele, dependențele și
conflictele cu sesiunile sau disponibilitatea Outlook. Taskurile neestimate rămân
nealocate și cer estimare introdusă explicit; AI nu inventează minute. Taskurile
blocate păstrează regulile existente ale Planner/SessionService. Planificarea unei
dependențe nu înseamnă finalizarea ei și nu autorizează începerea taskului dependent.

Nicio sesiune nu este salvată la primirea răspunsului AI. Verifică estimările,
apasă **Calculează propunerea**, apoi verifică și aplică sesiunile selectate prin
fluxul existent. Bifa calendarului și sincronizarea Outlook/ICS păstrează comportamentul
existent. Aceste evenimente sunt **rezervări personale de timp**, fără invitați,
întâlniri Teams sau promisiunea unei întâlniri cu colegii.

## Rapoarte zilnice și săptămânale

În **Astăzi → Raport zilnic / săptămânal**, Zilnic înseamnă azi în fusul workspace-ului;
Săptămânal înseamnă ultimele șapte zile inclusiv azi. **Calculează fără AI** produce
raportul numeric și funcționează fără model. **Generează cu AI** adaugă explicația,
păstrând registrul calculat complet în previzualizare.

Cifrele sunt calculate în cod prin `Queries.worked_by_day`:

- Se însumează numai `actual_seconds > 0` salvate. Durata planificată și timpul live
  nesalvat nu intră în raport.
- Sesiunea este atribuită integral zilei `started_actual_at`, cu fallback `start_at`,
  în fusul workspace-ului, conform regulii existente. Nu se împarte artificial la miezul nopții.
- Timpul propriu al părintelui și al subtaskurilor este numărat o singură dată;
  totalul nu însumează rollup-uri din ierarhie.
- Taskurile finalizate în perioadă au status curent Finalizat și `completed_at`
  în perioadă. Un task redeschis nu este raportat ca finalizat în starea curentă.
- Sunt incluse taskurile lucrate, finalizările și blocajele înregistrate, cu pașii
  următori salvați. Taskurile arhivate păstrate în workspace sunt incluse.

AI primește totalurile calculate și cel mult șase detalii de task; explicația poate
fi parțială, dar registrul afișat în cod rămâne complet. Sursele conțin ID-urile
taskurilor și sesiunilor. Lista de surse deschide taskurile și raportul calculat.
Modificarea datelor invalidează sursa raportului și cere recalculare înainte de
pregătirea mailului. Textul poate fi editat și copiat explicit.

**Pregătește e-mail** deschide editorul existent cu raportul și fără destinatari
presupuși. Funcționează inclusiv fără taskuri și nu asociază raportul global arbitrar
jurnalului unui task. Trimiterea rămâne exclusiv manuală, după validare și confirmare.

## Verificare

`tests/test_ai_productivity.py` verifică date lipsă, secunde exacte, atribuirea pe zi,
finalizări, revizii/sesiuni modificate, limita de priorități, taskuri neestimate,
dependențe și lipsa suprapunerilor. `tests/test_productivity_ui.py` folosește Tk real
și răspunsuri AI simulate pentru previzualizare, editare, copiere, anulare și lipsa
trimiterilor/aplicărilor automate.

Smoke opțional cu model GGUF real, workspace temporar și fără Outlook:

```sh
python scripts/smoke_productivity.py --mode all
```

Acesta validează ciorna, selecția și raportul fără a le aplica. Rezultatele efectiv
executate și limitele platformei sunt documentate în [RAPORT.md](RAPORT.md).
