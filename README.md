# BdGEN

BdGEN est une application de generation de bandes dessinees a partir d'une description de projet. Elle combine un backend Python/FastAPI, une interface React et une application Electron desktop.

Le projet peut etre utilise de deux facons principales :

- **Mode web** : le serveur local est lance manuellement, puis l'interface est ouverte dans un navigateur.
- **Mode desktop package** : un paquet Electron autonome lance l'application et son serveur local embarque.

## Prerequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js et npm
- L'OS cible pour construire un paquet desktop natif : Windows pour `.exe`, macOS pour `.dmg`, Linux pour les futurs artefacts Linux

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
XAI_API_KEY=xai-...
REPLICATE_API_TOKEN=...
```

L'application web permet aussi de configurer les cles via son coffre local chiffre au lancement.

Pour la creation du scenario, les fournisseurs OpenAI, Anthropic et xAI sont
disponibles. Pour les images, seul OpenAI est disponible. Le formulaire propose
une liste de modeles recents et conserve un champ de saisie libre pour entrer
manuellement un autre nom de modele.

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

## Mode Desktop Package

Le mode desktop package est le mode utilisateur final. Il produit un paquet Electron autonome adapte a la plateforme cible.

Dans ce mode :

- Electron affiche la fenetre de l'application.
- Le serveur FastAPI est lance automatiquement en arriere-plan.
- Le backend PyInstaller est embarque dans les ressources de l'application.
- Il n'est pas necessaire d'ouvrir un navigateur ni de lancer `uv run python -m bdgen.server`.

### Construire les paquets desktop

Depuis la racine du depot :

```bash
make portable  # Windows: build/portable/*.exe
make macos     # macOS: build/mac/*.dmg non signe
make linux     # Linux: build/linux/*, cible preparee pour la suite
```

Ces commandes enchainent :

1. `uv sync`
2. build du frontend React
3. build du serveur local avec PyInstaller
4. build de l'application Electron pour la plateforme cible

Les resultats attendus sont :

```text
build/portable/BdGEN 0.1.0.exe
build/mac/BdGEN 0.1.0.dmg
build/linux/BdGEN 0.1.0.AppImage
```

`make build` et `make desktop` restent des alias Windows et produisent l'executable portable. Le `.dmg` macOS actuel est volontairement non signe/non notarise pour la premiere etape ; Gatekeeper peut donc afficher un avertissement au premier lancement.

### Lancer le paquet desktop

Double-cliquez sur :

```text
build/portable/BdGEN 0.1.0.exe
build/mac/BdGEN 0.1.0.dmg
```

Au lancement, l'application affiche sa fenetre Electron personnalisee. Si le coffre de secrets n'est pas encore configure ou deverrouille, la page de verrouillage apparait avant l'acces au reste de l'application.

### Donnees en mode desktop

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
make portable     # build complet de l'exe portable Windows
make macos        # build du DMG macOS non signe
make linux        # build Linux prepare pour AppImage
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

## CI/CD et versions

Le workflow GitHub Actions `.github/workflows/release-portable.yml` se lance a
chaque push sur `main`.

Il execute d'abord les controles qualite :

- lint backend, frontend et desktop ;
- `npm audit --audit-level=critical` sur le frontend ;
- `npm audit --audit-level=critical` sur l'application desktop.

Si ces controles passent, le workflow calcule automatiquement la prochaine
version SemVer, cree le tag Git `vX.Y.Z`, puis lance une matrice de builds
desktop. La matrice construit l'executable Windows portable sur runner Windows
et le DMG macOS non signe sur runner macOS. Une fois les artefacts generes, le
workflow cree ou met a jour la release GitHub avec les assets disponibles. La
structure du packaging garde une cible Linux preparee, mais la publication
Linux sera ajoutee apres validation du format de distribution.

Le numero de version est deduit des messages de commit depuis le dernier tag
`vX.Y.Z` :

| Type de version | Message de commit | Exemple |
| --- | --- | --- |
| Majeure | `BREAKING CHANGE:` dans le corps du commit, ou `!` apres le type | `feat!: changer le format des projets` |
| Mineure | type `feat` | `feat: ajouter un fournisseur image` |
| Patch | tout autre message | `fix: corriger la fermeture desktop` |

Par defaut, si aucun commit ne demande une version majeure ou mineure, la
version suivante est un patch.

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
