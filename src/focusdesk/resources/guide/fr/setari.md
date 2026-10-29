# Paramètres et intégrations {#setari-si-integrari}
## Objectif {#la-ce-foloseste}
Configurez travail et intégrations facultatives. Les fonctions locales ne nécessitent ni Outlook ni compte cloud.
## Où le trouver {#unde-il-gasesti}
**Paramètres** ou **Outils → Paramètres…** : Général, Collègues, Horaires de travail, Sauvegarde, Versions et VS Code, Outlook.
## Configuration {#pasi-pentru-configurare}
1. Dans Général : nom, fuseau horaire, nombre de priorités quotidiennes.
2. **Langue** : Română, English, Deutsch, Français, Español. Appliquer au redémarrage enregistre uniquement le profil. Redémarrez manuellement quand vous le souhaitez ; brouillons/minuteur restent intacts.
3. Vérifiez jours, horaires, pauses et exceptions ; influencent la planification, pas le démarrage automatique.
4. Configurez des dossiers accessibles et Enregistrer.
## Collègues et demandeur {#colegi-si-solicitant}
Charger les collègues depuis Excel… lit la première feuille .xlsx : nom en A, code en B, sans domaine. Le sélecteur suit la convention d’adresse existante. Import remplace immédiatement la liste, séparément d’Enregistrer les paramètres ; un import invalide conserve l’ancienne. Le demandeur se sauvegarde avec la tâche.
## Outlook Classic et hors ligne {#outlook-classic-si-lucru-offline}
COM exige Outlook Classic et pywin32 inclus ; New Outlook ne le prend pas en charge. Import de métadonnées en lecture seule, notes locales. Calendrier de réservation et source des réunions distincts. Envoi explicite. Save/Send local ne confirme ni Exchange ni livraison ; ICS doit être importé. Sans Outlook : tâches, minuteur, rapports, notes et réunions manuelles restent disponibles. Aucun backend cloud caché.
## Erreurs fréquentes {#greseli-frecvente}
Langue et fuseau sont indépendants. Dates affichées jour d’abord ; YYYY-MM-DD pour saisir sans ambiguïté. ISO persistant inchangé. Ne changez pas le fuseau pour corriger un total. [Erreurs](guide:probleme).
