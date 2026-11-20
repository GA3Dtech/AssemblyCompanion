# Outils d'assemblage FreeCAD : figeage façon A2+, alignement rapide, jeux de sélection et explorateur visuel

Version 1.3, testée sur FreeCAD 26.3rc2 (Windows).

> **Assembly Companion 0.1.0** – Ce document vient de l'époque des macros. Dans le workbench, chaque macro est devenue une commande :
>
> | Macro | Commande du workbench | Module |
> |---|---|---|
> | assembly_Figer_composants | Freeze parts | `freeze.py` |
> | assembly_Relier_aux_sources | Relink to sources | `freeze.py` |
> | assembly_Supprimer_liaisons | Delete part joints | `freeze.py` |
> | assembly_Diagnostic_figeage | Check frozen assembly | `freeze.py` |
> | assembly_Reparer_copies_figees | Repair frozen copies | `freeze.py` |
> | assembly_Aligner_elements | Align elements | `align.py` |
> | assembly_Inserer_composant | Insert component (visual) | `explorer.py` |
> | assembly_Explorateur_local | Local parts explorer | `explorer.py` |
> | assembly_JeuxDeSelection | Selection sets | `selection_sets.py` |
>
> Les sections « Installation » et « Contenu » ci-dessous concernent les macros ; pour le workbench, voir le README principal.

## Pourquoi ces outils

L'atelier Assembly intégré à FreeCAD travaille avec des **App::Link** vers les fichiers des pièces. C'est léger et associatif, mais fragile dans la durée :

- Chaque ouverture **recalcule toute la chaîne** : pièce source, noms topologiques, liaisons. Il suffit d'un changement de version de FreeCAD, d'un fichier déplacé ou renommé, ou d'une petite différence de recalcul pour que des liaisons sautent.
- Les SubShapeBinder des pièces qui prennent appui sur l'assemblage créent des **références cycliques** : la pièce dépend de l'assemblage, qui dépend de la pièce par son Link.
- « Import link » rapatrie tout l'historique paramétrique des pièces, ce qui donne des fichiers énormes.

A2+ stockait au contraire un **solide mort** dans l'assemblage. Le fichier se rouvre à l'identique, des années plus tard. Ces outils apportent ce comportement à l'atelier Assembly, en gardant ses liaisons et son solveur.

## Contenu

