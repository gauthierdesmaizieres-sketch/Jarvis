# Jarvis

Une interface unique pour tout ce qui est installé dans Claude Code : projets, sessions, skills, serveurs MCP, plugins et config.

## Dashboard local (v1 inventaire, v2 actions, v3 cerveau)

```bash
python server.py
```

Puis ouvrir http://127.0.0.1:7777. Aucune dépendance (Python 3.10+ standard).

Ce qui est lu :

| Source | Contenu |
| --- | --- |
| `~/.claude.json` | projets connus, serveurs MCP utilisateur et locaux, stats d'usage des skills |
| `~/.claude/settings.json` | plugins activés |
| `~/.claude/skills/`, `agents/`, `commands/` | skills, agents et commandes utilisateur |
| `~/.claude/plugins/` | plugins installés et ce qu'ils apportent, marketplaces |
| `~/.claude/projects/` | sessions par projet (date, taille, premier prompt) |
| `<projet>/.mcp.json`, `<projet>/.claude/` | MCP, skills, agents et commandes du projet |
| `%APPDATA%/Claude/claude_desktop_config.json` | serveurs MCP de l'app desktop |

### Actions (v2, sur le PC uniquement)

Sur chaque carte projet du dashboard local :

- **Dossier** / **Éditeur** : ouvre le projet dans l'explorateur Windows ou dans VS Code ;
- **Claude ▶** : lance une nouvelle session Claude Code dans un terminal ;
- **Reprendre** (sur une session listée) : `claude --resume <id>` dans un terminal ;
- **Git statut** / **Git pull** (`--ff-only`, avec confirmation) : le résultat s'affiche en bas à droite ;
- **MCP … · on/off** : active ou désactive un serveur MCP pour ce projet (comme `/mcp` dans Claude Code).

Dans l'onglet Plugins, **Activer / Désactiver** change `enabledPlugins` dans `~/.claude/settings.json`.

Les seules écritures de Jarvis sont ces deux interrupteurs. Chacun demande une confirmation dans la page, garde une copie `*.jarvis.bak` du fichier d'avant, et prend effet à la prochaine session Claude Code. Le MCP coupé est noté dans `~/.claude.json`, dans le projet : `disabledMcpjsonServers` pour un serveur du `.mcp.json`, `disabledMcpServers` pour les autres.

Sécurité des actions : `POST /api/action` n'accepte que les requêtes dont `Host` et `Origin` sont `127.0.0.1`/`localhost` sur le port de Jarvis et qui portent le jeton aléatoire que le serveur met dans la page à chaque démarrage. Une action ne vise qu'un projet déjà connu de Claude Code, jamais un chemin libre. Les copies hors ligne (Artifact, GitHub Pages) n'ont pas de jeton : aucun bouton d'action n'y apparaît.

### Cerveau (v3, sur le PC uniquement)

Quatre onglets en plus, chargés seulement quand on les ouvre :

- **Chat** : choisis un projet et écris. Jarvis lance `claude -p` dans le dossier du projet et affiche la réponse en direct ; les messages suivants continuent la même conversation (`--resume`). **Nouvelle conversation** repart de zéro, **Stop** coupe la réponse, **Ouvrir dans un terminal** reprend la session dans Claude Code. Aucun mode qui contourne les permissions : ce qui demanderait ta confirmation (modifier un fichier, lancer une commande non autorisée) est refusé automatiquement (`--permission-prompts none`).
  Il faut que la commande `claude` soit connectée : si le chat répond « Not logged in », lance une fois `claude auth login` dans un terminal.
- **Usage** : tokens des 14 derniers jours, par jour (graphique), par projet et par modèle, lus dans `message.usage` des sessions de `~/.claude/projects/` (sous-agents compris). Seule la partie nouvelle des fichiers est relue, le reste est gardé en mémoire tant que le serveur tourne.
- **Recherche** : cherche un texte dans tes prompts et les réponses de Claude de toutes les sessions (50 résultats au plus), avec projet, date, extrait et bouton **Reprendre**.
- **Git** : pour chaque projet git, la branche, les fichiers modifiés, les commits à pousser et en retard sur la branche distante, et les branches locales. **Fetch + actualiser** fait d'abord un `git fetch`, **Tout pull** lance `git pull --ff-only` partout (avec confirmation) et affiche le résultat projet par projet.

Ces routes (`POST /api/chat`, `GET /api/usage`, `/api/search`, `/api/git`) ont la même protection que les actions (Host, Origin, jeton). Ces onglets n'existent ni dans l'Artifact ni sur la page publique.

