"""Point d'entrée de l'API Gordon.

Lancement :
    cd backend
    source .venv/bin/activate
    uvicorn app.main:app --reload --port 8787
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db
from .agents import registry
from .config import settings
from .routes import auth, chat, folders


def locate_cli() -> Path | None:
    """Retrouve le binaire `claude` utilisé par le SDK.

    Le paquet claude-agent-sdk embarque son propre CLI : il n'y a rien à
    installer séparément. On vérifie quand même sa présence pour pouvoir
    diagnostiquer, et on respecte une surcharge explicite.
    """
    if settings.cli_path:
        path = Path(settings.cli_path)
        return path if path.exists() else None

    try:
        import claude_agent_sdk

        bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
        if bundled.exists():
            return bundled
    except ImportError:
        pass

    from shutil import which

    found = which("claude")
    return Path(found) if found else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    registry.seed_if_empty()
    registry.backfill_workspaces()

    if locate_cli() is None:
        print(
            "\n  ⚠  Binaire `claude` introuvable.\n"
            "     Vérifie GORDON_CLI_PATH, ou réinstalle les dépendances.\n"
        )
    else:
        # Le CLI porte l'authentification. S'il n'a pas de session valide,
        # les agents échouent au premier message avec un message explicite.
        print("  Moteur : CLI claude détecté (authentification via abonnement).")

    print(f"  Gordon prêt — origine front autorisée : {settings.frontend_origin}")
    if db.credential_count() == 0:
        print("  Aucune passkey enregistrée : l'inscription est ouverte.\n")

    yield


app = FastAPI(title="Gordon", version="0.1.0", lifespan=lifespan)

# Le front est servi sur une origine distincte en développement.
# `allow_credentials` est indispensable : la session passe par un cookie.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(folders.router)


@app.get("/api/health")
def health() -> dict:
    cli = locate_cli()
    return {"ok": True, "cli_available": cli is not None, "cli_path": str(cli) if cli else None}
