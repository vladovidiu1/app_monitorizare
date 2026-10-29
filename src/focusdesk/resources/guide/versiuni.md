# Versiuni, checkpointuri și acces la cod

## La ce folosește
Checkpointul este o copie locală de versiune a fișierelor eligibile din folderul de cod asociat. Îți permite compararea și recuperarea unei versiuni, fără să ruleze scripturile. Git este opțional și separat.

## Unde îl găsești
Tabul **Versiuni** din task. Asocierea folderului se face în [Fișiere](guide:fisiere). Setările pentru excluderi, limite și automatizări sunt în **Setări → Versiuni & VS Code**.

## Pași pentru un checkpoint
1. Salvează documentele/sursele în editorul extern. Checkpointul nu vede textul nesalvat din VS Code.
2. Verifică folderul de lucru propriu, moștenit sau comun.
3. În **Versiuni**, completează descrierea checkpointului și apasă **Salvează checkpoint**.
4. Selectează o versiune și folosește **Fișiere incluse…**, **Compară cu curentul** sau **Compară cu anteriorul**.
5. Pentru recuperare alege preferabil **Restaurează în folder separat…** și o destinație potrivită, separată de sursa activă.

## Rezultatul și salvarea
Checkpointul creează arhiva și manifestul local, conform excluderilor și limitelor configurate. Dacă nimic nu s-a schimbat, poate să nu fie creată o copie repetată. Restaurarea separată nu înlocuiește sursa curentă. **Suprascrie sursa…** este o comandă distinctă, cu protecții și confirmări; nu o folosi ca simplă vizualizare.

## Automatizări și Git
Checkpointul la încheierea sesiunii sau cel zilnic se aplică numai când este configurat și există o sursă validă. Programarea rulează cât aplicația este deschisă. Git poate afișa status/log/diff și permite un commit manual cu fișiere alese; nu există push, reset sau checkout automat din acest flux.

## Greșeli frecvente
Un checkpoint nu este backupul întregului workspace și nu include automat orice fișier vizibil în explorator. O asociere externă nu schimbă regulile backupului. Într-un [lanț de cerințe](guide:cerinte#folder-de-cod-comun), păstrează distinct proprietarul versiunilor și munca fiecărui task.
