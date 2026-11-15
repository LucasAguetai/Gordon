# Gordon

Console d'agents IA spécialisés, auto-hébergée. Chaque agent a son métier, son
prompt, son jeu d'outils restreint et **sa mémoire** : la conversation reprend
où elle s'était arrêtée, visite après visite. Accès verrouillé par passkey.

Moteur : **Claude Agent SDK** — le SDK s'appuie sur le CLI `claude`, qui porte
l'authentification de ton abonnement Claude. **Aucune clé API, aucun coût à
l'appel.**

Sur macOS, les agents peuvent aussi recevoir des outils **Agenda, Rappels et
Mail**, branchés sur les applications du Mac — en local, rien ne sort de la
machine.

---

## Les spécialités

Gordon est la console ; chaque carte est une spécialité. Elles se créent et
se suppriment depuis l'interface — les quatre ci-dessous sont les valeurs
d'amorçage du premier démarrage, pas des agents privilégiés.

| № | Agent | Spécialité | Outils |
|---|-------|-----------|--------|
| 01 | **Atlas** | Finance — budget, épargne, projections | lecture seule |
| 02 | **Mentor** | Révisions — fiches, quiz, plannings | fichiers |
| 03 | **Vigie** | Veille — recherche et synthèse de sources | recherche web + lecture |
| 04 | **Forge** | Développement — code, debug, architecture | fichiers + shell |

Chaque agent a un portrait décliné en deux états. Écran verrouillé, l'équipe
est en civil ; au déverrouillage les portraits défilent vers leur tenue de
service — une combinaison bleue commune, barrée d'un baudrier à la couleur de
la spécialité, de l'épaule gauche vers la hanche droite.

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

Deux chemins, au choix.

**Depuis la console (recommandé)** : panneau **Moteur** en bas de l'accueil
→ **Connecter** → ouvre le lien d'autorisation, approuve, colle le code.
Gordon pilote le flux `setup-token` du CLI et conserve un **jeton valable un
an**, qui survit aux redémarrages. Tout se fait dans le navigateur — depuis
un téléphone aussi, ce qui compte le jour où la session saute alors que tu
n'as pas de shell sous la main. Le même bouton réapparaît directement sous
l'erreur dans le chat.

**Au shell** :

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

## Les conversations

Chaque agent garde **un fil continu**, et c'est le cœur du projet : plus tu
lui parles, plus il connaît ton contexte.

- **La transcription est persistée** : rouvre un agent, l'historique
  s'affiche. La mémoire du modèle, elle, voyage via l'identifiant de session
  du SDK — les deux survivent à un redémarrage du serveur.
- **Un tour survit à la fermeture de la page.** La réponse se calcule côté
  serveur : verrouille ton téléphone, ferme l'onglet — en revenant,
  l'interface voit qu'un tour est en cours, patiente, puis affiche la
  réponse enregistrée. Un agent ne traite qu'un message à la fois.
- **« Nouveau fil »** efface tout — transcription et mémoire — après
  confirmation.
- Les réponses sont rendues en **markdown** : tableaux, listes, code.

## Créer, modifier et supprimer des agents

Depuis la console : **« Nouvel agent »** ouvre un formulaire (nom,
spécialité, couleur, outils, dossier de travail, profondeur de réflexion,
prompt système), avec un aperçu du visage et un bouton pour en tirer un
autre. Au survol d'une carte : **✎** modifie, **✕** supprime (après
confirmation).

Le prompt système s'amorce depuis le nom et la spécialité — il ne reste
qu'à décrire la méthode. Dès que tu y touches, il cesse de se réécrire.

Modifier un agent **ne touche pas à sa mémoire** : l'identifiant interne ne
change jamais, même si tu renommes l'agent — la conversation continue avec
la fiche à jour. Supprimer un agent, en revanche, **efface aussi son fil**.
C'est volontaire : sans ça, recréer un agent sous le même nom reprendrait
la conversation du précédent.

### Les outils

Trois familles, et la différence compte.

| Famille | Outils | Portée |
|---|---|---|
| **Fichiers** | `Read`, `Glob`, `Grep`, `Write`, `Edit`, `Bash` | Un dossier, choisi à la création |
| **Web** | `WebSearch`, `WebFetch` | Internet |
| **Apple** (macOS) | `Agenda`, `AgendaAjout`, `Rappels`, `RappelAjout`, `Mail`, `MailBrouillon` | Les applications du Mac qui héberge Gordon |

Dès qu'un outil fichier est coché, le formulaire réclame un **dossier de
travail** et l'agent ne verra que celui-ci. Le sélecteur est servi par le
backend : un sélecteur de fichiers natif ne donne jamais le vrai chemin
disque au navigateur.

