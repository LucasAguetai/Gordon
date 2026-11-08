"""Routes d'authentification par passkey."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from ..auth import passkey
from ..auth.session import current_user, issue, revoke
from ..config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegistrationFinish(BaseModel):
    credential: dict
    label: str | None = Field(default=None, max_length=80)


class AuthenticationFinish(BaseModel):
    credential: dict


@router.get("/status")
def auth_status(response: Response) -> dict:
    """État de l'instance : y a-t-il une passkey, peut-on en créer une ?"""
    response.headers["Cache-Control"] = "no-store"
    return passkey.status()


@router.post("/register/begin")
def register_begin(label: str | None = None) -> dict:
    try:
        return passkey.start_registration(label)
    except passkey.PasskeyError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


@router.post("/register/finish")
def register_finish(body: RegistrationFinish, response: Response) -> dict:
    try:
        user_id = passkey.finish_registration(body.credential, body.label)
    except passkey.PasskeyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    issue(response, user_id)
    return {"ok": True, "user_id": user_id}


@router.post("/login/begin")
def login_begin() -> dict:
    try:
        return passkey.start_authentication()
    except passkey.PasskeyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/login/finish")
def login_finish(body: AuthenticationFinish, response: Response) -> dict:
    try:
        user_id = passkey.finish_authentication(body.credential)
    except passkey.PasskeyError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    issue(response, user_id)
    return {"ok": True, "user_id": user_id}


@router.post("/logout")
def logout(response: Response) -> dict:
    revoke(response)
    return {"ok": True}


@router.get("/me")
def me(user_id: str = Depends(current_user)) -> dict:
    return {
        "user_id": user_id,
        "devices": passkey.list_devices(user_id),
        "model": settings.model,
    }


@router.post("/devices/begin")
def add_device_begin(user_id: str = Depends(current_user)) -> dict:
    """Ajoute une passkey depuis une session déjà authentifiée.

    C'est le chemin pour enrôler un second appareil sans rouvrir
    l'inscription publique.
    """
    try:
        return passkey.start_registration()
    except passkey.PasskeyError:
        # Session authentifiée : on contourne la fermeture de l'inscription,
        # puisque l'identité est déjà prouvée par le cookie.
        settings.allow_registration = True
        try:
            return passkey.start_registration()
        finally:
            settings.allow_registration = False


@router.delete("/devices/{credential_id}")
def remove_device(
    credential_id: str, user_id: str = Depends(current_user)
) -> dict:
    try:
        passkey.remove_device(user_id, credential_id)
    except passkey.PasskeyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True}
