# Gordon

Console d'agents IA spécialisés, auto-hébergée. Chaque agent a son métier, son
prompt et son jeu d'outils restreint. Accès verrouillé par passkey.

Moteur : **Claude Agent SDK** — le SDK s'appuie sur le CLI `claude`, qui porte
l'authentification de ton abonnement Claude. **Aucune clé API, aucun coût à
l'appel.**

---

## L'équipe

| № | Agent | Spécialité | Outils |
|---|-------|-----------|--------|
| 01 | **Gordon** | Coordination — oriente vers le bon spécialiste | recherche web |
| 02 | **Atlas** | Finance — budget, épargne, projections | lecture seule |
| 03 | **Mentor** | Révisions — fiches, quiz, plannings | fichiers |
| 04 | **Vigie** | Veille — recherche et synthèse de sources | recherche web + lecture |
| 05 | **Forge** | Développement — code, debug, architecture | fichiers + shell |

---

## Prérequis

- **Python 3.11+** et **Node 18+**
- Un **abonnement Claude** (Pro ou Max)
- Un appareil gérant les passkeys (Touch ID, Windows Hello, clé de sécurité,
  ou ton téléphone)

Le binaire `claude` est **fourni avec le paquet `claude-agent-sdk`** — il n'y a
rien à installer séparément.

---

## Installation

```bash
git clone <ton-repo> gordon && cd gordon

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Frontend
cd ../frontend
npm install
```

### Authentifier le moteur

Le CLI doit avoir une session valide, sinon les agents échouent au premier
message avec un message explicite dans l'interface.

```bash
cd backend
./.venv/lib/python*/site-packages/claude_agent_sdk/_bundled/claude auth login
```

Si tu as déjà le CLI Claude Code installé par ailleurs, un simple
`claude auth login` suffit — la session est partagée.

---

## Lancement

Deux terminaux.

```bash
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8787
```

```bash
cd frontend && npm run dev
```

Puis ouvre **http://localhost:5173**.

> Passe toujours par le port 5173, pas par 8787. Le front proxifie l'API, ce
> qui rend le cookie de session first-party et aligne l'origine WebAuthn.

### Première connexion

Au premier démarrage aucune passkey n'existe : l'écran propose **« Créer ma
passkey »**. Dès qu'elle est enregistrée, l'inscription se **ferme
automatiquement** — personne d'autre ne peut s'enrôler.

Pour ajouter un second appareil, utilise **« + Ajouter une passkey »** depuis
la console, en étant déjà connecté. Ce chemin ne rouvre rien publiquement.

---

## Ajouter un agent

Tout est dans [`backend/app/agents/registry.py`](backend/app/agents/registry.py).
Ajoute une entrée `AgentSpec` au dictionnaire `AGENTS` : le front le découvre
tout seul via `GET /api/agents`, il n'y a rien à toucher côté interface.

```python
"juridique": AgentSpec(
    id="juridique",
    name="Themis",
    callsign="06",
    role="Juridique",
    tagline="Contrats, CGU, conformité.",
    accent="#60a5fa",
    tools=RESEARCH,
    effort="high",
    system_prompt="...",
),
```

Les outils disponibles : `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`,
`WebSearch`, `WebFetch`. **Ne donne que le strict nécessaire** — la liste est
appliquée côté serveur, un agent ne peut pas en sortir.

---

## Architecture

```
backend/
  app/
    main.py              FastAPI, CORS, détection du CLI
    config.py            configuration par variables d'environnement
    db.py                SQLite — passkeys, sessions d'agents
    agents/
      registry.py        ← définition des agents
      runner.py          pont vers le Claude Agent SDK, streaming SSE
    auth/
      passkey.py         WebAuthn (enregistrement, vérification)
      session.py         cookie signé + protection des routes
    routes/              auth.py, chat.py
frontend/
  src/
    api.ts               client HTTP + découpage du flux SSE
    components/          LoginGate, AgentGrid, ChatView, DevicePanel
```

