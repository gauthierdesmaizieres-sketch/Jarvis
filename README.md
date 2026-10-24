# Jarvis

Une interface unique pour tout ce qui est installé dans Claude Code : projets, sessions, skills, serveurs MCP, plugins et config.

## Dashboard local (v1 inventaire + v2 actions)

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

- v3 : chat intégré via le Claude Agent SDK, avec tous les skills et MCP disponibles
- v4 : voix (wake word, STT/TTS)
