# Activitate: înțelegerea dashboardului

## La ce folosește
Dashboardul local arată munca înregistrată și planificarea pentru o perioadă, fără dublarea sesiunilor părinte/subtask. Calendarul lunar, tabelele și exportul folosesc aceleași reguli de calcul.

## Unde îl găsești
Alege **Activitate** în navigare. **Calendar lunar · Ctrl+D** sau **Ctrl+D** deschide vizualizarea lunară secundară; aceasta nu este o destinație principală suplimentară.

## Tutorial J: verifică timpul lucrat
1. Alege **7 zile**, **30 zile**, **90 zile**, **Luna curentă**, **Interval personalizat** sau **Tot istoricul**.
2. Selectează proiectul dorit sau **Fără proiect**. Pentru un interval personalizat completează datele și folosește **Aplică interval**.
3. Citește **Lucrat înregistrat** și compară cu **Programat**, fără să le aduni ca muncă efectuată.
4. Selectează o zi/proiect din grafice sau tabelele de detaliu. Filtrul aplicat rămâne vizibil; **Elimină detaliul** îl scoate, iar **Resetare filtre** reface selecția generală.
5. În detaliile sesiunilor, Enter/dublu-click deschide taskul. Revino în dashboard pentru a păstra contextul.
6. **Export CSV** exportă filtrarea curentă, cu definițiile coloanelor, diacritice și protecție pentru texte interpretate de Excel ca formule.

## Cum interpretezi cardurile
**Lucrat înregistrat** numără durata salvată o dată pe sesiune, inclusiv pentru taskuri finalizate/arhivate sau indisponibile. Timpul live apare separat și nu se dublează cu durata salvată. Părintele și subtaskurile nu sunt două copii ale aceleiași munci.

**Programat** este durata rezervată eligibilă, fără cancelled/missed; nu dovedește lucru efectiv. Întâlnirile importate nu măresc niciunul dintre aceste două totaluri.

**Taskuri finalizate** numără taskuri distincte cu tranziție la Finalizat în istoricul perioadei; redeschiderea și refinalizarea aceluiași task nu îl numără de două ori în aceeași perioadă. Datele vechi fără istoric suficient pot avea finalizări neidentificabile; updated_at nu inventează o finalizare.

**Restante acum** și distribuția pe statusuri sunt situația curentă, nu o reconstrucție a trecutului. Apartenența la proiect este cea actuală. Intervalele mari se agregă pe săptămâni/luni; granularitatea este afișată.

## Salvare și greșeli frecvente
Filtrele nu modifică sesiunile. Exportul este o scriere explicită în fișierul ales. Pentru o eroare de timp folosește **Corectează timpul…** pe o sesiune încheiată, apoi reverifică raportul și exportul. Nu deduce productivitatea doar din ore. [Sesiuni și corecții](guide:sesiuni).
