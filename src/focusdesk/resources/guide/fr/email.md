# E-mail et pièces jointes {#e-mail-si-atasamente}
## Objectif {#la-ce-foloseste}
Rédigez un nouveau message modifiable avec description complète, puis envoyez-le via Outlook Classic (par défaut) ou Gmail avec un mot de passe d’application. Aucun Reply/ReplyAll ni lecture de boîte de réception. Modifier le message ne modifie pas la tâche.
## Où le trouver {#unde-il-gasesti}
**Ctrl+M**, **Organiser → E-mail depuis la tâche…**, **Plus → Rédiger un e-mail…** ou **Fichiers → Joindre à l’e-mail…**.
## Tutoriel H : description et documents choisis {#tutorial-h-descriere-completa-si-documente-alese}
1. Pour la description non enregistrée, choisissez texte actuel (défaut), dernière version enregistrée ou Annuler ; aucune autre métadonnée enregistrée.
2. Renseignez À, CC, Objet. N’utilisez jamais une adresse fictive du tutoriel pour un vrai envoi.
3. Modifiez Message ; texte complet, sauts de ligne et accents restent, sans ancienne limite de 600 caractères. Actualiser ne le régénère pas.
4. Choisissez les [pièces jointes](#atasamente) nécessaires.
5. **Ouvrir le brouillon dans Outlook** pour relire, ou **Envoyer** puis confirmer destinataires, objet et nombre/taille des fichiers.
## Pièces jointes {#atasamente}
Ajouter des fichiers… accepte plusieurs documents ; Depuis les fichiers de la tâche/du projet… inclut ceux ajoutés manuellement. Retirer de l’e-mail change seulement la sélection. Même nom à des chemins différents : fichiers distincts. Dossiers non compressés/joints automatiquement. Les fichiers sont revérifiés avant transmission ; un refus arrête tout, sans envoi partiel.
## Résultats et enregistrement {#rezultate-si-salvare}
Un brouillon ouvert n’est pas envoyé. Transmis signifie que Send a réussi, pas que le destinataire a reçu. Vérifiez Boîte d’envoi/Éléments envoyés. Le journal conserve résultat et noms des fichiers, pas le corps complet.
## Erreurs et précautions {#erori-si-greseli-frecvente}
Entrée n’envoie pas. Erreurs conservent le formulaire. Après délai dépassé/résultat incertain, vérifiez Outlook avant **J’ai vérifié dans Outlook…** puis nouvel essai explicite ; jamais automatique. Échec du journal ne justifie pas un renvoi. Le formulaire n’est pas un brouillon persistant après fermeture. [Outlook](guide:setari#outlook-classic-si-lucru-offline).

## Configurer Gmail {#gmail-configurare}
Outlook Classic reste le fournisseur par défaut. Ouvrez **Paramètres → Intégrations → E-mail** ou **Configurer Gmail…** dans le formulaire. Saisissez l’adresse du compte Gmail/Google Workspace (domaines personnalisés acceptés) et un nom affiché facultatif. Aucun expéditeur arbitraire ni alias non vérifié n’est proposé.

Activez la validation en deux étapes dans votre compte Google puis générez manuellement un mot de passe d’application dans le navigateur à `https://myaccount.google.com/apppasswords`, via **Comment obtenir un mot de passe d’application ?**. Saisissez ce mot de passe masqué, ni votre mot de passe habituel ni des codes de validation. Seules les espaces de présentation sont retirées. Les règles de l’organisation, Advanced Protection ou d’autres restrictions peuvent empêcher sa création. Modifier le mot de passe Google peut le révoquer. Ce n’est ni OAuth ni « Sign in with Google ».

**Mémoriser de façon sécurisée sur cet ordinateur** utilise le Gestionnaire d’identifiants Windows. Le secret est exclu de l’espace de travail, des fichiers JSON, du journal et des sauvegardes. Sans stockage sécurisé, il reste uniquement en mémoire pour la session ; ressaisissez-le après un redémarrage. **Enregistrer les paramètres e-mail** modifie seulement le profil de l’ordinateur, pas les modifications de tâche. Si un ancien identifiant ne peut pas être supprimé, un avertissement et sa référence restent disponibles pour une suppression ultérieure.

**Tester la connexion** vérifie TLS et l’authentification, sans envoyer de message ni enregistrer les champs. La réussite ne garantit ni l’acceptation ni la livraison d’un e-mail. **Supprimer les identifiants** efface le secret local et les métadonnées ; révoquez le mot de passe séparément dans le compte Google.

## Envoi Gmail et résultats {#gmail-trimitere}
Dans le même formulaire, choisissez **Envoyer via → Gmail — adresse du compte**. Le changement de fournisseur et la configuration conservent À, CC, objet, corps et pièces jointes. Le calendrier Outlook reste inchangé. Gmail ne nécessite pas Outlook ; l’envoi et le test nécessitent Internet, tandis que le reste de FocusDesk reste hors ligne.

**Envoyer** demande confirmation du compte et du message. SMTP utilise `smtp.gmail.com:465`, TLS vérifié et des délais d’attente, jamais une connexion non chiffrée. Tous les documents sont lus avant la remise ; un fichier manquant ou illisible bloque un message incomplet.

**Message accepté par le serveur Gmail pour envoi** ne confirme ni la livraison ni la lecture. Une acceptation partielle indique les destinataires acceptés/refusés et les codes SMTP. **Préparer uniquement les destinataires refusés…** retire les destinataires déjà acceptés et nécessite une nouvelle confirmation d’envoi. Aucun renvoi automatique ni basculement vers Outlook. Une coupure pendant la remise peut rendre le résultat incertain : vérifiez Gmail/les destinataires avant **J’ai vérifié dans Gmail…**. Changer de fournisseur ne débloque pas le renvoi.

SMTP ne crée aucun brouillon dans Gmail web. **Enregistrer en .eml (local)…** crée un fichier local contenant le corps et les pièces jointes, sans envoi ni synchronisation. **Ouvrir le brouillon dans Outlook** est réservé à Outlook. Le journal conserve fournisseur, compte, destinataires, objet, date, Message-ID et noms de fichiers, jamais le secret ni la conversation SMTP. Une erreur du journal après acceptation ne justifie pas un renvoi.

Vérifiez séparément Internet/DNS, délai d’attente, TLS/certificats, authentification, destinataires et limites du compte. Les codes ne distinguent pas toujours un mot de passe incorrect, révoqué ou une restriction du compte. Les erreurs conservent le formulaire ; ne désactivez pas TLS pour les contourner.
