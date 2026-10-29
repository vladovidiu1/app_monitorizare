# Probleme frecvente și limitări

## Nu găsesc un task finalizat
Folosește **Proiecte și taskuri → Finalizate**, **Închise** și filtrele potrivite. Arhivarea este separată: verifică și **Arhivă**. O legătură generică spre proiect nu îi schimbă apartenența. **Redeschide taskul** și **Adaugă cerință nouă…** au [scopuri diferite](guide:cerinte).

## Descrierea nu s-a păstrat
Aplicarea ghidului de completare schimbă bufferul, nu discul. Salvează taskul cu **Salvează/Ctrl+S**. Anularea editorului extins revine la snapshotul lui. Jurnalul taskului cere adăugarea explicită; doar notițele [întâlnirilor](guide:intalniri) au autosalvarea descrisă în acel ecran.

## Un document nou nu apare
Verifică rădăcina reală din **Fișiere**, extinde subfolderul și folosește **Actualizează** / **F5** în explorator. Nu alege automat directorul intern al nodului drept folder de lucru. Folderele inaccesibile pot păstra o listare anterioară; aceasta nu dovedește disponibilitatea actuală. Symlinkurile/junctions nu sunt traversate automat. [Explorarea și referințele](guide:fisiere).

## Văd Programat, dar nu am lucrat atât
Programarea este o rezervare. Lucratul este timpul efectiv salvat; timpul live apare separat. Întâlnirile nu măresc orele lucrate. Verifică perioada/proiectul și filtrele de detaliu din Activitate; corectează doar o sesiune încheiată pe care o poți identifica. [Regulile raportului](guide:activitate).

## Outlook nu răspunde sau lipsește un modul
Verifică faptul că folosești Outlook Classic; New Outlook nu suportă COM. Nu se ocolesc politicile companiei. Un mesaj precum `ModuleNotFoundError: win32timezone` indică o componentă pywin32 lipsă din mediul/distribuția folosită. Pentru un executabil este necesară o distribuție reconstruită corect de dezvoltator; instalarea separată pe PC nu repară automat un bundle deja creat.

La timeout după Send, mesajul poate exista deja în Outlook. Verifică ferestrele deschise, Ciorne, De trimis și Elemente trimise înainte de reîncercare. Apelul COM reușit nu dovedește livrarea. [Erori e-mail](guide:email#erori-si-greseli-frecvente).

## Salvare refuzată sau modificări externe
Nu suprascrie manual datele peste o ciornă importantă. F5/reload păstrează mecanismul de conflicte externe; dacă fișierul autoritar s-a schimbat, decide după verificare. Un workspace poate fi read-only dacă este folosit de alt proces sau a fost deschis astfel. **Instrumente → Verificare integritate workspace…** raportează probleme; nu șterge automat date ca soluție.

## Limite de performanță și siguranță
Prima reconstruire a unui index și o căutare globală completă în descrieri pot necesita citiri mai ample. Exploratorul scanează doar directoarele deschise, iar căutarea acestui ghid citește exclusiv documentația inclusă. Indexurile sunt reconstructibile, dar nu țin loc de backup. Nu există SQL/SQLite sau sincronizare cloud a datelor.

## Ce trebuie verificat pe calculatorul tău
Outlook Classic real, politicile COM, asocierile de documente, VS Code, junctions, DPI nativ și executabilul Windows depind de mediul țintă. Testele cu backend fals și scalarea Tk pe Linux nu le certifică. Un apel de sistem blocat în rețea nu poate fi anulat forțat în siguranță. Verifică backupul pe date temporare înainte de restaurare și păstrează separat folderele externe importante.
