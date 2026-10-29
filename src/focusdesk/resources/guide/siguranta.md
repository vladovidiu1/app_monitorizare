# Arhivă, Coș, backup și restaurare

## La ce folosește
Aceste funcții separă închiderea unei cerințe, organizarea istoricului și protejarea datelor. Datele autoritare rămân în foldere/fișiere; indexurile reconstructibile nu înlocuiesc un backup.

## Unde îl găsești
**Arhivă** și **Date și backup** în stânga, meniul **Fișier** și comenzile Organizare pentru taskul selectat.

## Finalizare, arhivare și Coș
**Finalizează** schimbă statusul; taskul se găsește prin Finalizate și se poate redeschide. **Organizare → Arhivează / dezarhivează** schimbă vizibilitatea de arhivă, separat de status. **Organizare → Trimite în coș** scoate nodul din structura curentă prin operația recuperabilă existentă.

**Fișier → Coș… → Restaurează** readuce nodul și descendenții, cu UUID-urile păstrate. **Șterge definitiv** este distructivă și cere confirmare; nu o confunda cu simpla finalizare sau arhivare.

## Tutorial K: backup și restaurare potrivită
1. Salvează ciornele importante și verifică ce folder este workspace-ul curent.
2. Alege **Fișier → Backup acum (complet, cu fișiere)** dacă vrei și datele administrate; **Backup acum (metadate)** are acoperire diferită.
3. Verifică rezultatul. Setările permit retenție și o copie externă; verifică separat dacă această copie a reușit.
4. Pentru restaurare alege **Fișier → Restaurează backup într-un folder nou…** și arhiva potrivită.
5. Alege un folder nou/gol, separat de workspace-ul curent. Comanda nu suprascrie workspace-ul deschis.
6. Deschide workspace-ul restaurat și verifică taskuri, descrieri, sesiuni și documentele administrate înainte de a-l folosi în locul celui anterior.

## Ce se salvează și când
Backupul salvează starea de pe disc, nu ciornele nesalvate. Backupul complet include fișierele administrate din workspace; folderele externe nu sunt copiate automat doar pentru că sunt asociate. Căile externe restaurate pot necesita relocalizare pe alt PC.

## Greșeli frecvente
O copie pe același disc nu protejează de defectarea acelui disc. Nu testa restaurarea peste datele reale. Nu șterge manual indexurile sau fișierele operațiilor ca metodă obișnuită de reparare; folosește [diagnosticul](guide:probleme). Politicile de retenție pot elimina backupuri vechi, nu taskurile active.
