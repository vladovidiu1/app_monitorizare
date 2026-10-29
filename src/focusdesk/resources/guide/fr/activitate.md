# Comprendre Activité {#activitate-intelegerea-dashboardului}
## Objectif {#la-ce-foloseste}
Tableau de bord, calendrier mensuel, tableaux et CSV partagent un calcul unique, sans double comptage parent/sous-tâche.
## Où le trouver {#unde-il-gasesti}
**Activité** ; **Calendrier mensuel · Ctrl+D** ouvre la vue secondaire.
## Tutoriel J : vérifier le travail enregistré {#tutorial-j-verifica-timpul-lucrat}
1. Choisissez 7/30/90 jours, Mois en cours, Période personnalisée ou Tout l’historique.
2. Projet ou Sans projet ; appliquez explicitement les dates personnalisées.
3. Comparez Travail enregistré et Programmé, sans les additionner comme travail.
4. Cliquez jour/projet ; **Retirer le détail** ou **Réinitialiser les filtres**.
5. Entrée/double-clic sur une session ouvre sa tâche ; retour conserve le contexte.
6. **Exporter en CSV** respecte les filtres et inclut définitions, accents et protection contre les formules Excel.
## Lire les indicateurs {#cum-interpretezi-cardurile}
Travail enregistré somme actual_seconds une fois par session, tâches terminées/archivées/manquantes incluses. Jour du début réel, sinon début programmé, dans le fuseau de l’espace. Temps en direct non enregistré séparé. Programmé inclut réservations éligibles, hors cancelled/missed. Les réunions n’augmentent aucun total.
Terminées compte des tâches distinctes avec transition done sur la période ; rouvrir/refinir ne double pas. L’historique manquant n’est pas inventé depuis updated_at. Retard actuel et statuts sont actuels, comme l’appartenance au projet. Grandes périodes agrégées par semaines/mois, granularité affichée.
## Enregistrement et erreurs fréquentes {#salvare-si-greseli-frecvente}
Les filtres ne changent aucune session. Export écrit le fichier choisi explicitement. Corrigez seulement les sessions terminées identifiables puis revérifiez les totaux. Les heures seules ne mesurent pas la productivité. [Sessions](guide:sesiuni).
