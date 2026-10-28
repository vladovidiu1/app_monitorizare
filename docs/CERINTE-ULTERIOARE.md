# Redeschidere și cerințe ulterioare

**Redeschide taskul** continuă cerința inițială: trece taskul în De făcut, fără să
reseteze descrierea, checklistul, fișierele, estimarea, sesiunile sau istoricul.
Finalizarea anterioară rămâne în istoric; `completed_at` curent se golește.
Acțiunea directă este rapidă; meniul oferă și **Redeschide cu motiv…**, cu notă
opțională. Arhivarea rămâne distinctă: redeschiderea nu dezarhivează automat.

**Adaugă cerință nouă…** creează o solicitare independentă, disponibilă din
inspector, spațiul taskului și meniul contextual, pentru taskuri deschise sau
finalizate. Sursa nu își schimbă statusul. Nu există remindere, recurențe sau
reveniri programate pentru acest mecanism.

## Creare și navigare

Dialogul cere titlu, permite descriere, solicitant prin componenta existentă,
prioritate și termen opționale. Implicit, destinația este containerul sursei,
nu taskul sursă. Dacă acesta este arhivat sau indisponibil, selectează explicit
o destinație activă. O sursă arhivată rămâne referință istorică.

Noul task are ID și timp propriu, status De făcut și prioritate Normală când nu
este specificată. Nu preia estimarea, sesiunile, istoricul, finalizarea, pinul
Astăzi sau starea de sincronizare. Descrierea și checklistul se preiau numai
prin opțiuni explicite; elementele copiate în checklist sunt toate nebifate.
Nu se creează dependențe de execuție.

Zona contextuală compactă oferă **Continuare a**, **Cerințe ulterioare** cu dată
și status, precum și acces la taskul inițial pentru lanțuri A → B → C.
Relația tipizată `continuation_of` păstrează sursa imediată, separat de ierarhie,
legături generice și dependențe. Sunt respinse autoreferințele și ciclurile.
Referințele indisponibile sunt explicite; restaurarea din coș reactivează
navigarea. Un intermediar indisponibil întrerupe descoperirea strămoșilor săi
până la restaurare; nu se inventează o altă sursă.

Timpul propriu salvat apare separat. Totalul lanțului este cerut explicit și
numără fiecare task o singură dată. Dashboardul continuă să însumeze sesiuni,
nu totaluri de lanț sau totaluri părinte/subtask.

## Acces la cod și versiuni

Implicit nu se preia accesul la cod, inclusiv prin moștenire de la proiect.
Opțiunea **Folder de cod comun** folosește aceeași sursă, fără copiere sau mutare.
O sursă managed păstrează identificatorul proprietarului și calea relativă;
o sursă external păstrează calea absolută. Lanțul de cerințe poate folosi același
proprietar al codului, fără a confunda proprietarul checkpointurilor.

Dacă folderul lipsește, dialogul explică problema: se poate alege alt folder,
crea fără acces sau păstra referința comună pentru recuperare ulterioară.
Ciorna rămâne în dialog la eroare. Checkpointurile unei cerințe noi sunt ale ei,
separate de checkpointurile sursei, și rămân consultabile dacă folderul de cod
nu mai poate fi rezolvat. Istoricul Git al folderului comun este comun și este
etichetat distinct de checkpointurile taskului.

Backupul complet include codul managed și păstrează referințele la restaurare.
Backupul doar de metadate nu include codul; directoarele external nu sunt copiate
și rămân referințe absolute. Coșul proprietarului managed face temporar codul
indisponibil, fără să șteargă cerințele sau checkpointurile lor.

## Fiabilitate și compatibilitate

Crearea folosește un UUID stabil de operație, ID de task și ID-uri de evenimente
deterministe. Planul recuperabil precedă scrierile atomice ale datelor autoritare.
Retry și dublu-click nu creează duplicate; după întrerupere, deschiderea workspace-ului
reia operația. Un task deja creat și mutat în coș nu este recreat automat.
Conflictul cu fișiere modificate extern oprește recuperarea, cu mesaj explicit.
Un formular poate corecta o cerere eșuată înainte de crearea oricărui artefact;
după începerea scrierilor, retry folosește planul inițial.

La final, jurnalul operației păstrează o chitanță compactă, nu o a doua descriere
persistentă. Indexurile sunt actualizate fără restart și rămân reconstructibile.
Modul read-only nu creează cerințe și nu execută recuperări cu scrieri.
Schema nodurilor rămâne compatibilă: câmpurile noi sunt opționale, cu valori
implicite pentru datele vechi. Nu sunt introduse baze de date sau dependențe.

Verificare în Linux/Xvfb: 382 teste reușite, 1 test Windows omis. Sunt acoperite
relațiile/ciclurile, copierea explicită, timpul independent, sursa comună,
checkpointurile, retry, întreruperile între scrieri, conflictele externe,
arhivarea, coșul, backup/restore, read-only și dialogurile cu ciornă.
Aceasta nu reprezintă validare a executabilului Windows.
