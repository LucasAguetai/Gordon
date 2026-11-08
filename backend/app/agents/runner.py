"""Pont entre Gordon et le Claude Agent SDK.

Le SDK lance le CLI `claude` en sous-processus ; c'est lui qui porte
l'authentification (abonnement Claude). Aucune clé API n'est nécessaire.

Choix d'architecture : plutôt que de garder un ClaudeSDKClient vivant par
conversation (un sous-processus par agent et par utilisateur, à surveiller et
à expirer), on utilise query() avec `resume=<session_id>`. L'identifiant de
session est renvoyé par le SDK à la fin de chaque tour et stocké en base. La
conversation survit donc à un redémarrage du serveur, et il n'y a aucun
processus à gérer entre deux messages.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    query,
)
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

from .. import db
from ..config import settings
from .registry import AgentSpec


class AgentRunError(RuntimeError):
    """Échec de l'exécution d'un agent, destiné à être montré à l'utilisateur."""


def _sse(event: str, data: dict[str, Any]) -> str:
    """Encode un évènement Server-Sent Events."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_options(spec: AgentSpec, resume: str | None) -> ClaudeAgentOptions:
    """Construit les options du SDK pour un agent donné.

    Deux garde-fous importants :

    `setting_sources=[]` empêche le SDK de charger les réglages Claude de la
    machine (CLAUDE.md, settings.json, skills du poste). Sans ça, un agent de
    Gordon héritait du contexte de développement de l'utilisateur — ce qui
    pollue ses réponses et élargit silencieusement ses permissions.

    `can_use_tool` applique la liste blanche de la fiche d'agent. On ne se
    repose pas seulement sur `tools=` : c'est une seconde barrière, côté
    serveur, et elle refuse franchement au lieu de laisser la requête
    attendre une validation humaine qui n'arrivera jamais.
    """
    allowed = set(spec.tools)

    async def gate(
        tool_name: str, input_data: dict, context: Any
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name in allowed or tool_name.startswith("mcp__"):
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(
            message=(
                f"L'agent {spec.name} n'a pas accès à l'outil {tool_name}."
            ),
            interrupt=False,
        )

    options = ClaudeAgentOptions(
        system_prompt=spec.system_prompt,
        tools=spec.tools,
        allowed_tools=spec.tools,
        can_use_tool=gate,
        setting_sources=[],
        model=spec.model or settings.model,
        resume=resume,
        include_partial_messages=True,
    )

    if spec.effort:
        options.effort = spec.effort
    if spec.needs_workspace:
        options.cwd = str(settings.workspace_dir)
    if settings.cli_path:
        options.cli_path = settings.cli_path

    return options


async def stream_turn(
    spec: AgentSpec,
    user_id: str,
    prompt: str,
) -> AsyncIterator[str]:
    """Exécute un tour de conversation et diffuse le résultat en SSE.

    Évènements émis :
      meta     — agent et reprise de session
      thinking — l'agent réfléchit (signal de progression)
      tool     — un outil est utilisé
      text     — fragment de réponse
      done     — fin du tour, avec coût et usage
      error    — échec
    """
    resume = db.get_agent_session(user_id, spec.id)
    options = _build_options(spec, resume)

    yield _sse("meta", {"agent": spec.id, "resumed": resume is not None})

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        yield _sse("text", {"text": block.text})
                    elif isinstance(block, ThinkingBlock):
                        # Signal de progression : on n'expose pas le contenu
                        # du raisonnement, seulement le fait qu'il a lieu.
                        yield _sse("thinking", {})
                    elif isinstance(block, ToolUseBlock):
                        yield _sse("tool", {"name": block.name})

            elif isinstance(message, ResultMessage):
                # Mémorise la session pour que le prochain message reprenne
                # le fil de cette conversation.
                if message.session_id:
                    db.set_agent_session(user_id, spec.id, message.session_id)

                if message.is_error:
                    detail = message.result or message.subtype
                    yield _sse(
                        "error",
                        {"message": f"L'agent a échoué : {detail}"},
                    )
                    return

                usage = message.usage or {}
                yield _sse(
                    "done",
                    {
                        "turns": message.num_turns,
                        "duration_ms": message.duration_ms,
                        "cost_usd": message.total_cost_usd,
                        "input_tokens": usage.get("input_tokens"),
                        "output_tokens": usage.get("output_tokens"),
                    },
                )

    except FileNotFoundError:
        # Le SDK embarque son propre CLI, donc ce cas ne survient que si
        # GORDON_CLI_PATH pointe vers un chemin invalide.
        yield _sse(
            "error",
            {
                "message": (
                    "Binaire `claude` introuvable au chemin configuré. "
                    "Vérifie GORDON_CLI_PATH dans backend/.env, ou retire "
                    "ce réglage pour utiliser le CLI fourni avec le SDK."
                )
            },
        )
    except Exception as exc:  # noqa: BLE001 — remonté tel quel au client
        yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})


def reset_conversation(user_id: str, agent_id: str) -> None:
    db.clear_agent_session(user_id, agent_id)
