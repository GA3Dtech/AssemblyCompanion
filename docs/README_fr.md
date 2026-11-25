# Outils d'assemblage FreeCAD : figeage façon A2+, alignement rapide, jeux de sélection et explorateur visuel

> [!WARNING]
> **Encore expérimental : soyez prudent avec vos fichiers.** Travaillez sur
> des copies quand les fichiers sont importants, et gardez des sauvegardes.
> L'auteur ne peut en aucun cas être tenu pour responsable en cas de mauvaise
> utilisation, de transformation ou de dégradation de fichiers, ou
> d'incompatibilité de fichiers. Il est du devoir de chacun de tester l'outil
> prudemment et progressivement, selon son propre jugement et selon ses
> spécificités : ce qui a marché chez quelqu'un ne sera peut-être pas
> identique chez vous.
>
> L'organisation avec des liens externes vers d'autres fichiers, avec des
> liaisons entre les pièces, est très complexe et demande beaucoup de temps
> pour être totalement couverte. Les différentes révisions de FreeCAD
> multiplient les versions et compliquent encore potentiellement cette
> problématique. On notera toutefois que le format de fichier FreeCAD reste,
> malgré toute cette évolution, globalement très stable. Le but de cet
> atelier est justement d'en apporter encore plus, et toujours sur le long
> terme.

Version 1.3, testée sur FreeCAD 26.3rc2 (Windows).

> **Assembly Companion 0.2.0** – Ce document vient de l'époque des macros. Dans le workbench, chaque macro est devenue une commande :
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
>
> Commandes ajoutées depuis, sans équivalent macro :
>
> | Commande | Rôle | Module |
> |---|---|---|
> | Reactivate assembly | Débloque un assemblage qui ne se réactive plus (panneau de tâches bloqué, édition en cours, objet actif périmé) | `reactivate.py` |
> | Duplicate components | Clone les composants sélectionnés dans l'arbre d'assemblage | `duplicate.py` |
> | New part from selection | Nouveau fichier `PREFIXE_001a_Description.FCStd` avec un corps contenant un SubShapeBinder de la sélection (copie indépendante par défaut, ou liée à l'assemblage) | `new_part.py` |
>
> L'interface est en anglais dans le code et traduite (français, allemand, italien, espagnol) ; la langue et les réglages sont dans *Édition → Préférences → Assembly Companion*.

## Pourquoi ces outils

L'atelier Assembly intégré à FreeCAD travaille avec des **App::Link** vers les fichiers des pièces. C'est léger et associatif, mais fragile dans la durée :

- Chaque ouverture **recalcule toute la chaîne** : pièce source, noms topologiques, liaisons. Il suffit d'un changement de version de FreeCAD, d'un fichier déplacé ou renommé, ou d'une petite différence de recalcul pour que des liaisons sautent.
- Les SubShapeBinder des pièces qui prennent appui sur l'assemblage créent des **références cycliques** : la pièce dépend de l'assemblage, qui dépend de la pièce par son Link.
- « Import link » rapatrie tout l'historique paramétrique des pièces, ce qui donne des fichiers énormes.
- Les pièces liées doivent **rester chargées** : tous les fichiers sources de l'assemblage sont ouverts en même temps, et l'arbre de construction à gauche les liste tous, avec tout leur historique. Dès qu'on dépasse quelques pièces, l'arbre devient interminable, réparti sur une multitude de fichiers ouverts, et c'est ingérable. Pire : fermer un de ces fichiers pour faire le ménage dans l'arbre fait disparaître ses pièces de l'assemblage (piège classique dans un assemblage hybride, mi-figé, mi-lié).

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

**Containers et sous-assemblages** : un Std_Part, un groupe d'import STEP (`App::LinkGroup`, avec ses solides ou ses Links) et un sous-assemblage (inséré comme Link, ou comme sous-assemblage de l'atelier Assembly de FreeCAD 26.x, sur plusieurs niveaux) sont figés avec leurs pièces, leurs noms, leurs placements, leurs couleurs et leurs liaisons internes : un sous-assemblage devient un assemblage figé rangé dans `Solides_figes`, et les liaisons du grand assemblage qui pointent dans le sous-assemblage restent valides. La préférence « Figer les containers et sous-assemblages » permet aussi d'en faire **un seul solide** par composant (plus léger, rigide ; la nomenclature garde la liste des pièces qu'il contient). Si un élément ne peut pas être figé (lien cassé…), le composant reste lié et un message dit pourquoi : jamais de gel à moitié. Le gel est une seule étape d'annulation.

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

Ce qui change : le dossier est lu avec `os.scandir` (sous Windows, taille et date arrivent avec la liste, sans requête par fichier) ; le résultat du scan est mis en cache, la vue s'affiche aussitôt depuis ce cache et un nouveau scan en arrière-plan ne la reconstruit que si quelque chose a changé ; les vignettes sont réduites et mises en cache sur le disque local, chaque `.FCStd` n'étant décompressé qu'une fois tant qu'il ne change pas ; 16 extractions tournent en parallèle hors de l'interface ; une seule feuille de style sert pour toutes les cartes. Le cache se trouve par défaut dans le dossier cache utilisateur de FreeCAD (`assembly_explorer_cache`). Les préférences permettent de choisir un autre dossier (utile quand le système vide son cache tous les jours) ; au changement, l'atelier propose de déplacer le cache existant ou de repartir à vide. Le dossier est réservé à l'utilisateur courant. Le bouton « Vider le cache » le supprime sans risque : vignettes et parcours sont reconstruits au parcours suivant.

