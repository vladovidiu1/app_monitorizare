# Verificarea integrării Gmail

Implementarea pornește de la `8e4263cf4cf385b6db9f8ebbd06264c921a7717e`, pe branchul de integrare. [Ghidul Gmail](GMAIL.md) descrie configurarea, limitele, implementarea și verificarea manuală necesară.

## Funcționalități livrate

- Outlook Classic rămâne implicit. Formularul existent oferă alegerea Outlook/Gmail, cu contul vizibil, fără pierderea destinatarilor, corpului editat sau documentelor.
- Configurare în profil, disponibilă fără workspace și în read-only; parolă mascată, Credential Manager nativ Windows sau numai în memoria sesiunii, eliminare locală și linkul oficial pentru generarea manuală a parolei de aplicație.
- SMTP cu TLS verificat, timeouturi și MIME complet Unicode. Testul conexiunii nu trimite mesaje. Gmail folosește UiBridge și nu necesită COM/Outlook; calendarul Outlook rămâne separat.
- Confirmare explicită, protecție la click repetat, rezultate parțiale/incerte fără retry sau fallback automat, pregătirea numai a destinatarilor refuzați și export local .eml. Jurnalul eșuat după acceptare nu repetă trimiterea.
- Configurarea Gmail nu salvează taskul sau setările workspace-ului. Enter în câmpurile e-mail nu declanșează salvarea setărilor workspace-ului. Dialogurile imbricate păstrează grab-ul și ciorna.
- 64 de mesaje noi în fiecare dintre cele cinci cataloage; ghidurile și F1 au ancore Gmail comune. Nu există SQL/SQLite, citire de inbox, Google Calendar, OAuth sau dependențe runtime noi.

## Teste automate efectiv executate

Suita completă finală: **654 teste trecute, 1 omis, 192,06 s**, fără avertismente în acea rulare. Omis este testul existent de junction Windows (`tests/test_stage3.py::test_junction_not_followed`), pe Linux. Toate cele 37 de cazuri noi (36 Gmail și unul pentru distribuție) au trecut. O regresie de înălțime a editorului la fereastra minimă, găsită în verificarea completă, a fost corectată fără modificarea criteriului testului existent.

`tests/test_gmail.py` include **36 de cazuri**, cu SMTP, stocare securizată și API WinCred false. Verifică:

- implicitul Outlook și absența parolei din modelul serializabil;
- adrese Google Workspace, corp lung/Unicode/indentare, MIME reparsat, CC, Date/Message-ID, mai multe documente cu nume internaționale și .eml;
- verificarea certificatelor, ordinea STARTTLS/autentificare pe 587, TLS implicit pe 465, test fără mesaj și lipsa conexiunii necriptate;
- DNS, timeout, TLS, autentificare refuzată, indicii de politică, cote/limite, mesaj respins, răspuns pierdut și eșecul QUIT după acceptare;
- acceptare/refuz parțial sau total, confirmări distincte și retry numai către refuzați, inclusiv numai CC;
- secret absent din JSON, jurnal, loguri și ZIP de backup, indisponibilitatea stocării securizate, păstrare doar în sesiune și eliminare;
- compensarea unei scrieri eșuate a profilului, schimbarea metadatelor fără acces la vault și referința pentru eliminarea ulterioară a unei credențiale vechi indisponibile;
- bindingul CredWriteW/CredReadW/CredDeleteW/CredFree cu un API nativ simulat, fără acces la Credential Manager real;
- worker fără Outlook, păstrarea ciornei la eroare/configurare, lipsa fallbackului, protecția workspace-ului la callback tardiv, read-only și absența retrimiterii după jurnal eșuat.

Un test nou în `tests/test_distribution.py` verifică faptul că verificatorul executabilului cere modulele Gmail/TLS, SMTP fals, absența rețelei și disponibilitatea simbolurilor Credential Manager. Testele existente pentru e-mail/Outlook, atașamente, ghid, internaționalizare, date și servicii sunt incluse în suita completă.

Comenzi rulate:

```sh
xvfb-run -a python -m pytest -q
python -m compileall -q src scripts/capture_gmail.py scripts/verify_distribution.py tests/test_gmail.py
python -m pip check
xvfb-run -a python -m focusdesk --smoke-test --smoke-report artifacts/gmail-smoke.json
python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir artifacts/wheel .
```

Compilarea, verificarea cerințelor Python și smoke-ul general din surse au trecut. Smoke-ul raportează `gmail_fake_smtp=true`, `gmail_network_used=false`, `frozen=false`. `credential_api_loaded=false` este rezultatul așteptat pe Linux; nu reprezintă o verificare Windows.

## Interfață reală pe date temporare

`scripts/capture_gmail.py` a trecut în **15 combinații: 5 limbi × 100%/125%/150%**, cu **36 de verificări fiecare, 540 în total și 45 de capturi**. Backendurile SMTP și vault sunt întotdeauna false; fiecare rulare are profil/workspace temporare și nu folosește parole reale.

