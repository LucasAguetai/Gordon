"""Exploration de dossiers, pour choisir le répertoire de travail d'un agent.

Le navigateur ne peut pas donner un vrai chemin disque depuis un sélecteur
de fichiers : c'est donc au serveur de lister l'arborescence. On se limite
strictement à `settings.fs_root` (le dossier personnel), on ne renvoie que
des noms de dossiers, et jamais de contenu de fichier.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from ..agents.registry import AgentError, resolve_workspace
from ..auth.session import current_user
from ..config import settings

router = APIRouter(prefix="/api/folders", tags=["folders"])


def _safe(raw: str | None) -> Path:
    """Résout un chemin demandé, en refusant toute sortie de la racine."""
    root = settings.fs_root.resolve()
    if not raw:
        return root

    candidate = Path(raw).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Dossier introuvable : {raw}"
        ) from exc

    if resolved != root and root not in resolved.parents:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Hors de {root}."
        )
    if not resolved.is_dir():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pas un dossier.")
    return resolved


@router.get("")
def browse(path: str | None = None, user_id: str = Depends(current_user)) -> dict:
    here = _safe(path)
    root = settings.fs_root.resolve()

    folders = []
    try:
        for entry in sorted(here.iterdir(), key=lambda p: p.name.lower()):
            # Les dossiers cachés encombrent la liste sans servir ici.
            if entry.name.startswith("."):
                continue
            # is_dir() suit les liens ; un lien cassé lèverait une erreur.
            try:
                if entry.is_dir():
                    folders.append({"name": entry.name, "path": str(entry)})
            except OSError:
                continue
    except PermissionError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Dossier non lisible."
        ) from None

    return {
        "path": str(here),
        "parent": str(here.parent) if here != root else None,
        "root": str(root),
        "folders": folders,
    }


@router.post("/check")
def check(path: str, user_id: str = Depends(current_user)) -> dict:
    """Valide un chemin saisi à la main, avec le même contrôle qu'à la création."""
    try:
        return {"path": resolve_workspace(path)}
    except AgentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
