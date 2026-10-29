# Ghidul complet de utilizare în aplicație

Butonul **Ghid de utilizare**, cu pictogramă locală de carte în antet, meniul **Ajutor** și **F1** oferă documentația offline a funcțiilor existente. Ghidul nu adaugă o destinație principală și nu execută pașii tutorialelor. Nu salvează/abandonează ciorne, nu schimbă selecția taskului și nu pornește/oprește timerul.

## Conținut și întreținere

Conținutul canonic este în [resources/guide](../src/focusdesk/resources/guide/index.json): 19 articole Markdown și un index JSON cu identificatori stabili. [utilizare.md](utilizare.md) este cuprinsul pentru repository, nu o a doua copie a articolelor. Documentele tehnice ale etapelor rămân referințe pentru implementare; ghidul de utilizare a fost adaptat codului actual. Au fost corectate trimiterile vechi la previzualizarea descrierii și la schimbarea timerului.

Capitole: introducere, workspace, interfață, Astăzi, organizare, descriere ghidată, sesiuni, calendar, întâlniri, Activitate, fișiere, e-mail, cerințe ulterioare, șabloane, versiuni, arhivă/Coș/backup, setări, scurtături și probleme. Tutorialele A–K acoperă exemple fictive și comenzi verificate în UI. Sunt explicate distinct rezervare/lucru/întâlnire, finalizare/arhivare/Coș, redeschidere/cerință nouă, descriere/checklist/subtask, copie/referință și salvare/autosalvare.

Când se schimbă o comandă sau un flux, actualizează articolul canonic și verifică identificatorii/linkurile. Ancorele sunt derivate din subtitluri prin normalizare fără diacritice; linkurile `guide:capitol#ancora` și `#ancora` sunt validate integral la încărcare și în teste. Indexul și căile acceptă numai nume locale din pachet. Nu se execută HTML, cod, URL-uri sau imagini din documentație.

## Fereastră și navigare

`ui/user_guide.py` afișează cuprinsul, căutarea, articolul cu scroll, Înapoi/Înainte și legăturile accesibile prin mouse sau controlul **Legături în articol**. Textul folosește un subset restrâns Markdown în Tk Text read-only: titluri, paragrafe, liste, observații, comenzi și cod literal. Editorul descrierii rămâne neschimbat, fără bara de formatare sau filele Editare/Previzualizare.

Există un singur model/istoric și cel mult o vedere a ghidului. Redeschiderea generală refolosește fereastra și păstrează capitolul, căutarea și scrollul în aceeași rulare. Înapoi/Înainte au istoric limitat la 100 de locații; o navigare nouă după Înapoi elimină ramura Înainte. Aceste preferințe de lectură sunt în memorie, nu în workspace.

Căutarea este limitată la documentația inclusă, indexată o singură dată. Ignoră majusculele și diacriticele, caută termenii în titlu/conținut și oferă titlu și fragment. Nu citește descrieri, notițe, mesaje sau alte documente personale. Lipsa rezultatelor și resursele lipsă/corupte au stări explicite; eroarea resurselor nu blochează aplicația, iar reîncercarea este doar locală.

## F1 și dialoguri

F1 este dedicat ajutorului în același interpreter Tk. Pagina activă alege fluxul zilnic, organizarea, Agenda/Întâlniri sau dashboardul; în spațiul taskului sunt identificate secțiunile. Focusul într-un editor sau dialog cunoscut poate oferi un capitol mai precis. Intrarea Scurtături din Ajutor folosește același conținut, fără o listă separată care să diverge.

Ghidul general este nemodal și nu pune grab. Dacă există un dialog modal, vederea este găzduită ca descendent al dialogului care deține grab-ul, fără eliberarea/mutarea lui. Dacă gazda se schimbă, se recreează numai vederea, păstrând modelul și istoricul; nu apar două ferestre de ghid. La ascundere se reface focusul anterior dacă widgetul mai există. Închiderea dialogului gazdă distruge vederea sa copil; modelul de lectură permite redeschiderea ghidului. Sunt gestionate și ferestrele Tcl care nu aveau inițial wrapper Python, fără a le modifica starea sau a păstra callbackuri după distrugere.

Ghidul general poate rămâne disponibil după eliberarea workspace-ului. Nu păstrează referințe la noduri, sesiuni sau date ale vechiului workspace. Nu oferă comenzi de mutație ori butoane care să execute tutorialul. Tastatura din editoarele aplicației rămâne neschimbată în afară de F1; Ctrl+F, Alt+săgeți și Escape din ghid sunt locale ferestrei acestuia, iar Ctrl+S în ghid nu salvează taskul.