Dans le chat, **Micro** dicte ton message et **Voix · on** lit les réponses à voix haute (reconnaissance et synthèse vocales du navigateur ; dans Chrome, la dictée passe par les serveurs de Google).

### Sur le téléphone

- **Jarvis en direct (PC allumé)** : installe [Tailscale](https://tailscale.com/download) sur le PC et sur le téléphone, connecte-les au même compte, puis lance une fois sur le PC :

  ```bash
  tailscale serve --bg 7777
  ```

  Au démarrage, `python server.py` affiche l'adresse à ouvrir sur le téléphone (`https://<pc>.<…>.ts.net`). Elle n'est accessible qu'à tes appareils (n'utilise pas `tailscale funnel`, qui la rendrait publique). Jarvis accepte cette adresse comme `127.0.0.1` ; le jeton reste obligatoire.
- **Installer l'app** : dans le navigateur du téléphone, « Ajouter à l'écran d'accueil ». Jarvis s'ouvre alors en plein écran.
- **Partager vers Jarvis** (Android, app installée) : dans le menu Partager d'une autre app, choisis Jarvis ; le texte ou le lien arrive dans le chat.
- **Widget** : `docs/stats.json` (public, seulement les compteurs) est publié avec la page, à l'adresse `https://gauthierdesmaizieres-sketch.github.io/Jarvis/stats.json`. Un widget (Raccourcis sur iPhone, KWGT sur Android) peut l'afficher.
- **PC éteint** : seules la page publique et l'Artifact marchent (lecture seule, état du dernier envoi). Le chat, git et la recherche ont besoin du PC. Pour coder sans le PC, utilise les sessions cloud de claude.ai/code.
- **Claude Code depuis l'app Claude du téléphone** : Remote Control est activé pour les nouvelles sessions.

`python tests/test_v3.py` vérifie le parseur de tokens, la recherche et la lecture du flux du chat.

### Version en ligne (téléphone, PC éteint)

Une copie autonome du dashboard est publiée en Artifact privé sur claude.ai :
https://claude.ai/artifact/Px4f79WX52RJz9cjXR53F6

Elle s'ouvre depuis le téléphone (navigateur ou app Claude, connecté à ton compte), même quand le PC est éteint. Elle montre l'état du dernier envoi, pas l'état en direct, et masque les liens locaux (« PC »), qui ne marchent pas hors du PC.

Pour la mettre à jour :

```bash
python snapshot.py
```

Puis demander à Claude de republier `dist/jarvis.html` sur cette URL (« mets à jour Jarvis en ligne »).

### Version publique automatique (GitHub Pages, 0 token)

`python publish.py` régénère `docs/index.html` avec `snapshot.py --public`, puis le commite et le pousse, seulement si quelque chose a changé : un projet, un lien, un skill, un MCP ou un commit. Un hook Claude Code le lance à la fin de chaque réponse de Claude, donc la page en ligne se met à jour toute seule, sans demande à Claude.

Cette version est publique et filtrée. Elle ne contient ni email, ni chemins, ni prompts de session, ni CLAUDE.md, ni détails des serveurs MCP, ni liens locaux.

### Liens des projets

Chaque carte projet affiche ses liens, détectés automatiquement :

- remote GitHub `origin` → GitHub, Changelog (commits), Actions s'il y a des workflows, Site web (GitHub Pages) s'il y a un `index.html` à la racine ou dans `docs/` ;
- `.claude/launch.json` → serveurs locaux (marqués « PC », inaccessibles depuis le téléphone) ;
- les dépôts git imbriqués d'un niveau (un dossier projet qui contient plusieurs apps) sont aussi lus.

Pour ajouter un lien à la main, l'écrire dans [links.json](links.json), avec comme clé le nom du dossier du projet :

```json
{ "Mon projet": [{ "label": "Démo", "url": "https://…" }] }
```

Sécurité : le serveur n'écoute que sur `127.0.0.1`. Les valeurs `env`, `headers` et les query strings des serveurs MCP ne sont jamais renvoyées, seulement leurs noms.

Limite connue : les connecteurs gérés par l'app Claude (Docs, Chrome, navigateur intégré…) ne sont pas dans ces fichiers et n'apparaissent pas.

`python -m jarvis.inventory` affiche l'inventaire brut en JSON.

## Pistes pour la suite

- v4 : bouton micro (dictée et réponse parlée avec la voix du navigateur), barre de commande Ctrl+K, état du PC (processeur, mémoire, disque) dans le HUD
