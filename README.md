# BdGEN

BdGEN est une application de generation de bandes dessinees a partir d'une description de projet. Elle combine un backend Python/FastAPI, une interface React et une application Electron portable pour Windows.

Le projet peut etre utilise de deux facons principales :

- **Mode web** : le serveur local est lance manuellement, puis l'interface est ouverte dans un navigateur.
- **Mode exe portable** : un executable Windows autonome lance l'application Electron et son serveur local embarque.

## Prerequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js et npm
- Windows pour la construction et l'utilisation de l'exe portable

## Mode Web

Le mode web est le plus pratique pour le developpement, le debug et les tests rapides. Il lance le backend FastAPI localement, puis sert l'interface web dans le navigateur.

### Installation

Depuis la racine du depot :

```bash
cd bdgen
uv sync
copy .env.sample .env
```

Editez ensuite `bdgen/.env` si vous voulez fournir les cles API par fichier d'environnement :

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
REPLICATE_API_TOKEN=...
```

L'application web permet aussi de configurer les cles via son coffre local chiffre au lancement.

### Lancer l'application web

Construisez d'abord le frontend React dans les assets statiques du serveur :

```bash
cd bdgen/web
npm install
npm run build
```

Lancez ensuite le serveur FastAPI :

```bash
cd ..
uv run python -m bdgen.server
```

Ouvrez l'application dans le navigateur :

```text
http://127.0.0.1:8000
```

### Developpement frontend

Pour travailler avec le rechargement a chaud de Vite, utilisez deux terminaux.

Terminal 1, API :

```bash
cd bdgen
uv run python -m bdgen.server
```

Terminal 2, frontend :

```bash
cd bdgen/web
npm run dev
```

Ouvrez ensuite :

```text
http://127.0.0.1:5173
```

Dans ce mode, Vite sert l'interface et proxy les appels API vers le serveur local.

### Donnees en mode web

Par defaut, les projets generes sont stockes sous :

```text
bdgen/output/<nom-du-projet>/
```

Le serveur peut utiliser un autre dossier si la variable `BDGEN_OUTPUT_ROOT` est definie.

## Mode Exe Portable

Le mode exe portable est le mode utilisateur final. Il produit un executable Windows sous `build/portable/`, sans installateur. L'utilisateur lance directement `BdGEN 0.1.0.exe`.

Dans ce mode :

- Electron affiche la fenetre de l'application.
- Le serveur FastAPI est lance automatiquement en arriere-plan.
- Le backend PyInstaller est embarque dans les ressources de l'application.
- Il n'est pas necessaire d'ouvrir un navigateur ni de lancer `uv run python -m bdgen.server`.

### Construire l'exe portable

Depuis la racine du depot :

```bash
make portable
```

La commande enchaine :

1. `uv sync`
2. build du frontend React
3. build du serveur local avec PyInstaller
4. build de l'application Electron portable

Le resultat attendu est :

```text
build/portable/BdGEN 0.1.0.exe
```

`make build` et `make desktop` produisent aussi l'executable portable. Il n'y a plus de cible installateur.

### Lancer l'exe portable

Double-cliquez sur :

```text
build/portable/BdGEN 0.1.0.exe
```

Au lancement, l'application affiche sa fenetre Electron personnalisee. Si le coffre de secrets n'est pas encore configure ou deverrouille, la page de verrouillage apparait avant l'acces au reste de l'application.

### Donnees en mode exe portable

En mode Electron, les projets sont ecrits dans le dossier Documents de l'utilisateur :

```text
Documents/BdGEN/
```

Les donnees de configuration de l'application Electron utilisent le dossier utilisateur de l'application gere par Electron.

## Pipeline de generation

BdGEN suit quatre etapes principales :

| Etape | Role | Sortie |
| --- | --- | --- |
| Script | Developpe la description du projet en script detaille | `bdgen-script.json` |
| References | Genere les planches modele des personnages, decors et objets | `references/` |
| Planches | Compose les pages finales, la couverture et la quatrieme de couverture | `pages/`, PDF final |
| Upscale | Optionnel, agrandit les images finales | `pages_upscaled/` |

## Commandes utiles

Depuis la racine du depot :

```bash
make frontend     # build React vers les assets FastAPI
make backend      # build du serveur local PyInstaller
make portable     # build complet de l'exe portable
make dev-desktop  # lance Electron en mode developpement
make lint         # lance les linters backend, frontend et desktop
make format       # formate backend, frontend et desktop
make format-check # verifie le format backend, frontend et desktop
make test         # tests Python
make clean        # nettoie les sorties de build
```

Depuis `bdgen/`, les commandes CLI restent disponibles :

```bash
uv run main.py wizard mon-projet.json
uv run main.py run mon-projet.json
uv run main.py script mon-projet.json
uv run main.py references ./output/mon-projet/bdgen-script.json
uv run main.py compose ./output/mon-projet/bdgen-script.json
uv run main.py upscale ./output/mon-projet/bdgen-script.json
```

Commandes qualite par partie :

```bash
# Backend Python
cd bdgen
uv run ruff check .
uv run ruff format .

# Frontend React
cd bdgen/web
npm run lint
npm run format
npm run format:check

# Desktop Electron
cd bdgen/desktop
npm run lint
npm run format
npm run format:check
```

## Structure d'un projet genere

```text
output/mon-projet/
  bdgen.json
  bdgen-script.json
  bdgen-feedback.json
  bdgen-stats.json
  references/
  pages/
  pages_upscaled/
  mon-projet.pdf
```
