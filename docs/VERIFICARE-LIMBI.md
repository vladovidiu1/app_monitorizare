# Verificarea internaționalizării FocusDesk

Etapa pornește de la `d9d50f6e14ab51d2dfcb4289896e64baabad406c`, cu păstrarea funcțiilor deja existente pe `focusdesk/integration-review`. Româna rămâne implicită. Sunt incluse English, Deutsch, Français și Español, fără dependențe runtime noi sau servicii de traducere.

## Comportamentul livrat

- **Setări → General → Limbă / Language** salvează atomic preferința profilului, inclusiv fără workspace sau cu workspace read-only. Aplicarea are loc la următoarea pornire manuală, explicată în dialog. Procesul curent păstrează limba, ciornele și timerul.
- Cinci cataloage locale cu **1.749 de chei fiecare**, parametri numiți, pluralizare și fallback românesc raportat în log. Interfața și mesajele proprii, datele/numerele afișate, textele generate, șabloanele incluse și cele 19 capitole ale ghidului folosesc infrastructura centrală.
- ID-urile taburilor, perioadelor și agregărilor sunt stabile. Preferințele vechi ale inspectorului se migrează. Taburile care nu încap folosesc un selector cu etichete complete; acțiunile se împart pe rânduri și antetele tabelelor țin cont de font/scalare.
- Descrierea rămâne un singur câmp, cu PeerText, ghid, Undo/Redo și anularea editorului extins. Nu au fost reintroduse formatarea sau previzualizarea.
- Conținutul personal existent rămâne nemodificat: titluri, descrieri, notițe, minute, persoane, căi, șabloane, istoric și mesaje compuse. Statusurile, prioritățile și tipurile persistate rămân aceleași. Datele autoritare rămân fișiere JSON/Markdown și foldere locale; nu a fost introdus SQL/SQLite.
- Datele demonstrative se traduc numai la crearea lor explicită. Alegerea ulterioară a altei limbi nu rescrie un workspace demonstrativ deja creat.

Instrucțiunile de utilizare și de adăugare a unei limbi sunt în [INTERNATIONALIZARE.md](INTERNATIONALIZARE.md).

## Verificări executate

Suita completă finală: **617 teste trecute, 1 omis, 175,69 s**. Singura omisiune este verificarea junction-urilor Windows (`tests/test_stage3.py::test_junction_not_followed`), pe Linux. Compilarea modulelor și `pip check` au trecut; nu există cerințe Python incompatibile în mediul folosit.

Comenzi principale, cu Python din mediul proiectului și Xvfb disponibil în PATH:

```sh
xvfb-run -a python -m pytest -q
python -m compileall -q src scripts/i18n_smoke.py tests/test_i18n.py
python -m pip check
python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir artifacts/wheel .
```

Cele **40 de cazuri noi** din `tests/test_i18n.py` verifică paritatea cheilor/parametrilor, pluralurile, fallback-ul inclusiv regula limbii sursă, preferințele vechi/invalide, formatele, ancorele ghidurilor, șabloanele, resursele frozen și colectarea PyInstaller. Includ pornire în procese distincte pentru fiecare limbă, conservarea datelor după restart, salvare eșuată a preferinței, read-only și păstrarea contextului selectorului de taburi. Testele existente continuă să acopere serviciile, operațiile recuperabile, sesiunile, rapoartele, întâlnirile și editorul.

### Matricea UI reală în Tk/Xvfb

Scenariul `scripts/i18n_smoke.py` a trecut în **15 combinații**, cu **47 de verificări în fiecare: 705 verificări și 45 de capturi**. Rulează cu profil și workspace temporare, fără mesaje trimise sau aplicații externe deschise.

| Limbă | 100% | 125% | 150% |
| --- | --- | --- | --- |
| Română | [manifest](capturi-ui/i18n/ro-100/manifest.json) | [manifest](capturi-ui/i18n/ro-125/manifest.json) | [manifest](capturi-ui/i18n/ro-150/manifest.json) |
| English | [manifest](capturi-ui/i18n/en-100/manifest.json) | [manifest](capturi-ui/i18n/en-125/manifest.json) | [manifest](capturi-ui/i18n/en-150/manifest.json) |
| Deutsch | [manifest](capturi-ui/i18n/de-100/manifest.json) | [manifest](capturi-ui/i18n/de-125/manifest.json) | [manifest](capturi-ui/i18n/de-150/manifest.json) |
| Français | [manifest](capturi-ui/i18n/fr-100/manifest.json) | [manifest](capturi-ui/i18n/fr-125/manifest.json) | [manifest](capturi-ui/i18n/fr-150/manifest.json) |
| Español | [manifest](capturi-ui/i18n/es-100/manifest.json) | [manifest](capturi-ui/i18n/es-125/manifest.json) | [manifest](capturi-ui/i18n/es-150/manifest.json) |

