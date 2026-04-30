- Il faudrait créer un mode "ultra draft" qui utilise des modèles à très bas coûts autant pour l'écriture du scénario que la génération d'images.
- On va aussi proposer par défaut l'utilisation de Sonnet, avec la possibilité de prendre opus également.
- La génération des images de référence en mode draft doit utiliser openai-image-1.5 et en mode définitif la version 2
- Lorsque l'on clique sur le bouton "suivre" ou qu'on ouvre un projet, il faudrait qu'on arrive directement à la bonne étape et pas sur l'étape initiale
- Export en .CBZ en plus du format .PDF

- Lorsque le style est un manga, on indique à l'outil d'inverser le sens de lecture pour être fidèle au format
- En plus des personnages et des décors, on va permettre optionnelement à l'utilisateur d'ajouter un ou plusieurs objet/produits/référence à l'histoire. Par exemple, si la BD traite d'un certain livre on va permettre l'upload de celui-ci et un champs description qui sera utilisé pour intégrer cet élément à l'histoire et sa photo qui permettra d'en intégrer une version caricaturée dans le style de l'histoire à la bd
- Comme pour les photos des persos, je souhaite voir l'image utilisée pour le style et pouvoir la supprimer par exemple
- Comme pour les persos, on va permettre l'utilisation de photo pour les décors
- Attention il y'a un bug: l'outil génère la couverture et le 4ème de couverture à la dernière étape même si elle n'est pas cochée dans le setup
- Pour les objets il est indispensable de mieux prendre en compte l'objet de base. Il est autorisé par exemple d'en reprendre les textes et logos contrairement au images de style
- Pour les objets, pas besoin de dire si oui ou non le système peux en ajouter. On part du principe que c'est oui, il peut en ajouter dans le scénario mais pas dans les réfs.
- Option pour ajouter des planches 
- Permettre différents formats de BD (portrait, paysage, carré, ...)
- Dans les objets, faire en sorte que les logos et pictos fournis soient reproduits avec fidélité
- Utiliser des chemins relatifs pour les assets dans les flux JSON, créer un script pour corriger les existants et effacer le script ensuite

- Ajouter un bouton permettant la regénération d'un élément de l'écriture sans que cela ne touche au reste.
- Ajouter un bouton permettant la regénération d'un élément des références sans que cela ne touche au reste.

- La génération du personnage dans les planches est très bonne. Par contre quelque chose c'est cassé car il n'y a plus de consistance du perso entre les planches et les références ne semble pas utilisées. A revoir

- Bien compter chaque appel aux modèles dans les stats. Là par exemple en cas de regénération ou de retouche rien n'est compté. Centraliser le comptage afin d'éviter de perdre de l'information.

- Une fois la retouche ciblée lancée ou lorsqu'on demande une regénération, griser tout le composant de lecture sur la page actuelle et mettre au centre une animation pour patienter.

- On va mettre tout ça dans 