Quelques choix à connaître :

- **Les conversations survivent au redémarrage.** Plutôt que de garder un
  sous-processus vivant par agent, on stocke l'identifiant de session renvoyé
  par le SDK et on reprend le fil avec `resume=`.
- **Les agents sont isolés de ta machine.** `setting_sources=[]` empêche le SDK
  de charger tes `CLAUDE.md`, réglages et skills locaux : un agent de Gordon
  n'hérite pas de ton contexte de développement.
- **Double barrière sur les outils.** La liste de la fiche d'agent est passée
  au SDK *et* revérifiée à chaque appel côté serveur, avec un refus franc
  plutôt qu'une attente de validation humaine qui n'arriverait jamais.

---

## Étape 2 — mise en ligne sur gordon.aguetai.fr

Trois choses à régler, par ordre de difficulté.

### 1. Configuration (facile)

```bash
GORDON_FRONTEND_ORIGIN=https://gordon.aguetai.fr
GORDON_RP_ID=gordon.aguetai.fr
GORDON_RP_ORIGIN=https://gordon.aguetai.fr
GORDON_SECRET_KEY=<valeur générée, gardée secrète>
```

HTTPS est **obligatoire** : WebAuthn ne fonctionne hors TLS que sur
`localhost`. Le cookie passe en `secure` automatiquement dès que
`GORDON_RP_ORIGIN` est en `https://`.

Construis le front (`npm run build`) et sers `frontend/dist` derrière un
reverse proxy qui renvoie `/api` vers uvicorn. Pense à désactiver la mise en
tampon du proxy sur `/api`, sinon le streaming arrive d'un bloc (l'en-tête
`X-Accel-Buffering: no` est déjà envoyé pour nginx).

> `GORDON_RP_ID` ne peut pas changer après coup sans invalider les passkeys
> existantes : elles sont liées au domaine. Enregistre tes passkeys de
> production une fois le domaine définitif en place.

### 2. Authentification du moteur sur un serveur (moyen)

`claude auth login` ouvre un navigateur — inutilisable sur un serveur. Le CLI
prévoit le cas :

```bash
claude setup-token          # génère un jeton longue durée
export CLAUDE_CODE_OAUTH_TOKEN=<le jeton>
```

C'est le mécanisme prévu pour les tâches non interactives.

### 3. Le point à trancher (important)

Faire tourner Gordon en ligne **avec ton abonnement** le fait sortir de son
cadre d'usage : un abonnement couvre ton usage personnel, pas un service
accessible à d'autres.

Tant que tu es le seul utilisateur derrière ta passkey, tu restes dans un
usage personnel — simplement depuis une autre machine. Si tu ouvres l'accès à
d'autres personnes, c'est un service, et il faut une autre source de modèle.

C'est précisément pour ça que `runner.py` est isolé : tout l'appel au moteur
est concentré dans `stream_turn()`. Basculer sur l'API Anthropic facturée, ou
sur un tiers gratuit (Gemini, Groq, Mistral), ne touche que ce fichier — ni
les agents, ni l'auth, ni l'interface.

---

## Dépannage

| Symptôme | Cause |
|---|---|
| `Failed to authenticate` dans le chat | Le CLI n'a pas de session valide → `claude auth login` |
| L'écran de connexion boucle | Le backend ne tourne pas, ou tu es sur :8787 au lieu de :5173 |
| `NotAllowedError` à la création de passkey | Fenêtre système annulée, ou page servie hors `localhost`/HTTPS |
| Réponse qui arrive d'un bloc | Mise en tampon du proxy sur `/api` |
| Session perdue à chaque redémarrage | `GORDON_SECRET_KEY` absent du `.env` |

---

## Licence et mentions

Projet personnel. L'identité visuelle est une création originale d'inspiration
retro-futuriste ; aucun asset, logo ou marque de tiers n'est repris.
