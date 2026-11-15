"""Routes des agents : liste, création, édition, suppression, conversation."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import db
from ..agents import registry, runner
from ..auth.session import current_user

router = APIRouter(prefix="/api", tags=["agents"])


class Message(BaseModel):
    prompt: str = Field(min_length=1, max_length=50_000)


class AgentBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    role: str = Field(min_length=1, max_length=40)
    tagline: str = Field(default="", max_length=120)
    accent: str = Field(min_length=7, max_length=7)
    tools: list[str] = Field(default_factory=list, max_length=16)
    system_prompt: str = Field(min_length=1, max_length=20_000)
    look: dict = Field(default_factory=dict)
    effort: str | None = None
    workspace: str | None = Field(default=None, max_length=1024)


@router.get("/agents")
def list_agents(user_id: str = Depends(current_user)) -> dict:
    return {"agents": registry.listing(), "tools": registry.TOOL_CATALOG}


@router.post("/agents", status_code=status.HTTP_201_CREATED)
def create_agent(body: AgentBody, user_id: str = Depends(current_user)) -> dict:
    try:
        spec = registry.create(**body.model_dump())
    except registry.AgentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"agent": spec.public()}


@router.put("/agents/{agent_id}")
def update_agent(
    agent_id: str, body: AgentBody, user_id: str = Depends(current_user)
) -> dict:
    if registry.get(agent_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent inconnu.")
    try:
        spec = registry.update(agent_id, **body.model_dump())
    except registry.AgentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"agent": spec.public()}


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, user_id: str = Depends(current_user)) -> dict:
    # Un tour encore en vol écrirait dans la transcription d'un agent
    # disparu : on l'arrête d'abord.
    await runner.abort_agent(agent_id)
    if not registry.delete(agent_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent inconnu.")
    return {"ok": True}


@router.post("/agents/{agent_id}/chat")
async def chat(
    agent_id: str,
    body: Message,
    user_id: str = Depends(current_user),
) -> StreamingResponse:
    spec = registry.get(agent_id)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent inconnu.")

    try:
        stream = runner.start_turn(spec, user_id, body.prompt)
    except runner.TurnInProgress as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Évite la mise en tampon par un reverse proxy en production,
            # qui casserait le streaming.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/agents/{agent_id}/history")
def history(agent_id: str, user_id: str = Depends(current_user)) -> dict:
    """Transcription de la conversation, et tour éventuellement en cours.

    `pending` permet à l'interface de se raccrocher à un tour lancé puis
    quitté (page fermée, téléphone verrouillé) : elle sonde jusqu'à voir la
    réponse apparaître dans la transcription.
    """
    if registry.get(agent_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent inconnu.")

    turns = [
        {
            "id": row["id"],
            "who": row["who"],
            "text": row["text"],
            "tools": json.loads(row["tools"]) if row["tools"] else [],
            "meta": json.loads(row["meta"]) if row["meta"] else None,
            "at": row["created_at"],
        }
        for row in db.list_messages(user_id, agent_id)
    ]
    return {"turns": turns, "pending": runner.is_busy(user_id, agent_id)}


@router.post("/agents/{agent_id}/reset")
async def reset(agent_id: str, user_id: str = Depends(current_user)) -> dict:
    if registry.get(agent_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent inconnu.")
    await runner.reset_conversation(user_id, agent_id)
    return {"ok": True}
