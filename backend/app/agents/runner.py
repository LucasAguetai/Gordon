"""Pont entre Gordon et le Claude Agent SDK.

Le SDK lance le CLI `claude` en sous-processus ; c'est lui qui porte
l'authentification (abonnement Claude). Aucune clé API n'est nécessaire.

Deux choix d'architecture :

Plutôt que de garder un ClaudeSDKClient vivant par conversation (un
sous-processus par agent et par utilisateur, à surveiller et à expirer), on
utilise query() avec `resume=<session_id>`. L'identifiant de session est
renvoyé par le SDK à la fin de chaque tour et stocké en base. La conversation
survit donc à un redémarrage du serveur, et il n'y a aucun processus à gérer
entre deux messages.

Le tour lui-même s'exécute dans une tâche asyncio séparée de la requête HTTP.
La réponse SSE ne fait que lire une file alimentée par cette tâche : si le
client disparaît (page fermée, téléphone verrouillé), le tour continue, la
réponse est enregistrée en base, et l'interface la retrouve en rouvrant
l'agent. Sans cette séparation, fermer l'onglet tuait le tour en plein vol.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass, field
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
from . import apple, registry
from .registry import AgentSpec


class TurnInProgress(RuntimeError):
    """Un tour est déjà en cours pour cet agent : un seul à la fois."""


def _sse(event: str, data: dict[str, Any]) -> str:
    """Encode un évènement Server-Sent Events."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# --- Résolution des outils -------------------------------------------------


def _resolve_tools(spec: AgentSpec) -> tuple[list[str], set[str], bool]:
    """Traduit la fiche d'agent en listes pour le SDK.

    Renvoie (outils intégrés, noms réellement autorisés, besoin du serveur
    Apple). Les entrées du catalogue qui portent un champ `sdk` sont des
    outils MCP : la case cochée dans la fiche en débloque un ou plusieurs,
    sous leur nom complet `mcp__apple__…`. Un outil absent du catalogue est
    ignoré — c'est le cas d'un agent créé avec les outils Apple si on
    déplace l'instance sur une machine qui ne les a pas.
    """
    builtin: list[str] = []
    allowed: set[str] = set()
    wants_apple = False

    for name in spec.tools:
        meta = registry.TOOL_CATALOG.get(name)
        if meta is None:
            continue
        sdk_names = meta.get("sdk")
        if sdk_names:
            allowed.update(sdk_names)
            wants_apple = wants_apple or meta["group"] == "apple"
        else:
            builtin.append(name)
            allowed.add(name)

    return builtin, allowed, wants_apple


