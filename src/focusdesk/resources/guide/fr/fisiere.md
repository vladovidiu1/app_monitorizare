# Fichiers et dossier du projet {#fisiere-si-folderul-proiectului}
## Objectif {#la-ce-foloseste}
Explorez le disque réel, y compris les documents ajoutés manuellement. Naviguer ne modifie pas les métadonnées et n’exige pas d’enregistrer chaque document.
## Où le trouver {#unde-il-gasesti}
**Fichiers** montre dossier de projet/de travail, fichiers de tâche (files/) et liens/références externes. Les racines héritées nomment leur source ; aucun doublon créé par chevauchement.
## Tutoriel G : associer un dossier et retrouver un document {#tutorial-g-folder-asociat-si-document-pus-manual}
1. Projet SAP, **Fichiers → Actions → Choisir le dossier du projet…**.
2. Choisissez un dossier existant ; aucun déplacement/copie.
3. Sélectionnez une tâche du projet, vérifiez « Hérité de ».
4. Développez Documents ; les sous-dossiers fermés ne sont pas parcourus récursivement.
5. Ajoutez un document dans l’Explorateur, revenez ou Actualiser/F5 dans Fichiers.
6. Entrée/double-clic ouvre un document sûr ; **Joindre à l’e-mail…** le présélectionne.
## Résultat et enregistrement {#rezultatul-si-salvarea}
Les documents apparaissent sans modifier node.json. Actualiser conserve les dossiers ouverts ; **Charger les 200 suivants** étend les grandes listes. **Plus d’espace pour Fichiers** élargit le panneau.
## Copies, références et sécurité {#copii-referinte-si-siguranta}
Ajouter… offre copie gérée ou lien externe. Copie gérée incluse en sauvegarde complète ; lien externe enregistre seulement le chemin. Retirer une référence ne supprime pas l’original, qui peut rester visible. Suppression de copie gérée distincte et confirmée. Les références peuvent être relocalisées. Scripts/exécutables ne sont pas lancés par erreur : utilisez VS Code/Explorateur. Liens symboliques/jonctions non parcourus automatiquement. Dossier réseau lent/absent ne justifie aucune suppression. [Sauvegarde](guide:siguranta).
