# BdGEN

Génération de bandes dessinées (BD) à partir d'un fichier JSON de description, en utilisant les modèles génératifs d'OpenAI (LLM pour le scénario, `gpt-image-2` pour les planches).

## Installation

Requiert Python 3.12+ et [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.sample .env
# éditer .env et y mettre votre OPENAI_API_KEY
```

## Démarrage rapide

1. **Décrire votre BD** : copiez `bdgen.sample.json` vers `mon-projet.json` et adaptez (titre, synopsis, personnages, style, nombre de pages).

2. **Lancer le wizard interactif** :

   ```bash
   uv run main.py wizard mon-projet.json
   ```

   Le wizard vous guide à travers les 3 étapes principales du pipeline, puis peut proposer une 4ᵉ étape optionnelle d'upscale local CPU si elle est activée dans la configuration. À chaque étape vous pouvez accepter, visualiser le résultat, ou saisir un feedback qui sera intégré à la régénération.

Tout est généré dans `./output/<project>/`.

## Pipeline

| Étape | Commande | Sortie |
|---|---|---|
| 1. Scénario | `script` | `bdgen-script.json` (LLM développe le synopsis en script détaillé : pages, cases, dialogues) |
| 2. Références visuelles | `references` | `references/characters/*.png`, `references/locations/*.png` (planches modèle pour cohérence) |
| 3. Composition | `compose` | `pages/page_XX.png` + couverture `cover.png` + 4ème de couv `back.png` + assemblage `<project>.pdf` (page-level avec bulles intégrées) |
| 4. Upscale local (optionnel) | `upscale` | `pages_upscaled/page_XX.*` + couverture / dos en version agrandie sur CPU local |

### Pas-à-pas (alternative au wizard)

```bash
uv run main.py script mon-projet.json
uv run main.py references ./output/mon-projet/bdgen-script.json
uv run main.py compose ./output/mon-projet/bdgen-script.json
uv run main.py upscale ./output/mon-projet/bdgen-script.json
```

### Pipeline complet non-interactif

```bash
uv run main.py run mon-projet.json
```

Si `generation_options.upscale.enabled` vaut `true`, la commande `run` enchaîne aussi l'étape d'upscale local après `compose`.

## Itérer avec feedback

Toute saisie via le wizard est consignée dans `./output/<project>/bdgen-feedback.json` et automatiquement réinjectée dans les prompts lors des régénérations. L'historique est cumulatif : chaque feedback enrichit le contexte au lieu d'écraser le précédent.

Le fichier `bdgen-feedback.json` est éditable à la main pour ajuster ou nettoyer les feedbacks.

Pour forcer une régénération complète d'une étape (hors wizard) :

```bash
uv run main.py references ./output/mon-projet/bdgen-script.json --force
```

Pour ne régénérer qu'un seul élément, supprimez son fichier puis relancez la commande — les autres seront skippés.

## Interface web

Une interface web React expose le même pipeline avec un wizard interactif et
des retouches granulaires (un personnage, un lieu, une planche, une
référence).

```bash
# 1. Construire le frontend (une fois)
cd web && npm install && npm run build && cd ..

# 2. Lancer le serveur
uv run python -m bdgen.server
# → http://127.0.0.1:8000
```

Pour le développement frontend, lancer en parallèle :

```bash
# terminal 1 (API)
uv run python -m bdgen.server

# terminal 2 (Vite dev avec HMR, proxy /api → 8000)
cd web && npm run dev
# → http://127.0.0.1:5173
```

L'interface permet de sauvegarder un projet sous forme de fichier `.bdgen`
(une archive zip du dossier projet) et d'en réimporter un. Une seule
génération est autorisée à la fois ; un bandeau s'affiche pour signaler
qu'une autre génération est en cours.

## Upscale local CPU

Une étape optionnelle `Upscale` est disponible après `Planches`.

- Elle fonctionne **entièrement en local** et **sur CPU uniquement**.
- Elle charge un vrai modèle local via `from pruna import SmashedModel`.
- Le dossier du modèle doit être disponible on-prem, par exemple `./models/p-image-upscale-v1`.

Configuration possible dans `bdgen.json` :

```json
{
   "generation_options": {
      "upscale": {
         "enabled": true,
         "mode": "target",
         "target_megapixels": 4,
         "scale_factor": 2.0,
         "output_format": "png",
         "output_quality": 90
      }
   }
}
```

Le provider, le runtime et le chemin du modèle Pruna sont fixés dans la configuration de base de l'outil ; ils ne sont plus exposés dans l'interface.

Le chargement local suit ce schéma :

```python
from pruna import SmashedModel

model = SmashedModel.load("./models/p-image-upscale-v1", device="cpu")
output_image = model.predict(image)
```

## Coût indicatif (gpt-image-2 high quality)

- BD courte (~6 pages) : **~$2** (compose page-level) + ~$0.70 (références) ≈ **$3**
- Album (~48 pages) : **~$15** + ~$2 ≈ **$17**

## Structure d'un projet généré

```
output/mon-projet/
├── bdgen-script.json       script détaillé (généré par le LLM)
├── bdgen-feedback.json     historique des feedbacks utilisateur
├── references/
│   ├── characters/         planches-modèle des personnages
│   └── locations/          planches-modèle des décors
├── pages/                  pages finales en PNG (+ cover.png et back.png)
└── mon-projet.pdf          assemblage final (cover + pages + back)
```
