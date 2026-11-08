"""Sessions par cookie signé, et dépendance FastAPI de protection des routes."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="gordon-session")


def issue(response: Response, user_id: str) -> None:
    token = _serializer.dumps({"uid": user_id})
    response.set_cookie(
        key=settings.session_cookie,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        # En production derrière HTTPS le cookie doit être `secure`.
        # On le déduit de l'origine configurée plutôt que d'un flag séparé,
        # pour qu'il n'y ait pas deux réglages à garder cohérents.
        secure=settings.rp_origin.startswith("https://"),
        path="/",
    )


def revoke(response: Response) -> None:
    response.delete_cookie(settings.session_cookie, path="/")


def read(request: Request) -> str | None:
    token = request.cookies.get(settings.session_cookie)
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid")


def current_user(request: Request) -> str:
    """Dépendance FastAPI : exige une session valide."""
    user_id = read(request)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
        )
    return user_id


RequireUser = Depends(current_user)