Sunt parcurse cele patru pagini, perioadele dashboardului, secțiunile spațiului taskului și F1, descrierea ghidată, un singur Undo/Redo, salvarea existentă, PeerText, anularea extinsă, grab-ul modal, timerul activ, schimbarea amânată a limbii, raportul/CSV, finalizarea/redeschiderea și șabloanele. Se verifică lipsa erorilor callbackurilor Tk și a cheilor lipsă. Instantaneele fișierelor workspace-ului rămân identice când se salvează numai limba; ciornele de titlu/descriere și identitatea timerului rămân în memorie.

Fereastra principală este verificată la minimul logic de **1100 × 700**, iar ghidul la **760 × 500**, scalate prin Tk. Capturi reprezentative:

- [Germană 150% — fereastră minimă](capturi-ui/i18n/de-150/main-minimum.png)
- [Franceză 125% — ghidul descrierii](capturi-ui/i18n/fr-125/guide-description.png)
- [Spaniolă 150% — alegerea limbii](capturi-ui/i18n/es-150/settings-language.png)
- [Română 100% — fereastră minimă](capturi-ui/i18n/ro-100/main-minimum.png)

Exemplu de reproducere a unei combinații:

```sh
xvfb-run -a -s '-screen 0 2400x1900x24' python scripts/i18n_smoke.py --language de --scale 1.5 --capture-dir artifacts/de-150 --report artifacts/de-150/manifest.json
```

### Distribuție offline

Wheel-ul construit local are **913.562 octeți**, SHA-256 `f67bb97b86d881469e564fd11eedc7cf2eb89b36efbdf6900cdd96a80fb14915`. Conținutul resurselor și modulelor modificate inspectate a fost comparat cu sursele:

| Resurse împachetate | Fișiere | Octeți necomprimați |
| --- | ---: | ---: |
| Cataloage | 5 | 789.601 |
| Ghiduri: 19 capitole + index în fiecare limbă | 100 | 187.550 |
| Șabloane incluse: 4 în fiecare limbă | 20 | 41.189 |

Wheel-ul a fost instalat local, fără descărcări și fără dependențe noi, într-un director separat. Dintr-un director de lucru temporar, cinci procese au importat explicit pachetul instalat, au pornit UI în fiecare limbă, au deschis Setări fără workspace și ghidul cu 19 capitole și au găsit cele patru șabloane ale limbii. Nu au folosit resursele checkout-ului. Dependențele Python existente au rămas cele din mediul de verificare.

Testul cu `collect_data_files('focusdesk')` confirmă includerea tuturor cataloagelor, ghidurilor și șabloanelor în lista de resurse utilizată de `focusdesk.spec`. Un test separat verifică încărcarea resurselor cu `_MEIPASS` simulat. Aceste verificări nu reprezintă construirea sau rularea unui executabil Windows.

## Limite ale validării

- Execuțiile și capturile sunt **Linux/Tk/Xvfb**, cu scalare simulată. Nu certifică DPI nativ Windows, mutarea între monitoare sau fonturile/dialogurile native Windows. Fonturile de substituție ale mediului pot reda diferit simbolurile; testele verifică separat conținutul Unicode, diacriticele și păstrarea textului personal.
- Nu s-au executat builduri ori executabile Windows și nu există o măsurătoare a dimensiunii sau pornirii unui EXE pentru această etapă. Dimensiunea de mai sus aparține numai wheel-ului verificat.
- Integrarea **Outlook Classic real nu a fost executată**. Testele de integrare existente folosesc backenduri false. Mesajele proprii sunt localizate; detaliile tehnice returnate de Windows/COM/Outlook rămân originale.
- Navigarea cu ID-uri și selectoarele native au fost exercitate automat; nu a fost efectuată o sesiune manuală completă cu cititor de ecran ori exclusiv tastatură pe Windows. Capturile și verificările automate nu înlocuiesc o evaluare lingvistică independentă de vorbitori nativi.
- Nu sunt raportate benchmarkuri noi de performanță: această etapă verifică localizarea și regresiile, nu repetă măsurătorile etapei de indexare. Cataloagele sunt încărcate o singură dată per proces; nu s-au introdus scanări ale istoricului sau notițelor pentru traducere.
