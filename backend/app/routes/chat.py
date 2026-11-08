"""Routes de conversation avec les agents."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agents import registry, runner
from ..auth.session import current_user

router = APIRouter(prefix="/api", tags=["agents"])


class Message(BaseModel):
    prompt: str = Field(min_length=1, max_length=50_000)


@router.get("/agents")
def list_agents(user_id: str = Depends(current_user)) -> dict:
    return {"agents": registry.listing()}


@router.post("/agents/{agent_id}/chat")
async def chat(
    agent_id: str,
    body: Message,
    user_id: str = Depends(current_user),
) -> StreamingResponse:
    spec = registry.get(agent_id)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent inconnu.")

    return StreamingResponse(
        runner.stream_turn(spec, user_id, body.prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Évite la mise en tampon par un reverse proxy en production,
            # qui casserait le streaming.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agents/{agent_id}/reset")
def reset(agent_id: str, user_id: str = Depends(current_user)) -> dict:
    if registry.get(agent_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent inconnu.")
    runner.reset_conversation(user_id, agent_id)
    return {"ok": True}
