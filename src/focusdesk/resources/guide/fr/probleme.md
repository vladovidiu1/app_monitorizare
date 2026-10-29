# Problèmes fréquents et limites {#probleme-frecvente-si-limitari}
## Tâche terminée introuvable {#nu-gasesc-un-task-finalizat}
Utilisez Terminées/Fermées et les bons filtres, puis Archives. Les liens projets ne changent pas l’appartenance. [Rouvrir/nouvelle demande](guide:cerinte) ont des buts différents.
## Description perdue {#descrierea-nu-s-a-pastrat}
L’assistant change le brouillon ; Enregistrer/Ctrl+S le conserve sur disque. Annuler l’éditeur agrandi restaure son texte initial. Journal explicitement ajouté ; [notes de réunion](guide:intalniri) automatiques.
## Document récent absent {#un-document-nou-nu-apare}
Vérifiez la racine Fichiers, développez, Actualiser/F5. Un dossier indisponible peut afficher une ancienne liste, sans garantir sa disponibilité. Liens/jonctions non suivis automatiquement. [Fichiers](guide:fisiere).
## Plus de programmé que de travaillé {#vad-programat-dar-nu-am-lucrat-atat}
Une réservation n’est pas du travail. Durée enregistrée et temps en direct séparés ; réunions n’ajoutent pas de travail. Vérifiez filtres et corrigez seulement les sessions terminées identifiées. [Règles](guide:activitate).
## Outlook ne répond pas ou module absent {#outlook-nu-raspunde-sau-lipseste-un-modul}
Utilisez Outlook Classic et respectez les règles de l’entreprise. `ModuleNotFoundError: win32timezone` indique pywin32 incomplet ; il faut reconstruire correctement le bundle, pas seulement installer ailleurs des packages Python. Après Send en timeout : fenêtres, Brouillons, Boîte d’envoi et Éléments envoyés à vérifier avant nouvel essai. Succès COM n’est pas livraison. [Erreurs e-mail](guide:email#erori-si-greseli-frecvente).
## Enregistrement refusé ou modifications externes {#salvare-refuzata-sau-modificari-externe}
Protégez les brouillons. F5 garde les contrôles de conflit ; n’écrasez pas aveuglément les fichiers. Le verrou d’un autre processus peut imposer la lecture seule. Vérifier l’intégrité signale les problèmes sans suppression automatique.
## Performance et sécurité {#limite-de-performanta-si-siguranta}
Première reconstruction d’index/recherche globale de descriptions peut lire davantage. Fichiers explore les dossiers ouverts ; le guide ne recherche que sa documentation incluse. Index supprimables mais pas des sauvegardes. Aucun SQL/SQLite ni synchronisation cloud des données.
## À vérifier sur votre ordinateur {#ce-trebuie-verificat-pe-calculatorul-tau}
Outlook réel/règles COM, associations, VS Code, jonctions, DPI natif et exécutable Windows dépendent de l’environnement cible. Backend simulé et mise à l’échelle Linux ne les certifient pas. Un appel réseau bloqué ne peut être annulé de force sans risque. Testez la restauration sur données temporaires, sauvegardez séparément les dossiers externes.
