# E-mail și atașamente

## La ce folosește
Compune un mesaj nou despre task, cu context și descriere integrală, apoi trimite-l prin furnizorul ales: Outlook Classic (implicit) sau Gmail prin parolă de aplicație. Nu este Reply/ReplyAll și nu citește inboxul. Corpul mesajului este un snapshot editabil; editarea lui nu schimbă descrierea taskului.

## Unde îl găsești
Selectează taskul și folosește **Ctrl+M**, **Organizare → Trimite e-mail din task…** sau **Mai multe → Compune e-mail…** din task. **Fișiere → Acțiuni → Atașează la e-mail…** poate preselecta documentele descoperite.

## Tutorial H: descriere completă și documente alese
1. Deschide formularul pentru taskul dorit. Dacă descrierea are modificări nesalvate, alege **Folosește descrierea curentă**, **Folosește ultima versiune salvată** sau **Anulează**. Implicit este descrierea curentă; alegerea nu salvează alte metadate.
2. Completează **Către**, **CC** și **Subiect**. Exemplul `ana@exemplu.ro` este fictiv; nu îl folosi pentru o trimitere reală.
3. Editează **Mesaj**. Descrierea lungă, liniile și diacriticele sunt păstrate, fără limita veche de 600 de caractere. Refreshul nu regenerează textul editat.
4. Selectează numai documentele necesare în [Atașamente](#atasamente).
5. Pentru revizuire alege **Deschide ciorna în Outlook**. Pentru trimitere apasă **Trimite** și verifică destinatarii, CC, subiectul, numărul și dimensiunea atașamentelor din confirmare.

## Atașamente
**Adaugă fișiere…** permite selecție multiplă de pe calculator. **Din fișierele taskului/proiectului…** include și documente puse manual pe disc. **Elimină din e-mail** scoate numai selecția din mesaj, fără ștergerea originalului sau a referinței taskului.

Numele identice din directoare diferite rămân documente distincte. Directoarele nu sunt atașate sau arhivate automat. Nu se copiază automat documente în workspace doar pentru e-mail. Fișierele sunt verificate din nou înaintea predării; un refuz al unui atașament oprește operația, fără trimitere parțială.

## Rezultate și salvare
**Ciornă deschisă** nu înseamnă trimitere. **Mesaj predat Outlook pentru trimitere** înseamnă că apelul Send a revenit fără eroare, nu că destinatarul l-a primit. Verifică Outlook pentru livrare/De trimis/Elemente trimise. Jurnalul păstrează rezultatul și numele atașamentelor, fără corpul integral.

## Erori și greșeli frecvente
Enter într-un câmp nu trimite. La eroare rămân destinatarii, corpul și documentele. După timeout/rezultat incert, verifică Outlook înainte de **Am verificat în Outlook…** și o nouă încercare explicită; nu există relansare automată. Eșecul jurnalului după predare nu justifică retrimiterea. Formularul nu este o ciornă locală persistentă după închiderea aplicației. [Outlook Classic/New Outlook](guide:setari#outlook-classic-si-lucru-offline).

## Configurare Gmail {#gmail-configurare}
Outlook Classic rămâne implicit. Pentru Gmail, deschide **Setări → Integrări → E-mail** sau **Configurează Gmail…** din formular. Completează adresa contului Gmail/Google Workspace (sunt acceptate domenii proprii) și, opțional, numele afișat. Nu există expeditor sau alias arbitrar în formular.

Activează verificarea în doi pași în contul Google și generează manual o parolă de aplicație în browser, la `https://myaccount.google.com/apppasswords`, folosind **Cum obțin parola de aplicație?**. Introdu parola de aplicație mascată în FocusDesk, nu parola obișnuită și nici coduri de verificare. FocusDesk elimină numai spațiile de prezentare. Politica organizației, Advanced Protection ori alte restricții pot face opțiunea indisponibilă. Schimbarea parolei Google poate revoca parolele de aplicație. Nu este OAuth sau „Sign in with Google”.

**Memorează securizat pe acest calculator** folosește Windows Credential Manager. Secretul nu intră în workspace, JSON, jurnal sau backup. Fără stocare securizată, parola rămâne numai în memoria sesiunii; la restart trebuie reintrodusă. **Salvează configurarea e-mail** păstrează numai profilul calculatorului și nu salvează metadatele taskului. Dacă o credențială veche nu poate fi ștearsă, apare avertisment și referința ei este păstrată pentru o eliminare ulterioară.

**Testează conexiunea** verifică TLS și autentificarea fără să trimită un mesaj și fără să salveze automat câmpurile. Reușita nu garantează acceptarea unui mesaj sau livrarea. **Elimină datele de conectare** șterge secretul local și metadatele; revocarea la Google se face separat din contul Google.

## Trimitere Gmail și rezultate {#gmail-trimitere}
În același formular folosește **Trimite prin → Gmail — adresa contului**. Schimbarea furnizorului sau configurarea Gmail păstrează destinatarii, CC, subiectul, textul și atașamentele. Calendarul Outlook nu se schimbă. Gmail nu necesită Outlook, dar trimiterea și testul necesită internet. Restul aplicației rămâne offline.

**Trimite** cere confirmarea contului și mesajului. SMTP folosește `smtp.gmail.com:465`, TLS verificat și timeouturi, fără conexiune necriptată. Toate documentele sunt citite înainte de predare; dacă unul lipsește sau este inaccesibil, nu se trimite un mesaj incomplet.

**Mesaj acceptat de serverul Gmail pentru trimitere** nu confirmă livrarea sau citirea. La acceptare parțială apar destinatarii acceptați și refuzați, cu coduri SMTP. **Pregătește numai destinatarii refuzați…** elimină destinatarii deja acceptați din noua încercare; cere apoi o nouă confirmare. Nu există relansare automată sau fallback Outlook. Dacă răspunsul se pierde în timpul predării, rezultatul este incert: verifică Gmail/destinatarii înainte de **Am verificat în Gmail…**. Nici schimbarea furnizorului nu deblochează singură retrimiterea.

SMTP nu creează ciorne în Gmail web. **Salvează ca .eml (local)…** produce un fișier local cu corp și atașamente, fără trimitere sau sincronizare. **Deschide ciorna în Outlook** apare numai pentru Outlook. Jurnalul păstrează furnizorul, contul, destinatarii, subiectul, momentul, Message-ID și numele documentelor; nici secretul, nici conversația SMTP. Eșecul jurnalului după acceptare nu justifică retrimiterea.

Pentru erori, verifică separat internet/DNS, timeout, TLS/certificate, autentificare, destinatari și limitele contului. Codurile de autentificare nu permit întotdeauna diferențierea unei parole greșite de una revocată sau de o politică a contului. Formularul rămâne disponibil la eroare; nu reduce securitatea TLS pentru a o evita.
