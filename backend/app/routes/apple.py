"""Page de gestion des accès Apple.

Clarifie ce que « connecté à Apple » veut dire ici : rien ne relie Gordon au
compte iCloud. Les outils lisent les applications du Mac, et chaque accès est
une autorisation macOS, accordée à la machine, révocable dans les Réglages
Système. Ces routes exposent l'état de ces autorisations et permettent de
déclencher les demandes — la fenêtre s'affiche sur le Mac qui héberge Gordon.
"""

from __future__ import annotations

import subprocess
import threading

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .. import db
from ..agents import apple
from ..auth.session import current_user
from ..config import settings

router = APIRouter(prefix="/api/apple", tags=["apple"])

KV_MAIL = "apple_mail_status"

# Panneaux des Réglages Système vers lesquels on sait téléporter l'utilisateur.
_PANELS = {
    "calendriers": "Privacy_Calendars",
    "rappels": "Privacy_Reminders",
    "mail": "Privacy_Automation",
}


class Domain(BaseModel):
    domain: str


@router.get("")
def overview(user_id: str = Depends(current_user)) -> dict:
    if not settings.apple_tools:
        return {"available": False}

    data = apple.access_overview()
    if data.get("available"):
        # L'Automatisation n'a pas d'API de consultation passive : on affiche
        # le résultat du dernier essai réel, ou « à tester ».
        stored = db.get_kv(KV_MAIL)
        data["mail"] = {"status": stored["value"] if stored else "a_tester"}
    return data


@router.post("/request")
def request_access(body: Domain, user_id: str = Depends(current_user)) -> dict:
    """Déclenche la demande d'accès, sans bloquer la réponse HTTP.

    La fenêtre macOS attend un humain devant le Mac ; la page, elle, sonde
    l'état jusqu'à voir la décision.
    """
    if not settings.apple_tools:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Outils Apple inactifs.")
    if body.domain not in _PANELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Domaine inconnu.")

    def run() -> None:
        try:
            if body.domain == "mail":
                db.set_kv(KV_MAIL, apple.probe_mail())
            else:
                apple.request_access(body.domain)
        except apple.AppleToolError:
            if body.domain == "mail":
                db.set_kv(KV_MAIL, "refuse")
            # Calendriers/Rappels : le refus se lit directement dans le statut.

    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}


@router.post("/settings")
def open_settings(body: Domain, user_id: str = Depends(current_user)) -> dict:
    """Ouvre les Réglages Système du Mac sur le bon panneau."""
    panel = _PANELS.get(body.domain)
    if panel is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Domaine inconnu.")
    subprocess.Popen(
        ["open", f"x-apple.systempreferences:com.apple.preference.security?{panel}"]
    )
    return {"ok": True}