## Resurse și distribuție

`pyproject.toml` include `resources/guide/*.md`, `resources/guide/*.json` și pictogramele locale. `focusdesk.spec` folosește mecanismul existent `collect_data_files("focusdesk")`, care include aceste resurse. Loaderul reutilizează `config.resource_path`, inclusiv calea `_MEIPASS/focusdesk/resources/guide` dintr-un bundle PyInstaller; nu depinde de checkout sau de docs/ la utilizator.

S-au construit și inspectat un wheel cu 19 articole + index și cele șase dimensiuni de pictogramă. S-a executat colectarea efectivă `collect_data_files`, plus un test al loaderului dintr-un director `_MEIPASS` simulat care conține numai resursele copiate. Acestea verifică includerea/căile resurselor; nu reprezintă pornirea unui executabil Windows.

Nu există dependențe runtime noi, browser integrat, SQL/SQLite, servicii cloud sau trafic de rețea al ghidului. Pillow este folosit numai de scripturile de dezvoltare pentru pictograme/capturi.

## Verificări efectuate

Pe Linux/Xvfb și workspace-uri temporare:

- Suita completă finală: **577 teste reușite, 1 omis**, în **130,12 s**. Omis este testul de junction Windows.
- **40 de teste noi** pentru ghid, toate reușite; au trecut și rerulările dedicate după ajustările de lizibilitate.
- **33 verificări de geometrie** reușite la 100%/125%/150%, cu 12 capturi reale. Antetul și controalele ghidului rămân în fereastra minimă, fără suprapunerea butonului cu căutarea.
- Wheel-ul verificat conține **20 de fișiere ale ghidului (45.658 bytes)** și șase pictograme help; fișierele documentației și modulul UI din wheel au fost comparate cu sursele curente.

- Testele noi verifică resursele, toate linkurile și țintele contextuale, normalizarea căutării, fragmentele, istoria/scrollul, textul literal, erorile și retry-ul resurselor, antet/meniu/F1, reutilizarea ferestrei, secțiunile Calendar/spațiu task, ciorne/timer, editor modal imbricat, formular e-mail fără Send, dialog Tcl nativ, eliberarea callbackurilor și funcționarea fără workspace/offline.
- Sunt rulate și testele existente pentru dashboard, ghidul descrierii, cerințe ulterioare, sesiuni/timer unic, întâlniri, e-mail și exploratorul de fișiere.
- Wheel-ul, lista PyInstaller, loaderul frozen simulat, `compileall` și `pip check` sunt verificate separat.

Reproducere:

```sh
xvfb-run -a python -m pytest -q
python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir artifacts/wheel .
xvfb-run -a python scripts/capture_guide.py --scale 1.25 --output artifacts/guide-125
```

Capturi Tk reale pe date fictive: [antet 100%](capturi-ui/ghid/100/ghid-acces-antet.png), [ghid la minimum 125%](capturi-ui/ghid/125/ghid-descriere-minim.png), [căutare 150%](capturi-ui/ghid/150/ghid-cautare.png), [ajutor din editor modal](capturi-ui/ghid/100/ghid-din-editor-modal.png). Manifestele consemnează geometria verificată. Fereastra principală este verificată la minimum 1100×700 logic, ghidul la 760×500 logic, cu scalare 100%/125%/150%.

## Limite și verificări Windows rămase

Scalarea Tk/Xvfb nu certifică DPI nativ sau mutarea între monitoare Windows. Nu s-a construit/rulat un EXE Windows în această etapă și nu s-a executat integrarea reală Outlook, Explorer sau VS Code. Dialogurile modale FocusDesk și un dialog Tcl sunt testate; F1 și focusul în dialogurile native Windows de selecție fișiere, avertismente COM și alte ferestre OS necesită test pe calculatorul țintă. Ghidul nu încearcă să ocolească modalitatea/politicile lor.

Test manual recomandat: pornește distribuția completă fără checkout/Python instalat, deschide ghidul din antet și F1, verifică toate capitolele/căutarea offline, treci între aplicație și ghid cu o ciornă/timer, apoi repetă dintr-un dialog de editare și din selectoarele native la 125%/150%. Nu trimite mesaje reale pentru verificarea ghidului.
