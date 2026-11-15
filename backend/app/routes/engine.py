"""Connexion du moteur depuis l'interface (flux setup-token piloté)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import engine
from ..auth.session import current_user

router = APIRouter(prefix="/api/engine", tags=["engine"])


class Code(BaseModel):
    code: str = Field(min_length=1, max_length=2000)


@router.get("")
def engine_status(user_id: str = Depends(current_user)) -> dict:
    return engine.status()


@router.post("/connect")
async def connect(user_id: str = Depends(current_user)) -> dict:
    """Lance le flux et renvoie l'adresse d'autorisation à ouvrir."""
    try:
        url = await asyncio.to_thread(engine.begin)
    except engine.EngineError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return {"url": url}


@router.post("/connect/code")
async def submit_code(body: Code, user_id: str = Depends(current_user)) -> dict:
    try:
        await asyncio.to_thread(engine.finish, body.code)
    except engine.EngineError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"ok": True}


@router.delete("/connect")
def cancel(user_id: str = Depends(current_user)) -> dict:
    engine.cancel()
    return {"ok": True}


@router.delete("/token")
def forget(user_id: str = Depends(current_user)) -> dict:
    engine.forget()
    return {"ok": True}
