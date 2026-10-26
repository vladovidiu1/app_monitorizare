# Navigarea și lucrul zilnic în FocusDesk

Sidebarul are patru destinații principale. La deschiderea unei pagini fără task
selectat, inspectorul se retrage pentru a lăsa loc conținutului. Selectarea unui task
îl readuce; panourile rămân redimensionabile, iar Instrumente permite ascunderea lui.

## Astăzi

Priorități alese manual (maximum configurat), sesiuni planificate și timerul activ,
în liste compacte. Fără o sesiune activă, selectează o prioritate și apasă **Începe**.
Când rulează sesiunea apar **Pauză**, **Încheie sesiunea…** și **Deschide taskul activ**.
După pauză, **Continuă** reia aceeași sesiune. Pornirea altui task este dezactivată
până la încheierea sesiunii curente; aceasta nu se oprește implicit.

Restantele sunt un număr și o comandă către filtrul din lista de taskuri, fără o
listă duplicată. Sesiunile din Astăzi deschid Calendarul pentru programare. Listele
nu sunt reconstruite ca widgeturi la fiecare refresh și păstrează selecția.

## Proiecte și taskuri

Destinația oferă toate taskurile, arborele de proiecte și categoriile/folderele
existente. Selectarea unui container arată ierarhia lui în centru. Taskurile pot
rămâne independente, inclusiv în categorii; nu trebuie creat un proiect artificial.

Filtre: status, prioritate, termen, proiect, solicitant (nume/cod/adresă) și text.
**Fără proiect** verifică cel mai apropiat strămoș de tip proiect. O simplă legătură
către un proiect nu schimbă apartenența; folosește **Mută / proiect…** pentru aceasta.
Proiectele cu nume identice sunt diferențiate în filtru printr-un sufix de ID.

**În așteptare**, **Restante** și **Finalizate** sunt filtre rapide ale aceleiași
pagini. **Toate** resetează filtrele; comutatorul **Închise** include finalizatele și
anulatele în listă. Arhivarea rămâne separată de status.

Câmpul de adăugare rapidă funcționează și fără proiect. **Task independent** creează
la rădăcină; **Adaugă** sub un task selectat creează un subtask, iar în proiectul
curent creează un task în acel proiect. Contextul țintă este afișat deasupra câmpului.
Căutarea globală și Ctrl+F rămân în antet; Enter în lista de taskuri deschide Detalii.

## Calendar

Agenda, programarea manuală, planificatorul determinist, recurențele, exportul ICS și
sincronizarea Outlook rămân în aceeași pagină. Nu s-au schimbat regulile de program,
pauze, dependențe, capacitate sau suprapuneri. La refresh se păstrează selecția și
derularea agendei. Evenimentele sunt rezervări personale de timp, fără invitați sau
Teams. Outlook Classic este opțional; New Outlook nu oferă COM.

## Activitate

Tabele pentru zile, proiecte și sesiunile individuale, cu perioade de 7/30/90 zile sau
întregul istoric. **Dashboard lunar** deschide dashboardul existent; Ctrl+D rămâne activ.
Dublu-clic pe o sesiune deschide taskul său.

- **Lucrat înregistrat** însumează direct `actual_seconds` salvat, o dată per sesiune.
  Nu însumează rollup-urile părinților și nu include timerul încă nesalvat.
- Ziua lucrată este `started_actual_at`, cu fallback `start_at`, în fusul workspace-ului,
  la fel ca în calculele existente; sesiunea nu este împărțită artificial la miezul nopții.
- **Programat** este durata rezervată, inclusiv pentru sesiuni realizate, exclusiv
  anulările și sesiunile ratate. Durata programată nu reprezintă muncă efectuată.
- Proiectul se calculează din apartenența actuală a taskului. Mutarea taskului schimbă
  gruparea lui, fără a rescrie sesiunile. Fișierele sesiunilor rămân autoritare.

## Inspectorul taskului

Antetul arată titlul, statusul, prioritatea, termenul și următorul pas. Oferă **Începe /
Pauză / Continuă**, **Finalizează / Redeschide** și **Mai multe**. În Mai multe găsești
compunerea manuală a e-mailului, mutarea/asocierea cu proiectul, arhivarea și folderul.

Taburi: **Detalii**, **Subtaskuri**, **Activitate**, **Fișiere**, **Planificare**, **Versiuni**.
Activitate reunește notițele, sesiunile și istoricul statusului; o notiță nesalvată
beneficiază acum de aceeași întrebare Salvează/Renunță/Rămâi aici la schimbarea taskului.
Descrierea păstrează editorul Markdown, bufferul comun și fereastra extinsă; vezi
[ghidul descrierii](DESCRIERE-MARKDOWN.md).

## Funcții secundare și scurtături

**Arhivă**, **Setări** și **Date și backup** sunt în partea de jos a sidebarului.
Ultimul meniu oferă Coș, backup de metadate/complet, restaurare și integritate.
Meniurile Fișier, Organizare și Instrumente păstrează funcțiile existente.

Ctrl+N, Ctrl+F, Ctrl+S, Ctrl+M, Ctrl+D, F2, F5, Insert, Alt+săgeți și Ctrl+Enter
în jurnal sunt păstrate. Ctrl+M și **Mai multe → Compune e-mail…** deschid mesajul
nou manual. Ciorna și trimiterea cu confirmare folosesc Outlook Classic prin ComWorker;
nu există citire a inboxului, analiză de mail sau trimitere automată.

## Compatibilitate

`inbox` rămâne o valoare internă acceptată pentru date vechi, afișată cu aceeași
etichetă și pictogramă ca `todo`: **De făcut**. Filtrul le include împreună, fără două
categorii. Salvarea altui câmp nu rescrie automat vechiul status. Taskurile noi, inclusiv
captura rapidă, sunt `todo`. Nu se șterg și nu se mută taskuri automat.

Preferințele `last_view` și `inspector_tab` acceptă vechile nume: destinațiile retrase
se deschid în Proiecte și taskuri, Jurnal devine Activitate, Subtask-uri devine Subtaskuri.
Apelurile vechi către paginile retrase sunt redirecționate către filtre. Preferințele
se salvează cu configurația aplicației; nu se schimbă schema workspace-ului.

Refresh-ul păstrează selecția și derularea listei, arborelui, calendarului și activității.
Schimbarea explicită a sursei listei pornește de sus. Widgeturile din Astăzi sunt
persistente. Descrierile și notițele nesalvate nu sunt înlocuite de refresh.

Capturi reale pe date demonstrative: [Astăzi](capturi-ui/01-astazi.png),
[task](capturi-ui/03-inspector.png), [toate taskurile](capturi-ui/13-proiecte-taskuri.png),
[Activitate](capturi-ui/14-activitate.png).

## Spațiul de lucru al taskului

Inspectorul și meniul contextual oferă **Deschide spațiul de lucru**: pagină centrală
cu descriere amplă, Pași, Fișiere, Activitate, Planificare și Versiuni. Înapoi păstrează
contextul de navigare. **F11** intră/iese din Concentrare, cu timerul neschimbat.
[Detalii și salvare comună cu inspectorul](SPATIU-DE-LUCRU.md).

## Structuri reutilizabile

**+ Nou → Din șablon…** creează o structură după previzualizare. Pentru reutilizarea
unui proiect/task existent folosește **Salvează ca șablon…** în meniul contextual.
Catalogul complet este în **Instrumente → Gestionare șabloane…**.
[Editare, variabile și protecția datelor](SABLOANE.md).
