"""Configuration centrale de Gordon.

Tout est surchargeable par variables d'environnement ou par un fichier .env
placé dans backend/. Voir .env.example.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_prefix="GORDON_",
        extra="ignore",
    )

    # --- Serveur ---
    host: str = "127.0.0.1"
    port: int = 8787

    # Origine du front, autorisée en CORS. En prod : https://gordon.aguetai.fr
    frontend_origin: str = "http://localhost:5173"

    # --- Sessions ---
    # Généré à la volée si absent : les sessions sont alors invalidées à chaque
    # redémarrage. Fixe GORDON_SECRET_KEY en prod pour les faire persister.
    secret_key: str = secrets.token_urlsafe(32)
    session_cookie: str = "gordon_session"
    session_max_age: int = 60 * 60 * 24 * 14  # 14 jours

    # --- WebAuthn / passkey ---
    # rp_id doit être le domaine exact, sans schéma ni port.
    # localhost en dev, aguetai.fr en prod.
    rp_id: str = "localhost"
    rp_name: str = "Gordon"
    # Origine complète attendue dans l'assertion WebAuthn.
    rp_origin: str = "http://localhost:5173"

    # Une fois la première passkey enregistrée, l'inscription se ferme
    # automatiquement. Mets ceci à True pour la réouvrir temporairement.
    allow_registration: bool = False

    # --- Moteur IA ---
    # Laisse vide pour utiliser le défaut du CLI. "opus", "sonnet", "haiku"
    # ou un identifiant complet.
    model: str = "opus"

    # Répertoire proposé par défaut aux agents qui manipulent des fichiers.
    workspace_dir: Path = DATA_DIR / "workspace"

    # Racine au-delà de laquelle un agent ne peut pas se voir attribuer de
    # dossier, et que l'explorateur de la console refuse de quitter. Le
    # dossier personnel par défaut : assez large pour être utile, assez
    # étroit pour qu'un agent ne parte pas dans /etc ou /System.
    fs_root: Path = Path.home()

    # Chemin du binaire `claude` si absent du PATH.
    cli_path: str | None = None

    # Jeton longue durée pour un serveur sans navigateur (`claude setup-token`).
    # Laisse vide en local : le CLI utilise alors la session de `claude auth
    # login`, stockée dans le trousseau macOS.
    oauth_token: str | None = None

    # --- Outils Apple ---
    # Agenda, Rappels et Mail passent par les applications du Mac : ils
    # n'existent que sur macOS, et seulement sur la machine où vivent ces
    # données. GORDON_APPLE_TOOLS=false pour les retirer du catalogue.
    apple_tools: bool = sys.platform == "darwin"

    @property
    def db_path(self) -> Path:
        return DATA_DIR / "gordon.db"


settings = Settings()

DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.workspace_dir.mkdir(parents=True, exist_ok=True)


def _scrub_engine_env() -> None:
    """Purge l'environnement hérité avant tout lancement du moteur.

    Si Gordon est démarré depuis un terminal déjà « habité » (une session
    Claude Code, un IDE), le CLI hérite de variables ANTHROPIC_*/CLAUDE_* qui
    détournent son authentification vers la session parente — des jetons à
    durée de vie courte, que le CLI peut même persister dans le trousseau en
    écrasant la vraie connexion de l'utilisateur. C'est arrivé ici. On repart
    donc toujours d'un environnement neutre : l'authentification vient du
    trousseau (`claude auth login`), ou du jeton GORDON_OAUTH_TOKEN ci-dessous.
    """
    for name in list(os.environ):
        if name.startswith(("CLAUDE", "ANTHROPIC")):
            del os.environ[name]

    if settings.oauth_token:
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = settings.oauth_token


_scrub_engine_env()
