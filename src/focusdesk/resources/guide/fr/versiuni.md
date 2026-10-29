# Versions, checkpoints et code {#versiuni-checkpointuri-si-acces-la-cod}
## Objectif {#la-ce-foloseste}
Un checkpoint est une copie locale des fichiers de code admissibles enregistrés, pour comparer/restaurer. Git est distinct et facultatif ; aucun script exécuté.
## Où le trouver {#unde-il-gasesti}
**Versions** de tâche ; source dans [Fichiers](guide:fisiere), exclusions/limites dans **Paramètres → Versions et VS Code**.
## Créer un checkpoint {#pasi-pentru-un-checkpoint}
1. Enregistrez les fichiers dans l’éditeur externe.
2. Vérifiez la racine propre/héritée/partagée.
3. Description puis **Enregistrer un checkpoint**.
4. Fichiers inclus…, Comparer avec l’état actuel/précédent.
5. Préférez **Restaurer dans un dossier distinct…**, hors de la source active.
## Résultat et enregistrement {#rezultatul-si-salvarea}
Archive/manifeste respectent exclusions et limites ; un état identique peut ne créer aucune copie. Restauration distincte ne modifie pas la source. Écraser la source… est une action distincte confirmée et protégée.
## Automatisation et Git {#automatizari-si-git}
Checkpoints de fin de session/quotidiens nécessitent réglages et source valide. Planification seulement lorsque FocusDesk tourne. Git : statut/log/diff et commits manuels de fichiers choisis, sans push/reset/checkout automatique.
## Erreurs fréquentes {#greseli-frecvente}
Un checkpoint n’est pas une sauvegarde complète de l’espace. Association externe ne change pas la couverture. Distinguez versions et travail de chaque [demande](guide:cerinte#folder-de-cod-comun).
