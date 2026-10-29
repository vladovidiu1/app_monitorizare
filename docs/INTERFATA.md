# FocusDesk Light

Noua versiune folosește exclusiv o temă luminoasă, în Tkinter + ttkbootstrap.
Configurațiile vechi cu `theme: dark` sunt acceptate; aplicația pornește luminos și
salvează `light` la închidere. Geometria și celelalte setări sunt
păstrate. În Instrumente, comutatorul vechi este înlocuit de „Aspect luminos FocusDesk”.

## Sistem vizual

`ui/design.py` centralizează paleta, fontul de bază, spațierile, înălțimea rândurilor,
limita ferestrei, tema ttkbootstrap și stilurile reutilizabile. Fundal gri foarte
deschis, suprafețe albe, text gri închis și accent indigo. Stările păstrează text
explicit și culori discrete; culoarea nu este singurul indicator.

Segoe UI este preferat pe Windows. În lipsa lui este folosit DejaVu Sans sau fontul
sans existent al sistemului. Stilurile includ buton principal, secundar, discret,
distructiv, hover/apăsat/dezactivat și focus nativ vizibil. Entry, Combobox,
Checkbutton, Notebook, Treeview și scrollbarurile păstrează implementările native
tematizate. Nu sunt construite controale decorative custom, animații sau servicii web.

Pictogramele outline originale sunt în `resources/icons`, la șase dimensiuni,
cu licență MIT inclusă. `scripts/generate_ui_icons.py` reproduce resursele în dezvoltare;
nu este rulat de aplicație. Imaginile sunt încărcate local, memorate per interpreter
Tk și incluse prin package-data. Nu se descarcă resurse în timpul utilizării.
Butoanele doar cu pictogramă au tooltip; focusul și scurtăturile existente rămân active.

## Modificări vizibile

- Bara principală păstrează FocusDesk, workspace-ul, căutarea extensibilă, Nou,
  E-mail.
- Sidebarul separă navigarea de ierarhia proiectelor, cu pictograme locale și
  selecție indigo discretă. Numărătorile provin în continuare din Queries.
- Lista de taskuri păstrează ierarhia, extinderea, sortarea și coloanele. Filtrele
  sunt regrupate; derularea orizontală permite accesul la coloane pe ferestre mici.
- Inspectorul păstrează taburile și protecția modificărilor nesalvate. Titlul și
  breadcrumb-ul se adaptează lățimii. Salvarea și starea formularului sunt în
  subsolul fix, în afara derulării. Grupul termenului ocupă două rânduri pentru
  a păstra accesibile data, ora, Azi, Mâine și eliminarea termenului.
- Astăzi prezintă data, numere reale de priorități/sesiuni/restante, priorități în
  suprafețe compacte și starea timerului/pauzei. Programul și stările goale
  păstrează datele și acțiunile existente. Nu sunt grafice sau cifre decorative.
- Calendarul, planificarea, dashboardul, setările, mailul, fișierele, jurnalul,
  versiunile folosesc aceleași stiluri. Barele de acțiuni formate
  din butoane trec pe mai multe rânduri; nu dispar comenzile la redimensionare.
  Tabelele comune au derulare pe ambele axe.

Nu s-au schimbat schema workspace-ului, calculele de timp, Planner, confirmarea
trimiterii mailurilor. Rezervările Outlook/ICS rămân
rezervări personale de timp, fără invitați sau Teams.

## Dimensiuni și capturi reproductibile

Minimul este 1100 × 700 pixeli logici. Dimensiunile minime, separatoarele și rândurile
se adaptează factorului Tk. Cele trei panouri sunt redimensionabile; inspectorul
poate fi ascuns din Instrumente. Pentru ferestre mici se folosesc scrollurile
formularelor și tabelelor. Panourile salvate anterior sunt păstrate în limitele
ferestrei curente.

Scriptul creează un workspace demonstrativ și configurație **temporare**, inclusiv
preferința veche dark, deschide ferestre Tk reale și salvează capturi PNG. Nu folosește
mockup-uri, nu activează COM și nu trimite mesaje. Eșuează la erori din callbackurile Tk.
Necesită Pillow (deja folosit de ttkbootstrap) și un desktop/display disponibil:

```powershell
python scripts/capture_ui.py --output artifacts/ui/100
python scripts/capture_ui.py --output artifacts/ui/min --size 1100x700
python scripts/capture_ui.py --output artifacts/ui/125 --scale 1.25
python scripts/capture_ui.py --output artifacts/ui/150 --scale 1.5
```

La 125% și 150%, desktopul virtual trebuie să încapă imaginile de 1800 × 1125,
respectiv 2160 × 1350. Parametrul `--scale` simulează factorul Tk și nu certifică
comportamentul DPI Windows sau mutarea între monitoare cu DPI diferit.

## Verificat efectiv

Interfața a fost pornită în Linux, Tk 9, cu Xvfb. Au fost inspectate capturi reale
pentru Astăzi, proiect/taskuri/subtaskuri, inspector, Calendar, Setări,
E-mail și Dashboard, la dimensiunea standard și minimă.
Capturile livrate acum au fost regenerate la 100% după eliminarea extensiilor.
Testele automate verifică păstrarea comenzilor esențiale la minimul 1100 × 700.
Verificările anterioare cu scalare Tk 125% și 150% nu certifică DPI Windows.

Exemple livrate: [Astăzi](capturi-ui/01-astazi.png),
[proiect](capturi-ui/02-proiect.png), [inspector](capturi-ui/03-inspector.png),
[Calendar](capturi-ui/04-calendar.png),
[Setări](capturi-ui/06-setari.png), [E-mail](capturi-ui/08-email.png).

Fonturile și rasterizarea X11 din acest mediu diferă de Segoe UI pe Windows;
anumite semne tipografice au fallback limitat. Butoanele folosesc pictograme locale,
iar acțiunile nu depind de glyph-uri emoji. Verificarea pe Windows la 100/125/150%,
High Contrast și pe monitoare cu DPI diferit rămâne manuală. Nu a fost generat un
executabil în această etapă.

## Statusuri și documentare

Pictogramele originale MIT diferențiază statusurile prin formă și etichete text,
inclusiv în arbore, căutare și inspector. Descrierea are panou redimensionabil,
editor extins cu buffer comun, fără bară de formatare sau file de previzualizare. [Comportament, scurtături și limite](DESCRIERE-MARKDOWN.md).

## Navigare și lucru zilnic

Patru destinații principale; ierarhia apare în Proiecte și taskuri. Inspectorul se
retrage fără selecție. Listele de taskuri sunt mai dense (26 pixeli logici pe rând),
iar Astăzi folosește liste persistente, fără carduri mari sau reconstrucții de widgeturi.
Timerul arată Pauză/Continuă după starea reală. [Ghidul navigării](NAVIGARE.md).

Capturile actuale includ și [toate taskurile](capturi-ui/13-proiecte-taskuri.png) și
[Activitate](capturi-ui/14-activitate.png). Rularea la minim și cea de 125% au fost
verificate în Xvfb; vezi [manifestul](capturi-ui/navigation-layouts.json).
