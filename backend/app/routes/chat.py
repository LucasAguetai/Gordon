"""Routes des agents : liste, création, suppression, conversation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agents import registry, runner
from ..auth.session import current_user

router = APIRouter(prefix="/api", tags=["agents"])


class Message(BaseModel):
    prompt: str = Field(min_length=1, max_length=50_000)


class NewAgent(BaseModel):
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
def create_agent(body: NewAgent, user_id: str = Depends(current_user)) -> dict:
    try:
        spec = registry.create(
            name=body.name,
            role=body.role,
            tagline=body.tagline,
            accent=body.accent,
            tools=body.tools,
            system_prompt=body.system_prompt,
            look=body.look,
            effort=body.effort,
            workspace=body.workspace,
        )
    except registry.AgentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"agent": spec.public()}


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str, user_id: str = Depends(current_user)) -> dict:
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