`Glob` et `Grep` se confondent facilement : `Glob` cherche des fichiers
**par leur nom** (`*.pdf`, `**/releve-*.csv`), `Grep` cherche une expression
**à l'intérieur** des fichiers.

**Ne donne que le strict nécessaire** : la liste est une liste blanche
appliquée côté serveur, un agent ne peut pas en sortir, et tout outil
inconnu est refusé à la création. `Bash` est le plus puissant et le plus
risqué — il exécute des commandes dans le dossier.

> Un agent ne peut recevoir qu'un dossier situé dans ton dossier personnel.
> Le chemin est résolu **avant** d'être comparé à cette racine, pour qu'un
> `..` ou un lien symbolique ne permette pas d'en sortir. Pour élargir ou
> resserrer, c'est `fs_root` dans
> [`config.py`](backend/app/config.py).

### Les outils Apple

Implémentés dans [`apple.py`](backend/app/agents/apple.py) et servis au
moteur par un petit serveur MCP embarqué dans le backend. Agenda et Rappels
passent par **EventKit** (pyobjc), Mail par un script **JXA** via
`osascript` — tout est local, aucun service tiers.

Lecture et écriture sont des cases **séparées** : tu peux donner l'agenda en
lecture seule. Et chaque écriture est étroite par construction :

- `AgendaAjout` / `RappelAjout` **créent** ; impossible de modifier ou de
  supprimer quoi que ce soit d'existant.
- `MailBrouillon` prépare un brouillon **ouvert dans Mail** — l'agent ne
  peut rien envoyer, l'envoi reste un geste humain.

**Aucun lien avec le compte iCloud** : Gordon ne connaît ni identifiant ni
mot de passe Apple et ne parle jamais aux serveurs d'Apple. Il lit les
applications du Mac, qui se synchronisent elles-mêmes avec iCloud. Chaque
accès est une autorisation macOS classique, visible et révocable dans les
Réglages Système.