**Favoris et tags** : clic droit sur l'en-tête d'un dossier → « Ajouter aux favoris » : le dossier est épinglé en haut (étoile), le bouton ★ liste les favoris et la case « Favoris seulement » filtre la vue. Clic droit sur une vignette ou un dossier → « Tag » : un emoji ou un #tag court s'affiche sur la vignette. Favoris et tags sont gardés dans les préférences de l'utilisateur, pas dans les dossiers ; un favori déplacé ou supprimé est signalé (menu ★) sans gêner l'explorateur.

**Rafraîchissement ciblé** : un clic droit sur l'en-tête d'un dossier propose « Rafraîchir ce dossier », « Rafraîchir ce dossier et ses sous-dossiers » et « Ouvrir dans le gestionnaire de fichiers ». Un document enregistré depuis FreeCAD sous le dossier maître (nouvelle pièce, nouvelle révision, simple enregistrement) rafraîchit seul son dossier. « Tout rafraîchir » relit tout l'arbre, mais ne reconstruit que les dossiers qui ont changé : le défilement, le filtre et les autres vignettes restent en place. La préférence « Parcours complet de la bibliothèque » choisit si l'ouverture d'un explorateur relance un parcours complet (à chaque fois, une fois par session, ou seulement avec « Tout rafraîchir »).

## Ce qu'on a appris en chemin (notes techniques)

- **Forme morte = aller-retour BREP** (`exportBrepToString` / `importBrepFromString`). Une simple `Shape.copy()` garde l'historique topologique, qui renvoie au document source : les liaisons cassent alors à la réouverture. Le BREP conserve la géométrie et la numérotation des faces, arêtes et sommets.
- **Vider puis réécrire les références** après chaque reciblage d'un Link, même si le texte (`Edge3`) ne change pas. Une référence garde en interne un nom topologique calculé sur l'ancienne cible. FreeCAD l'enregistre, ne le retrouve plus à la réouverture et marque l'élément `?`.
- En 26.3, les références des liaisons sont rattachées **directement au Link** (`Reference1 = (Link, ["Face20", "Face20"])`), pas à l'assemblage.
- Un App::Link **relaie les attributs de sa cible** : `hasattr(link, 'X')` peut être vrai sans que la propriété existe sur le Link. Il faut tester `'X' in obj.PropertiesList`.
- L'observateur de sélection peut transmettre l'**objet le plus profond** (`Pad` + `Edge10`) au lieu du chemin complet. On récupère le chemin avec `Gui.Selection.getSelectionEx(doc, 0)`.
- Un Link **ignore le placement de sa cible** : dans un assemblage, c'est le Link qu'on déplace.
- `Part.Conic.Center` est déprécié depuis 26.3 (`Location` à la place).

## Limites connues

- **Placement manuel** : l'outil *Transformer* de FreeCAD (clic droit →
  Transformer) reste bien pratique pour placer une pièce à la main, y compris
  dans un assemblage de l'atelier Assembly intégré.
- **Liaisons sur un SubShapeBinder** : avec l'atelier Assembly intégré, une
  liaison entre un SubShapeBinder et une pièce peut faire apparaître un
  décalage dans la vue 3D. Ce n'est pas un problème pour l'assemblage,
  seulement un effet d'affichage à connaître.

- Explorateur : « Figer à l'insertion » ignore les fichiers dont l'objet principal est un Std_Part (multi-corps), comme le figeage.

- Les Links vers des **Body / Part::Feature** et vers des **conteneurs Std_Part** sont figés. Un conteneur devient un Std_Part figé (`Fige_<nom>`, dans `Solides_figes`) qui contient une copie morte de chaque Body à sa place ; les Part imbriqués sont figés aussi. Les liaisons qui visent un corps du conteneur (`CoteA.Body001.Face6`) sont réécrites vers sa copie (`CoteA.Fige_Body001.Face6`), et inversement par Relier. Les autres objets du conteneur (esquisses, Links internes…) sont ignorés, avec un message.
- La mise à jour automatique d'une copie figée sans relier (recalage géométrique) a été abandonnée : les positions stockées dans les liaisons n'étaient pas recalculées. Relier, réparer puis refiger est la méthode fiable.
- Le gizmo d'Aligner reste expérimental.
- Les sous-assemblages figés imbriqués et le passage vers une autre version de FreeCAD restent à tester sur des projets réels.

## Prochaine étape : le workbench

Transformer ces macros (et le panneau des jeux de sélection) en commandes d'un workbench (icônes, barre d'outils, menu, `package.xml`), installable depuis l'Addon Manager par l'URL d'un dépôt Git. Les commentaires du code sont déjà en anglais ; les messages affichés à l'utilisateur sont en français.

## Licence

Tout le code est sous **LGPL-2.1-or-later**, la même licence que FreeCAD, et sans CLA. Chaque fichier porte l'en-tête `SPDX-License-Identifier: LGPL-2.1-or-later`. L'explorateur reprend du code de PiStock (© GA3Dtech), relicencié en LGPL par son auteur pour ce projet. Le texte complet de la licence (fichier `LICENSE`) est à ajouter dans le dépôt Git, par exemple avec le choix de licence proposé par GitHub ou depuis gnu.org.