| Fichier | Rôle |
|---|---|
| `assembly_figeage.py` | Module commun (utilisé par toutes les macros sauf Aligner) |
| `assembly_Figer_composants.FCMacro` | Figer : chaque Link pointe vers une copie BREP morte stockée dans l'assemblage |
| `assembly_Relier_aux_sources.FCMacro` | Relier : le Link pointe de nouveau vers le Body source, pour modifier la pièce |
| `assembly_Supprimer_liaisons.FCMacro` | Supprimer toutes les liaisons (et le blocage) des pièces sélectionnées |
| `assembly_Aligner_elements.FCMacro` | Placement rapide de corps dans un conteneur Std_Part (autonome) |
| `assembly_explorer.py` | Module de l'explorateur local et de l'insertion visuelle (dérivé de PiStock Local Explorer) |
| `assembly_Explorateur_local.FCMacro` | Explorateur à vignettes d'un dossier master, dans un onglet central (clic = ouvrir) |
| `assembly_Inserer_composant.FCMacro` | Le même explorateur en panneau ancré, à côté de la vue 3D (clic = insérer dans l'assemblage) |
| `assembly_JeuxDeSelection.FCMacro` | Panneau de jeux de sélection nommés, enregistrés dans le fichier (autonome) |
| `assembly_Diagnostic_figeage.FCMacro` | Vérifier que toutes les références des liaisons sont valides |
| `assembly_Reparer_copies_figees.FCMacro` | Nettoyer des assemblages figés avec les toutes premières versions |

## Installation

1. Fermer FreeCAD.
2. Copier **tous** les fichiers dans le dossier des macros (Macro → Macros…, le chemin est affiché en bas de la fenêtre), par exemple `C:\Users\<nom>\AppData\Roaming\FreeCAD\v26-3\Macro\`.
3. Supprimer les anciennes versions et les doublons « (1) », « (2) » créés par le navigateur. Sinon, c'est une ancienne version qui risque de tourner.

## Sélection (Figer, Relier, Supprimer liaisons)

| Sélection | Effet |
|---|---|
| Rien | Tout le document (Figer et Relier) |
| Une pièce dans l'arbre, ou une face d'une pièce dans la vue 3D | Cette pièce |
| Une copie dans le groupe `Solides_figes` | Toutes les occurrences de cette pièce (vis montée 10 fois…) |
| Une sélection sans pièce d'assemblage | Rien (message dans la vue rapport) |

## Flux de travail

**Figer un assemblage** : lancer Figer composants. Les copies sont rangées, masquées, dans le groupe `Solides_figes`. Chaque copie garde le fichier source, l'objet, la date et la version de FreeCAD (groupe de propriétés « Figeage »).

**Modifier une pièce** :

1. Sélectionner la pièce, puis lancer **Relier aux sources**.
2. Modifier le fichier source.
3. Réparer les liaisons qui ont bougé. Si c'est trop cassé, lancer **Supprimer liaisons** puis recréer les liaisons.
4. Resélectionner la pièce et lancer **Figer composants**.

> Pour une pièce montée plusieurs fois, relier et refiger **toutes** les occurrences ensemble, en sélectionnant la copie dans `Solides_figes`.

**Vérifier** : lancer Diagnostic figeage, enregistrer, fermer, rouvrir, puis relancer le diagnostic. Le résultat attendu : `historique topo = 0` pour chaque copie, toutes les références OK, aucun `?`.

## Aligner éléments

Pour les assemblages statiques : des corps dans un conteneur Std_Part.

1. Lancer la macro, puis cliquer une **face, arête ou sommet** dans la vue 3D, sur le corps à déplacer (origine).
2. Cliquer un élément sur un autre corps (cible). Le corps s'aligne aussitôt.
3. Ajuster dans le panneau :
   - **Objet déplacé** : le Body ou son conteneur parent.
   - **Inverser** : par défaut les faces se mettent en appui, normales opposées.
   - **Translation seule** : garde l'orientation.
   - **Décalage X/Y/Z et rotations** : exprimés dans le repère de la cible, avec un bouton +90°.
   - **Gizmo** : optionnel, expérimental.
4. OK valide en une seule étape d'annulation ; Annuler remet tout en place.

Repère pris sur chaque élément : face plane (centre, normale) ; cylindre, cône ou sphère (axe) ; arête circulaire (centre, axe) ; arête droite (milieu, direction) ; sommet (point, translation seule).

Dans un assemblage de l'atelier Assembly, le solveur remet en place une pièce qui a des liaisons. Il faut donc supprimer ses liaisons avant de la placer avec Aligner.

## Jeux de sélection

La gestion de la sélection dans FreeCAD devient ingérable dès qu'il y a beaucoup de pièces ou des pièces cachées : STEP éclatés en centaines de pièces, vieux assemblages dont on veut extraire une partie pour une simulation ou un rendu, mêmes éléments resélectionnés dix fois de suite en modélisation… Cette macro ouvre un **panneau ancré** à droite.

- **Stockés dans le document** : les jeux sont rangés dans le groupe « Jeux de sélection » et enregistrés avec le `.FCStd`. Les pièces ne sont jamais déplacées.
- **Chemin complet** : chaque membre est mémorisé par son chemin depuis la racine, ce qui distingue les différentes occurrences d'une même pièce (Links).

| Groupe | Actions |
|---|---|
| Composer | Nouveau, + Ajouter, − Retirer, Remplacer (depuis la sélection courante) ; Filtre… (par nom ou regex, y compris dans les noms des sous-ensembles parents, taille, volume, visibles seulement) ; Nettoyer (pièces disparues) ; Renommer, Dupliquer, Supprimer |
| Utiliser | Sélectionner, Sélect. + (ajout), Zoom ; Afficher, Masquer, Isoler ; Isoler transp. (le reste devient transparent et non sélectionnable) ; Tout afficher ; Rétablir aspect |
| Combiner | A ∪ B, A ∩ B, A − B, chaque fois dans un nouveau jeu |

Double-cliquer sur un jeu de la liste le sélectionne. Supprimer un jeu ne touche pas aux pièces.

Exemple : importer un STEP éclaté, faire un jeu « Visserie » par le filtre « vis|écrou|rondelle » (regex), un jeu « Châssis » à la main, puis « Châssis − Visserie », et l'isoler en transparence pour exporter ou simuler juste cette partie.

## Explorateur local et insertion visuelle

Dérivé de l'explorateur local de [PiStock](https://github.com/pistock-org/PiStock), avec la même présentation : un bloc par dossier, indenté selon la profondeur, chacun avec une bande de mini-vignettes extraites des `.FCStd`, sans ouvrir les fichiers. Le dossier master est mémorisé ; au premier lancement, la macro reprend celui de PiStock.

**Ouvrir** (`assembly_Explorateur_local`) : l'explorateur s'ouvre en onglet central, et un clic ouvre le fichier.

**Insérer** (`assembly_Inserer_composant`) : l'explorateur s'ouvre en panneau ancré à droite, pour garder la vue 3D visible. Un clic sur une vignette insère la pièce comme App::Link dans l'**assemblage ou le Std_Part actif**, ou à la racine du document s'il n'y en a pas.

- Le fichier source n'a **pas besoin d'être ouvert** : il est chargé en arrière-plan, sans onglet.
- La macro insère le Std_Part racine du fichier (par exemple celui créé par « Wrap bodies » de PiStock), sinon le Body, sinon le solide. S'il y a plusieurs candidats, elle demande lequel prendre.
- Avec l'option **« Figer à l'insertion »**, la pièce est figée aussitôt. Cela ne marche que pour les Body, comme le figeage.
- La pièce est insérée à l'origine ; on la place ensuite avec ses liaisons ou avec Aligner.

Dans les deux modes, le **filtre** cherche dans les noms de fichiers et de dossiers, et le **clic droit** propose Insérer, Ouvrir et Ouvrir le dossier.

### Vitesse (mesurée sur 3600 fichiers, 150 dossiers, 20 ms de latence réseau simulée par fichier)

| | Original PiStock | Nouvelle version |
|---|---|---|
| FreeCAD bloqué | 81 s | non : la vue apparaît en ~2,5 s |
| Toutes les vignettes, 1re fois | 81 s | ~9 s, en arrière-plan |
| Toutes les vignettes, fois suivantes | 81 s | ~4,5 s, depuis le cache |

Ce qui change : le dossier est lu avec `os.scandir` (sous Windows, taille et date arrivent avec la liste, sans requête par fichier) ; le résultat du scan est mis en cache, la vue s'affiche aussitôt depuis ce cache et un nouveau scan en arrière-plan ne la reconstruit que si quelque chose a changé ; les vignettes sont réduites et mises en cache sur le disque local, chaque `.FCStd` n'étant décompressé qu'une fois tant qu'il ne change pas ; 16 extractions tournent en parallèle hors de l'interface ; une seule feuille de style sert pour toutes les cartes. Le cache se trouve dans le dossier cache utilisateur de FreeCAD (`assembly_explorer_cache`) et peut être supprimé sans risque.

## Ce qu'on a appris en chemin (notes techniques)

- **Forme morte = aller-retour BREP** (`exportBrepToString` / `importBrepFromString`). Une simple `Shape.copy()` garde l'historique topologique, qui renvoie au document source : les liaisons cassent alors à la réouverture. Le BREP conserve la géométrie et la numérotation des faces, arêtes et sommets.
- **Vider puis réécrire les références** après chaque reciblage d'un Link, même si le texte (`Edge3`) ne change pas. Une référence garde en interne un nom topologique calculé sur l'ancienne cible. FreeCAD l'enregistre, ne le retrouve plus à la réouverture et marque l'élément `?`.
- En 26.3, les références des liaisons sont rattachées **directement au Link** (`Reference1 = (Link, ["Face20", "Face20"])`), pas à l'assemblage.
- Un App::Link **relaie les attributs de sa cible** : `hasattr(link, 'X')` peut être vrai sans que la propriété existe sur le Link. Il faut tester `'X' in obj.PropertiesList`.
- L'observateur de sélection peut transmettre l'**objet le plus profond** (`Pad` + `Edge10`) au lieu du chemin complet. On récupère le chemin avec `Gui.Selection.getSelectionEx(doc, 0)`.
- Un Link **ignore le placement de sa cible** : dans un assemblage, c'est le Link qu'on déplace.
- `Part.Conic.Center` est déprécié depuis 26.3 (`Location` à la place).

## Limites connues

- Explorateur : « Figer à l'insertion » ignore les fichiers dont l'objet principal est un Std_Part (multi-corps), comme le figeage.

- Seuls les Links vers des **Body / Part::Feature** sont figés. Les conteneurs Std_Part multi-corps sont ignorés, avec un message.
- La mise à jour automatique d'une copie figée sans relier (recalage géométrique) a été abandonnée : les positions stockées dans les liaisons n'étaient pas recalculées. Relier, réparer puis refiger est la méthode fiable.
- Le gizmo d'Aligner reste expérimental.
- Les sous-assemblages figés imbriqués et le passage vers une autre version de FreeCAD restent à tester sur des projets réels.

## Prochaine étape : le workbench

Transformer ces macros (et le panneau des jeux de sélection) en commandes d'un workbench (icônes, barre d'outils, menu, `package.xml`), installable depuis l'Addon Manager par l'URL d'un dépôt Git. Les commentaires du code sont déjà en anglais ; les messages affichés à l'utilisateur sont en français.

## Licence

Tout le code est sous **LGPL-2.1-or-later**, la même licence que FreeCAD, et sans CLA. Chaque fichier porte l'en-tête `SPDX-License-Identifier: LGPL-2.1-or-later`. L'explorateur reprend du code de PiStock (© GA3Dtech), relicencié en LGPL par son auteur pour ce projet. Le texte complet de la licence (fichier `LICENSE`) est à ajouter dans le dépôt Git, par exemple avec le choix de licence proposé par GitHub ou depuis gnu.org.