| Limbă | 100% | 125% | 150% |
| --- | --- | --- | --- |
| Română | [manifest](capturi-ui/gmail/ro-100/manifest.json) | [manifest](capturi-ui/gmail/ro-125/manifest.json) | [manifest](capturi-ui/gmail/ro-150/manifest.json) |
| English | [manifest](capturi-ui/gmail/en-100/manifest.json) | [manifest](capturi-ui/gmail/en-125/manifest.json) | [manifest](capturi-ui/gmail/en-150/manifest.json) |
| Deutsch | [manifest](capturi-ui/gmail/de-100/manifest.json) | [manifest](capturi-ui/gmail/de-125/manifest.json) | [manifest](capturi-ui/gmail/de-150/manifest.json) |
| Français | [manifest](capturi-ui/gmail/fr-100/manifest.json) | [manifest](capturi-ui/gmail/fr-125/manifest.json) | [manifest](capturi-ui/gmail/fr-150/manifest.json) |
| Español | [manifest](capturi-ui/gmail/es-100/manifest.json) | [manifest](capturi-ui/gmail/es-125/manifest.json) | [manifest](capturi-ui/gmail/es-150/manifest.json) |

Scenariul verifică configurarea la **600×360** și compunerea la **680×540** logic, scalate prin Tk, butoanele accesibile, masca parolei și scrollul la focus, test fără trimitere/salvare, profil salvat fără modificarea workspace-ului, păstrarea ciornei la schimbarea furnizorului, contul vizibil, capabilitățile ciornelor, refuzul parțial, clickul repetat, retry explicit numai către refuzați și lipsa erorilor Tk/cheilor lipsă. La fereastra minimă, separatorul inspectorului rezervă mai întâi spațiu pentru descriere și păstrează câmpurile de sus derulabile; testul existent pentru editorul de minimum 200 px rămâne activ. În inspecția capturilor a fost corectat un buton de închidere tăiat la minimum; verificarea finală îi cere și încadrarea, și înălțimea completă.

Capturi reprezentative:

- [Configurare germană, 150%](capturi-ui/gmail/de-150/gmail-settings-minimum.png)
- [Compunere română, 125%](capturi-ui/gmail/ro-125/gmail-compose-minimum.png)
- [Rezultat parțial franceză, 150%](capturi-ui/gmail/fr-150/gmail-partial-result.png)

Reproducere fără trimitere reală:

```sh
xvfb-run -a -s '-screen 0 2400x1900x24' python scripts/capture_gmail.py --language de --scale 1.5 --output artifacts/gmail-de-150
```

## Pachet și limite

Wheel-ul final a fost construit local: **944.254 octeți**, SHA-256 `3c8cb9aa21b9532023ad7c65f4d705bd860611bf284b1e45d8643420e6f652d0`. Fișierele pachetului au fost comparate cu sursele, inclusiv modulele Gmail/WinCred, cele cinci cataloage și toate ghidurile. Wheel-ul a fost instalat într-un director separat, fără descărcări/dependențe noi; un proces pornit dintr-un director temporar a importat explicit pachetul instalat și a trecut smoke-ul UI/MIME/SMTP fals, fără resursele checkout-ului. Dependențele deja instalate ale mediului Python au fost reutilizate.

Nu s-a construit/rulat **niciun EXE Windows**, nu s-a accesat **Credential Manager real** și nu s-a autentificat ori trimis prin **Gmail/Outlook real**. Cazurile SMTP/WinCred de mai sus sunt simulări, inclusiv refuzul parțial și întreruperile. Verificarea Windows introdusă în fluxul existent de distribuție urmează să ruleze la construirea executabilului; nu este raportată drept executată aici. Nu există o măsurătoare nouă a dimensiunii sau pornirii executabilului.

Capturile sunt Linux/Tk/Xvfb, cu scalare simulată; nu certifică DPI nativ Windows, fonturile Windows, cititoare de ecran sau mutarea între monitoare. Fonturile de substituție ale mediului pot reda diferit unele simboluri; conținutul Unicode și păstrarea datelor sunt verificate separat. Într-o rulare intermediară de 156 de teste a apărut un avertisment la curățarea unei variabile Tk în testul existent de modal Tcl; rezultatul suitei finale este consemnat mai sus, separat de acea rulare.

Documentația Python și Microsoft a fost consultată din repository-urile oficiale. Accesul la paginile Google a fost refuzat de proxy cu HTTP 403; politicile actuale ale contului trebuie reconfirmate manual. [Pașii separați pentru un cont Gmail de test și executabil Windows](GMAIL.md#test-manual-necesar-separat-de-backendurile-false) includ verificarea stocării, restartului, trimiterii/livrării și revocării. Nu sunt necesare credențiale reale pentru reproducerea testelor automate.
