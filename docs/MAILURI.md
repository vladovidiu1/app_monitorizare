# Monitorizare Outlook Classic și analiză locală

Pagina **Mailuri de analizat** este separată de Inbox-ul taskurilor. Integrarea este
opțională și dezactivată implicit. Necesită **Outlook Classic pentru Windows**, cu
profilul deschis și conectat. New Outlook nu oferă acest COM; Microsoft Graph nu
este folosit. FocusDesk nu pornește Outlook pentru citirea mailurilor.

## Configurare și utilizare

În **Setări → Mailuri**, activează explicit monitorizarea, enumeră conturile și
alege un singur mailbox și folderele sale. Configurează intervalul, perioada primei
scanări și plafonul inițial **per folder**, mărimea paginii și plafonul per verificare.
Implicit: ultimele 7 zile, cel mult 100 mailuri/folder, pagini de 25, maximum 50 pe
verificare și interval de 300 secunde. Poți alege date calendaristice explicite;
limita superioară este exclusivă. Nu se importă implicit întreaga căsuță.

Verificarea periodică importă doar text simplu limitat la 12.000 caractere și până
la 20 de metadate de atașamente (nume, dimensiune, tip). **Analizează local** este o
acțiune explicită și necesită AI activat și GGUF disponibil. Lipsa acestora nu
împiedică restul aplicației. Conținutul atașamentelor nu este citit, executat sau
trimis motorului. Nu se trimit mailuri sau date către servicii externe.

Selectează un mail pentru sursă, data originală, SMTP și fragment. Analiza produce
o **estimare neconfirmată**, distinctă de taskurile asociate confirmat. Mesajele
informative pot avea zero acțiuni. Celelalte oferă propuneri comune: creare,
asociere, notiță în jurnal, status, motiv de așteptare sau următor pas. În
**Propuneri**, verifică înainte/după, motivul și sursele, apoi acceptă, editează ori
respinge. Nimic nu se aplică doar pentru că modelul a produs JSON. Aplicația nu
atribuie responsabil sau prioritate din presupuneri; prioritatea Normală este
valoarea implicită a aplicației. Solicitantul este expeditorul doar când modelul
identifică solicitarea sa și COM a rezolvat un SMTP real; altfel cere completare.

Termenele trebuie susținute de citate. „Mâine”/„vineri” se calculează față de data
**mesajului**, în fusul workspace-ului, și data rezultată apare în previzualizare.
Aceeași vineri, expresii alternative, texte citate/forwarded sau date contradictorii
cer clarificare. Data ambiguă blochează aplicarea creării până la editare explicită.
Aceste reguli conservative nu înlocuiesc citirea mailului original.

Respingerile, ignorarea conversațiilor și rezultatele aplicării persistă după
restart. Reluarea unei conversații păstrează deciziile anterioare; reanalizarea unui
mail tratat cere confirmare explicită. ConversationID oferă numai context: legăturile
confirmate sugerează candidați, fără a asocia automat alte mesaje aceluiași task.

## Identitate, incrementare și limitări

Datele persistă prin Workspace în `_system/mail/state.json` și
`_system/mail/messages/<UUID>.json`; rezultatele propunerilor sunt în istoricul comun
`_system/history`. Corpurile sunt cache local și intră în backupurile workspace-ului;
protejează accesul la acesta. Logurile de diagnostic nu conțin corpuri complete sau
mesaje brute din excepțiile COM/inferență.

Identitatea este UUIDv5 din StoreID + InternetMessageID; fallback StoreID +
PR_SEARCH_KEY, apoi StoreID + EntryID. Mutarea în același store păstrează identitatea
când primul sau al doilea identificator rămâne stabil; locația se actualizează.
Mutarea între store-uri produce identitate nouă. Copiile cu același MessageID în
același store sunt deduplicate. Fără MessageID/search key, mutarea poate schimba
EntryID și produce duplicat; UI afișează avertismentul. ConversationID nu este
cheie de deduplicare sau dovadă de apartenență la un task.

Prima scanare fixează intervalul de primire și plafonul. Ulterior sunt folosite
ferestre fixe pe LastModificationTime cu suprapunere de o zi și offset persistent.
Checkpoint-ul avansează numai după salvarea lotului; reluarea unui lot este
idempotentă. Mesajele vechi necunoscute din suprapunere nu ocolesc plafonul primei
scanări. Scanarea nu este un snapshot tranzacțional Outlook: modificările în timpul
paginării pot deplasa rânduri, iar suprapunerea ajută la recuperare. Nu garantează
capturarea unui mail mutat în afara folderelor monitorizate înainte de citire.
Offseturile de peste 10.000 sunt oprite controlat; restrânge intervalul și resetează
cursorul dacă backlogul depășește această limită. Resetarea nu șterge deciziile sau
mailurile deja importate. Un mesaj respins/ignorat nu reapare ca propunere la scanare.

COM folosește exclusiv ComWorker existent, comun cu calendarul și trimiterea.
Din fir ies doar DTO-uri serializabile. Nu se modifică Unread și nu se apelează
Move/Delete/Save pe mailuri. SMTP Exchange este rezolvat din proprietăți MAPI,
ExchangeUser/ExchangeDL; nu se formează adrese din numele afișat.

Nu se suprapun scanări. Outlook închis/offline produce stare controlată, fără
avansarea cursorului. Un apel COM blocat nu poate fi întrerupt în siguranță de Python:
la timeout workerul rămâne blocat până revine apelul; nu se creează alt fir COM care
să-l dubleze. Anularea analizei oprește procesul AI prin mecanismul existent.
Schimbarea workspace-ului invalidează rezultatele scanării/analizei și golește sursa
afișată. Aplicările se fac pe firul UI prin Workspace, cu revizii, surse și receipts
persistente; conflictele cer recalculare, iar rezultatele parțiale rămân vizibile.

## Verificări

Testele automate `test_mail_monitor.py`, `test_mail_com.py`, `test_mail_ui.py`
folosesc backend Outlook fals sau obiecte COM simulate și Tk real cu Xvfb. Acoperă
informare, cerere nouă, răspuns la task, termen ambiguu, deduplicare, restart,
indisponibilitate/timeout, citate, buget, ignorare și rezultate parțiale.

Smoke opțional, cu modelul descărcat și dependența nativă instalată:

```sh
python scripts/smoke_mail.py
```

Acesta folosește **Outlook fals și GGUF real**, pe workspace temporar; nu trimite
mailuri și nu aplică propunerea. Nu dovedește funcționarea Outlook Classic real.

Verificare manuală necesară pe Windows cu mailbox de test:

1. Outlook închis, apoi Classic deschis/conectat; enumerare cont/foldere, inclusiv
   Exchange, adrese SMTP reale și fus/oră de vară pentru proprietățile MAPI UTC.
2. Interval restrâns și plafon mic; restart între pagini; modificare și mutare
   între foldere monitorizate, apoi între store-uri, verificând identitatea.
3. Confirmă că Unread/locația/atașamentele originale nu se schimbă, inclusiv pentru
   mesaje informative și fișiere executabile atașate.
4. Offline, eroare de acces la folder și COM lent/blocat: UI fluid, fără scanări
   suprapuse sau checkpoint avansat la eroare; recuperare după revenirea COM.
5. Acceptă/editează/respinge, ignoră/reia, redeschide workspace-ul; verifică receipts,
   clarificările de termen și absența reaplicărilor după restart.

Aceste verificări pe Outlook real **nu au fost executate în mediul Linux**.