def _build_options(spec: AgentSpec, resume: str | None) -> ClaudeAgentOptions:
    """Construit les options du SDK pour un agent donné.

    Deux garde-fous importants :

    `setting_sources=[]` empêche le SDK de charger les réglages Claude de la
    machine (CLAUDE.md, settings.json, skills du poste). Sans ça, un agent de
    Gordon héritait du contexte de développement de l'utilisateur — ce qui
    pollue ses réponses et élargit silencieusement ses permissions.

    `can_use_tool` applique la liste blanche de la fiche d'agent — y compris
    pour les outils MCP, désignés par leur nom complet. On ne se repose pas
    seulement sur `allowed_tools=` : c'est une seconde barrière, côté
    serveur, et elle refuse franchement au lieu de laisser la requête
    attendre une validation humaine qui n'arriverait jamais.
    """
    builtin, allowed, wants_apple = _resolve_tools(spec)

    async def gate(
        tool_name: str, input_data: dict, context: Any
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name in allowed:
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(
            message=(
                f"L'agent {spec.name} n'a pas accès à l'outil {tool_name}."
            ),
            interrupt=False,
        )

    options = ClaudeAgentOptions(
        system_prompt=spec.system_prompt,
        tools=builtin,
        allowed_tools=sorted(allowed),
        can_use_tool=gate,
        setting_sources=[],
        model=settings.model,
        resume=resume,
        include_partial_messages=True,
    )

    if wants_apple:
        options.mcp_servers = {"apple": apple.SERVER}
    if spec.effort:
        options.effort = spec.effort
    if spec.needs_workspace:
        # Chaque agent a son propre dossier ; on retombe sur le dossier
        # partagé si aucun n'a été choisi (agents créés avant ce réglage).
        options.cwd = spec.workspace or str(settings.workspace_dir)
    if settings.cli_path:
        options.cli_path = settings.cli_path

    return options


# --- Tours en cours --------------------------------------------------------


@dataclass
class _ActiveTurn:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: asyncio.Task | None = None


# Un seul tour à la fois par (utilisateur, agent). En mémoire : un tour ne
# survit pas à un redémarrage du serveur, et c'est très bien ainsi.
_active: dict[tuple[str, str], _ActiveTurn] = {}


def is_busy(user_id: str, agent_id: str) -> bool:
    return (user_id, agent_id) in _active


def start_turn(spec: AgentSpec, user_id: str, prompt: str) -> AsyncIterator[str]:
    """Démarre un tour en tâche de fond et renvoie le flux SSE à servir.

    Le message de l'utilisateur est enregistré immédiatement : même si le
    tour échoue ensuite, l'historique reflète ce qui a été demandé.
    """
    key = (user_id, spec.id)
    if key in _active:
        raise TurnInProgress(
            f"{spec.name} travaille déjà sur un message. Attends sa réponse."
        )

    db.append_message(user_id, spec.id, "user", prompt)

    turn = _ActiveTurn()
    _active[key] = turn
    turn.task = asyncio.create_task(_run_turn(spec, user_id, prompt, turn))
    return _follow(turn)


async def _follow(turn: _ActiveTurn) -> AsyncIterator[str]:
    """Relaie la file d'évènements vers le client attaché.

    Si le client ferme la connexion, ce générateur meurt — mais la tâche du
    tour, elle, continue et les évènements s'accumulent dans la file jusqu'à
    la fin du tour, où tout est relâché avec elle.
    """
    while True:
        item = await turn.queue.get()
        if item is None:
            return
        yield item


async def _run_turn(
    spec: AgentSpec,
    user_id: str,
    prompt: str,
    turn: _ActiveTurn,
) -> None:
    """Exécute un tour complet : flux SSE vers la file + transcription en base.

    Évènements émis :
      meta     — agent et reprise de session
      thinking — l'agent réfléchit (signal de progression)
      tool     — un outil est utilisé
      text     — fragment de réponse
      done     — fin du tour, avec durée et usage
      error    — échec
    """
    key = (user_id, spec.id)

    def emit(event: str, data: dict[str, Any]) -> None:
        turn.queue.put_nowait(_sse(event, data))

    def record(who: str, text: str, tools: list[str] | None = None,
               meta: dict | None = None) -> None:
        db.append_message(
            user_id, spec.id, who, text,
            tools=json.dumps(tools, ensure_ascii=False) if tools else None,
            meta=json.dumps(meta, ensure_ascii=False) if meta else None,
        )

    text_parts: list[str] = []
    tools_used: list[str] = []

    def fail(message: str) -> None:
        # Une réponse entamée puis interrompue vaut la peine d'être gardée :
        # elle a été vue à l'écran, l'historique doit la refléter.
        if text_parts:
            record("agent", "".join(text_parts), tools_used,
                   {"interrupted": True})
        record("error", message)
        emit("error", {"message": message})

    # Tout le tour vit sous ce try, préparation des options comprise : une
    # exception hors du try tuerait la tâche en silence et laisserait un
    # tour fantôme dans _active — l'agent paraîtrait occupé pour toujours.
    try:
        resume = db.get_agent_session(user_id, spec.id)
        options = _build_options(spec, resume)

        emit("meta", {"agent": spec.id, "resumed": resume is not None})

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                        emit("text", {"text": block.text})
                    elif isinstance(block, ThinkingBlock):
                        # Signal de progression : on n'expose pas le contenu
                        # du raisonnement, seulement le fait qu'il a lieu.
                        emit("thinking", {})
                    elif isinstance(block, ToolUseBlock):
                        if block.name not in tools_used:
                            tools_used.append(block.name)
                        emit("tool", {"name": block.name})

            elif isinstance(message, ResultMessage):
                # Mémorise la session pour que le prochain message reprenne
                # le fil de cette conversation.
                if message.session_id:
                    db.set_agent_session(user_id, spec.id, message.session_id)

                if message.is_error:
                    detail = message.result or message.subtype
                    fail(f"L'agent a échoué : {detail}")
                    return

                usage = message.usage or {}
                meta = {
                    "duration_ms": message.duration_ms,
                    "output_tokens": usage.get("output_tokens"),
                }
                record("agent", "".join(text_parts) or "(aucune réponse)",
                       tools_used, meta)
                emit("done", {"turns": message.num_turns, **meta})

    except asyncio.CancelledError:
        # Annulation volontaire (nouveau fil, suppression de l'agent) :
        # l'appelant purge l'historique juste après, rien à enregistrer.
        raise
    except FileNotFoundError:
        # Le SDK embarque son propre CLI, donc ce cas ne survient que si
        # GORDON_CLI_PATH pointe vers un chemin invalide.
        fail(
            "Binaire `claude` introuvable au chemin configuré. "
            "Vérifie GORDON_CLI_PATH dans backend/.env, ou retire "
            "ce réglage pour utiliser le CLI fourni avec le SDK."
        )
    except Exception as exc:  # noqa: BLE001 — remonté tel quel au client
        fail(f"{type(exc).__name__}: {exc}")
    finally:
        if _active.get(key) is turn:
            del _active[key]
        turn.queue.put_nowait(None)


# --- Cycle de vie ----------------------------------------------------------


async def _abort(key: tuple[str, str]) -> None:
    """Annule un tour en cours et attend qu'il soit réellement terminé.

    L'attente compte : sans elle, la tâche annulée pourrait écrire sa
    transcription après la purge qui suit l'annulation.
    """
    turn = _active.pop(key, None)
    if turn and turn.task:
        turn.task.cancel()
        with suppress(BaseException):
            await turn.task


async def reset_conversation(user_id: str, agent_id: str) -> None:
    """Oublie tout : tour en cours, session Claude, transcription."""
    await _abort((user_id, agent_id))
    db.clear_agent_session(user_id, agent_id)
    db.clear_messages(user_id, agent_id)


async def abort_agent(agent_id: str) -> None:
    """Arrête les tours en cours d'un agent, avant sa suppression."""
    for key in [k for k in _active if k[1] == agent_id]:
        await _abort(key)
