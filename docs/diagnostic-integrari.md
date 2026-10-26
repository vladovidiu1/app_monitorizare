# Diagnostic integrări și teste manuale pe calculatorul țintă

Funcțiile principale nu depind de nicio integrare. Mai jos: ce este opțional, cum se diagnostichează și ce trebuie
verificat manual pentru că nu a putut fi verificat automat în acest repository.

## Outlook Classic (COM, pywin32) — NEVERIFICAT pe un Outlook real

Implementat: `integrations/outlook.py` (logică, testată cu backend fals), `integrations/outlook_com.py` (COM real, **neexecutat
în testele automate**), `workers/com_worker.py` (thread COM, testat), `services/calendar_sync.py` (testat).

Ce face: citește disponibilitatea dintr-un interval limitat (cu recurențe expandate, evenimente all-day, politici pentru
Provizoriu și „Lucrez din altă locație”), creează programări **personale** (fără participanți, fără link Teams, „Ocupat”,
memento configurabil) în calendarul ales cu `calendar.Items.Add` + `Save()` (calendarul nu folosește `Send()`; singura trimitere
de mesaje este dialogul de e-mail de mai jos), le marchează cu
`FocusDeskSessionId` și `FocusDeskWorkspaceId`, le regăsește după UUID la reîncercare și actualizează/anulează doar
elementele cu markerii proprii. Dacă utilizatorul le mută/șterge/modifică în Outlook apare un **conflict** cu opțiunile
„Preia din Outlook”, „Aplică planul local”, „Detașează”; evenimentele șterse nu se recreează automat.

Ce nu garantează: `Save()` confirmă doar salvarea în Outlook local — nu sincronizarea serverului Exchange și nu prezența în
Teams. Nu se simulează „Nu deranjați”.

### Test manual (într-un calendar de TEST)

1. Setări › Outlook › „Testează Outlook și alege calendarul…”. Rezultat așteptat: „Outlook Classic răspunde prin COM”,
   lista de calendare cu tipul (Exchange / fișier local). Alege calendarul de serviciu Exchange/M365 sau, pentru test, un
   calendar creat special. Dacă apare eroare `Invalid class string` / „Outlook.Application indisponibil”: nu este Outlook
   Classic (New Outlook nu suportă COM) → folosește exportul `.ics`.
2. Programează o sesiune de test cu „Rezervă timp în calendar”, apoi Calendar › „Sincronizează cu Outlook”. Verifică în
   Outlook: titlul `[FocusDesk] Lucru — <task>`, „Ocupat”, fără participanți/Teams, descrierea cu UUID-uri fără căi locale.
3. Apasă din nou „Sincronizează” — nu trebuie să apară un duplicat.
4. Mută evenimentul în Outlook, apoi modifică sesiunea local și sincronizează → conflict; încearcă fiecare rezolvare.
5. Șterge evenimentul în Outlook și sincronizează → conflict (fără recreare automată).
6. Anulează sesiunea local → evenimentul ajunge în „Elemente șterse”.
7. Verifică formatul datei din filtrul COM (`Items.Restrict`) cu setările regionale reale (aplicația folosește formatul
   regional Windows și, dacă filtrul eșuează, o iterare limitată). Planificarea asistată trebuie să afișeze „Disponibilitate
   verificată în Outlook” doar după o citire reușită.
8. Verifică dacă politicile companiei permit automatizarea COM (pot apărea avertismente de securitate Outlook; aplicația
   nu încearcă să le ocolească).

Puncte de atenție la verificare: conversia fusului orar (aplicația scrie `datetime` naive în ora locală a sistemului),
`UserProperties.Find`, `GetItemFromID` pentru elemente șterse (se tratează ca „șters” dacă folderul părinte nu este de tip
calendar), calendare moștenite/delegate.

## ICS (fără Outlook COM)

„Exportă ICS…” scrie un fișier iCalendar valid (`icalendar`): UID stabil derivat din workspace+sesiune, DTSTAMP, DTSTART/DTEND
în UTC, SEQUENCE crescător, SUMMARY, DESCRIPTION cu escaping și line folding, `TRANSP:OPAQUE`, plus
`X-MICROSOFT-CDO-BUSYSTATUS:BUSY`. Starea afișată este **„Exportat — necesită import în calendar”**; exportul nu este
sincronizare, iar reimportul actualizărilor/anulărilor depinde de clientul de calendar (nu este upsert garantat). Un adaptor
de email pentru trimiterea ICS este doar o interfață documentată (`EmailAdapter`), dezactivată implicit, fără implementare:
configurația mecanismului existent de email trebuie furnizată de utilizator; faptul că se poate trimite email nu înseamnă drept
de scriere automată în calendar.

## E-mail din task (Outlook Classic, COM) — NEVERIFICAT pe un Outlook real

Implementat: `services/mail.py` (adrese, subiect, text implicit — testat), `integrations/outlook_com.py::send_mail`
(COM real, **neexecutat în testele automate**), `ui/mail_ui.py` (dialog), `OutlookController.send_mail` (testat cu backend fals).

Flux: task selectat → buton „✉ E-mail” / Ctrl+M / clic dreapta › „Trimite e-mail…”. Dialogul propune subiectul
„Nelămuriri: <task>” și un text cu contextul task-ului (locație, status, termen, următorul pas, descriere limitată), editabil.
„Trimite” cere confirmare și trimite din contul implicit Outlook; „Deschide ciorna în Outlook” lasă mesajul deschis pentru
ajustări (nu se trimite nimic). Enter nu trimite din greseală. Dacă Outlook nu poate rezolva un destinatar, **nu se trimite
nimic**. După o trimitere reușită se adaugă o înregistrare „Acțiune” în Activitatea taskului. La timeout (Outlook blocat de un
dialog) aplicația nu spune dacă mesajul a plecat: verifică „Elemente trimise”.

Test manual: (1) „Deschide ciorna” cu un destinatar — trebuie să se deschidă o fereastră de mesaj nou cu subiectul/textul;
(2) trimite-ți ție un mesaj de test cu „Trimite” și verifică „Elemente trimise” și Activitatea taskului; (3) încearcă o adresă inexistentă
și o adresă invalidă (fără @) — trebuie refuzate; (4) dacă politica companiei afișează un avertisment de securitate Outlook la
automatizare, aplicația nu îl ocolește. Mesajul se trimite ca text simplu; semnătura implicită din Outlook poate lipsi în
modul „Trimite” (o poți scrie în mesaj sau folosi ciorna) — de verificat pe Outlook-ul real.

## Git și VS Code

Git este opțional (`git` în PATH): status, log, diff, comparație cu sesiunile task-ului și **commit manual** cu fișiere
alese explicit și mesaj propus. Nu există `git add .`, push, reset, stash sau checkout automate. VS Code: detectat automat
(`Code.exe`) sau ales în Setări; pornit cu listă de argumente, fără shell. Procesul local vede doar fișierele **salvate**;
Auto Save din VS Code este recomandat, dar aplicația nu schimbă setările VS Code.

## Executabilul

Verifică pe un calculator fără Python: pornește `FocusDesk.exe`, creează un workspace gol, un proiect/task/subtask, închide
și redeschide (datele și ordinea se păstrează), pornește o sesiune, salvează un checkpoint. Pictograma și resursele trebuie
să se încarce; datele rămân în folderul workspace-ului.
