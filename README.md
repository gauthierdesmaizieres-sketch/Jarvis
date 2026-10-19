# Jarvis

Une interface unique pour tout ce qui est installé dans Claude Code : projets, sessions, skills, serveurs MCP, plugins et config.

## v1 : dashboard local en lecture seule

```bash
python server.py
```

Puis ouvrir http://127.0.0.1:7777. Aucune dépendance (Python 3.10+ standard).

Ce qui est lu (jamais écrit) :

| Source | Contenu |
| --- | --- |
| `~/.claude.json` | projets connus, serveurs MCP utilisateur et locaux, stats d'usage des skills |
| `~/.claude/settings.json` | plugins activés |
| `~/.claude/skills/`, `agents/`, `commands/` | skills, agents et commandes utilisateur |
| `~/.claude/plugins/` | plugins installés et ce qu'ils apportent, marketplaces |
| `~/.claude/projects/` | sessions par projet (date, taille, premier prompt) |
| `<projet>/.mcp.json`, `<projet>/.claude/` | MCP, skills, agents et commandes du projet |
| `%APPDATA%/Claude/claude_desktop_config.json` | serveurs MCP de l'app desktop |

### Version en ligne (téléphone, PC éteint)

Une copie autonome du dashboard est publiée en Artifact privé sur claude.ai :
https://claude.ai/artifact/Px4f79WX52RJz9cjXR53F6

Elle s'ouvre depuis le téléphone (navigateur ou app Claude, connecté à ton compte), même quand le PC est éteint. Elle montre l'état du dernier envoi, pas l'état en direct, et masque les liens locaux (« PC »), qui ne marchent pas hors du PC.

Pour la mettre à jour :

```bash
python snapshot.py
```

Puis demander à Claude de republier `dist/jarvis.html` sur cette URL (« mets à jour Jarvis en ligne »).

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

- v2 : actions (ouvrir un projet dans l'éditeur, lancer `claude` dans un projet, reprendre une session, activer/désactiver un MCP)
- v3 : chat intégré via le Claude Agent SDK, avec tous les skills et MCP disponibles
- v4 : voix (wake word, STT/TTS)