La page **Apple** de la console (panneau Apple de l'accueil → Gérer) montre
l'état de chaque autorisation, permet de déclencher les demandes — la
fenêtre s'affiche **sur le Mac qui héberge Gordon** — et ouvre les Réglages
Système au bon panneau. Elle liste aussi les calendriers visibles et les
agents qui utilisent ces outils. Si un agent tente un accès jamais accordé,
il reçoit un message qui explique quoi autoriser et où.

C'est aussi ce qui ancre l'étape 2 : ces données vivent sur ton Mac, donc
**c'est ton Mac qui doit héberger Gordon** pour que ces outils existent.
`GORDON_APPLE_TOOLS=false` les retire du catalogue.

Les agents vivent en base
([`backend/app/db.py`](backend/app/db.py)) ; les valeurs d'amorçage du
premier démarrage sont dans
[`registry.py`](backend/app/agents/registry.py) sous `SEEDS`.

### Les portraits

Les visages sont des avatars **avataaars** construits dans le navigateur par
[`frontend/src/avatar.ts`](frontend/src/avatar.ts), à partir d'une
description (`look`) stockée avec l'agent : coiffure, couleurs, regard,
bouche, lunettes. La tenue de service est ajoutée par-dessus — combinaison
bleue commune et baudrier à la couleur de l'agent.

Les listes de variantes y sont volontairement restreintes : l'inventaire
complet contient des expressions (pleurs, nausée, yeux en cœur) qui n'ont
pas leur place sur une fiche d'agent.

> Ces avatars étaient pré-générés au build tant que la liste était figée.
> Depuis qu'on peut créer des agents, le style est embarqué et rendu à
> l'exécution : un agent inventé doit obtenir un visage immédiatement.

---

## Architecture

```
backend/
  app/
    main.py              FastAPI, CORS, détection du CLI
    config.py            configuration par variables d'environnement
    db.py                SQLite — passkeys, agents, sessions, transcriptions
    agents/
      registry.py        CRUD des agents + valeurs d'amorçage
      runner.py          pont vers le Claude Agent SDK, tours en tâche de
                         fond, streaming SSE, transcription
      apple.py           outils Agenda / Rappels / Mail (serveur MCP embarqué)
    auth/
      passkey.py         WebAuthn (enregistrement, vérification)
      session.py         cookie signé + protection des routes
    routes/              auth.py, chat.py, folders.py
frontend/
  src/
    api.ts               client HTTP + découpage du flux SSE
    avatar.ts            construction des portraits et du baudrier
    components/          LoginGate, AgentGrid, AgentForm, ChatView,
                         PortraitReel, FolderPicker, DevicePanel
```

Quelques choix à connaître :

- **Les conversations survivent au redémarrage.** Plutôt que de garder un
  sous-processus vivant par agent, on stocke l'identifiant de session renvoyé
  par le SDK et on reprend le fil avec `resume=`. La transcription, elle, vit
  dans SQLite — c'est elle que l'interface affiche.
- **Un tour ne dépend pas de la connexion du navigateur.** Le tour s'exécute
  dans une tâche asyncio ; la réponse HTTP ne fait que relayer une file
  d'évènements. Client parti, le tour finit quand même et s'enregistre.
- **Les agents sont isolés de ta machine.** `setting_sources=[]` empêche le SDK
  de charger tes `CLAUDE.md`, réglages et skills locaux : un agent de Gordon
  n'hérite pas de ton contexte de développement.
- **Double barrière sur les outils.** La liste de la fiche d'agent est passée
  au SDK *et* revérifiée à chaque appel côté serveur — outils Apple compris,
  sous leur nom complet `mcp__apple__…` — avec un refus franc plutôt qu'une
  attente de validation humaine qui n'arriverait jamais.

---

## Étape 2 — mise en ligne sur gordon.aguetai.fr

D'abord une décision devenue simple : **c'est ton Mac qui héberge.** Les
outils Apple lisent l'agenda, les rappels et le courrier *de la machine qui
fait tourner Gordon* — sur un VPS, ils n'auraient rien à lire. Le chemin
naturel est donc un tunnel depuis le Mac (Cloudflare Tunnel, par exemple) :
pas de port ouvert sur ta box, TLS géré, et `gordon.aguetai.fr` pointe vers
la maison. Garde le Mac branché et interdis sa mise en veille
(`caffeinate` ou Réglages → Économie d'énergie).

Ensuite, trois choses à régler, par ordre de difficulté.

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

### 2. Authentification du moteur sur un serveur (déjà réglé)

C'est précisément ce que fait le panneau **Moteur** de la console : le flux
d'autorisation se déroule dans **ton** navigateur, le serveur n'en a pas
besoin, et le jeton d'un an est conservé en base. Déconnecté ? Reconnecte-toi
depuis n'importe où, téléphone compris.

Alternative d'administration : `claude setup-token` au shell, puis le jeton
dans `backend/.env` sous `GORDON_OAUTH_TOKEN=…` — cette valeur prime alors
sur celle de la console.

> Au démarrage, Gordon **purge les variables `CLAUDE*`/`ANTHROPIC*` héritées**
> du terminal avant de lancer le moteur. Sans ça, démarrer le backend depuis
> un environnement déjà habité (une session Claude Code, un IDE) détournait
> l'authentification vers des jetons de session éphémères — qui pouvaient
> même écraser la vraie connexion dans le trousseau. L'authentification de
> Gordon vient donc toujours du trousseau (`claude auth login`) ou de
> `GORDON_OAUTH_TOKEN`, jamais de l'environnement ambiant.

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
| « Le moteur n'est pas connecté » dans le chat | Bouton **Connecter le moteur** (sous l'erreur, ou panneau Moteur de l'accueil) |
| « travaille déjà sur un message » | Un tour est en cours pour cet agent — un seul à la fois |
| « macOS refuse l'accès aux Calendriers/Rappels » | Autorisation à donner sur le Mac : Réglages Système → Confidentialité et sécurité |
| « macOS a bloqué le contrôle de Mail » | Même endroit, section Automatisation → autoriser Mail pour le terminal |
| L'écran de connexion boucle | Le backend ne tourne pas, ou tu es sur :8787 au lieu de :5173 |
| `NotAllowedError` à la création de passkey | Fenêtre système annulée, ou page servie hors `localhost`/HTTPS |
| Réponse qui arrive d'un bloc | Mise en tampon du proxy sur `/api` |
| Session perdue à chaque redémarrage | `GORDON_SECRET_KEY` absent du `.env` |

---

## Licence et mentions

Projet personnel. L'habillage de l'interface est une création originale
d'inspiration retro-futuriste ; aucun asset, logo ou marque de tiers n'est
repris.

Les portraits sont des remix d'[Avataaars](https://avataaars.com/) par Pablo
Stanley, libres d'usage personnel et commercial, générés avec
[DiceBear](https://www.dicebear.com/). La combinaison et le baudrier sont
ajoutés par-dessus.

> Si tu changes de style d'avatar, vérifie sa licence : plusieurs styles
> DiceBear (micah, personas, adventurer, big-smile…) sont en **CC BY 4.0** et
> imposent alors une attribution visible sur le site.
