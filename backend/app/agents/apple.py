"""Outils Apple : Agenda, Rappels et Mail, servis aux agents en MCP embarqué.

Tout est local. L'agenda et les rappels passent par EventKit (pyobjc), Mail
par un script JXA piloté via `osascript` — Mail n'a pas de framework public,
le scripting est la voie prévue par Apple. Aucun service tiers, aucune
donnée ne quitte la machine : c'est la raison d'être de ces outils, et aussi
ce qui impose que Gordon tourne sur le Mac où vivent ces données.

Côté permissions, macOS réclame une autorisation la première fois :
Calendriers et Rappels pour EventKit, Automatisation → Mail pour le script.
La fenêtre s'affiche sur le Mac qui héberge Gordon, et l'autorisation est
rattachée à l'application qui a lancé le serveur (le terminal, en pratique).

Chaque écriture est volontairement étroite : on peut créer un évènement ou
un rappel, jamais en modifier ni en supprimer. Pour le courrier, l'outil
prépare un brouillon ouvert dans Mail — l'envoi reste un geste humain.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import subprocess
import threading
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

# Fourni par pyobjc-framework-EventKit, installé seulement sur macOS. Le
# module doit rester importable ailleurs : le catalogue est vide hors macOS,
# mais le registre importe toujours ce fichier.
try:
    import EventKit  # type: ignore
    import Foundation  # type: ignore

    AVAILABLE = True
except ImportError:  # pragma: no cover — autre OS, ou dépendance absente
    AVAILABLE = False


class AppleToolError(RuntimeError):
    """Erreur à montrer telle quelle à l'agent (et donc à l'utilisateur)."""


# --- EventKit : accès et conversions --------------------------------------

_EVENTS, _REMINDERS = 0, 1  # EKEntityType
_FULL_ACCESS = 3  # EKAuthorizationStatus : accès complet
_UNDEFINED = 0x7FFFFFFFFFFFFFFF  # NSDateComponentUndefined

_store = None
_store_lock = threading.Lock()


def _event_store():
    global _store
    with _store_lock:
        if _store is None:
            _store = EventKit.EKEventStore.alloc().init()
        return _store


def _ensure_access(entity: int, label: str) -> None:
    """Vérifie l'autorisation, en la demandant au système si besoin.

    La demande fait apparaître la fenêtre macOS sur le Mac qui héberge
    Gordon — pas dans le navigateur. Si personne n'est devant l'écran, elle
    expire et l'agent reçoit l'explication ci-dessous.
    """
    status = EventKit.EKEventStore.authorizationStatusForEntityType_(entity)
    if status == _FULL_ACCESS:
        return

    if status == 0:  # jamais demandé
        store = _event_store()
        answered = threading.Event()
        granted: dict[str, bool] = {}

        def completion(ok: bool, _error: Any) -> None:
            granted["ok"] = bool(ok)
            answered.set()

        # macOS 14 a scindé l'accès ; les sélecteurs « full access »
        # n'existent pas avant, d'où le repli sur l'ancien.
        if entity == _EVENTS and hasattr(
            store, "requestFullAccessToEventsWithCompletion_"
        ):
            store.requestFullAccessToEventsWithCompletion_(completion)
        elif entity == _REMINDERS and hasattr(
            store, "requestFullAccessToRemindersWithCompletion_"
        ):
            store.requestFullAccessToRemindersWithCompletion_(completion)
        else:  # pragma: no cover — macOS < 14
            store.requestAccessToEntityType_completion_(entity, completion)

        if answered.wait(timeout=180) and granted.get("ok"):
            return

    raise AppleToolError(
        f"macOS refuse l'accès aux {label}. Sur le Mac qui héberge Gordon : "
        f"Réglages Système → Confidentialité et sécurité → {label}, autorise "
        f"l'application qui lance le serveur (ton terminal), puis réessaie."
    )


def _parse_dt(raw: str, field: str) -> datetime.datetime:
    """Accepte AAAA-MM-JJ, avec ou sans heure HH:MM, en heure locale du Mac."""
    cleaned = raw.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    raise AppleToolError(
        f"Date invalide pour « {field} » : {raw!r}. "
        "Format attendu : AAAA-MM-JJ ou AAAA-MM-JJ HH:MM."
    )


def _nsdate(moment: datetime.datetime):
    return Foundation.NSDate.dateWithTimeIntervalSince1970_(moment.timestamp())


def _local(nsdate: Any) -> str | None:
    if nsdate is None:
        return None
    stamp = datetime.datetime.fromtimestamp(nsdate.timeIntervalSince1970())
    return stamp.strftime("%Y-%m-%d %H:%M")


def _components_str(components: Any) -> str | None:
    """Échéance d'un rappel — NSDateComponents, à l'heure parfois absente."""
    if components is None:
        return None
    date = components.date()
    if date is None:
        return None
    with_time = components.hour() != _UNDEFINED
    stamp = datetime.datetime.fromtimestamp(date.timeIntervalSince1970())
    return stamp.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")


def _find_calendar(entity: int, name: str | None, fallback: Any) -> Any:
    if not name:
        if fallback is None:
            raise AppleToolError(
                "Aucun calendrier par défaut. Précise le paramètre "
                "« calendrier » (ou « liste » pour un rappel)."
            )
        return fallback
    store = _event_store()
    for cal in store.calendarsForEntityType_(entity) or []:
        if str(cal.title()).casefold() == name.strip().casefold():
            return cal
    choices = ", ".join(
        str(c.title()) for c in store.calendarsForEntityType_(entity) or []
    )
    raise AppleToolError(f"Calendrier « {name} » introuvable. Dispo : {choices}.")


# --- EventKit : opérations (bloquantes, à passer par asyncio.to_thread) ----


def _list_events(start: str, end: str, limit: int) -> list[dict]:
    _ensure_access(_EVENTS, "Calendriers")
    store = _event_store()

    first = _parse_dt(start, "de")
    last = _parse_dt(end, "a")
    if last <= first:
        # Une borne de fin à minuit pile couvre en fait toute la journée.
        last = last + datetime.timedelta(days=1)

    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        _nsdate(first), _nsdate(last), None
    )
    events = list(store.eventsMatchingPredicate_(predicate) or [])
    events.sort(key=lambda e: e.startDate().timeIntervalSince1970())

    return [
        {
            "titre": str(event.title() or "(sans titre)"),
            "debut": _local(event.startDate()),
            "fin": _local(event.endDate()),
            "journee_entiere": bool(event.isAllDay()),
            "calendrier": str(event.calendar().title())
            if event.calendar()
            else None,
            "lieu": str(event.location()) if event.location() else None,
        }
        for event in events[:limit]
    ]


def _create_event(
    title: str,
    start: str,
    end: str,
    location: str | None,
    notes: str | None,
    calendar: str | None,
) -> dict:
    _ensure_access(_EVENTS, "Calendriers")
    store = _event_store()

    first = _parse_dt(start, "debut")
    last = _parse_dt(end, "fin")
    if last <= first:
        raise AppleToolError("La fin de l'évènement doit suivre son début.")

    event = EventKit.EKEvent.eventWithEventStore_(store)
    event.setTitle_(title.strip())
    event.setStartDate_(_nsdate(first))
    event.setEndDate_(_nsdate(last))
    if location:
        event.setLocation_(location.strip())
    if notes:
        event.setNotes_(notes.strip())
    event.setCalendar_(
        _find_calendar(_EVENTS, calendar, store.defaultCalendarForNewEvents())
    )

    ok, error = store.saveEvent_span_error_(event, 0, None)  # 0 = cet évènement
    if not ok:
        raise AppleToolError(
            f"Enregistrement refusé : {error.localizedDescription() if error else 'raison inconnue'}"
        )
    return {
        "cree": str(event.title()),
        "debut": _local(event.startDate()),
        "fin": _local(event.endDate()),
        "calendrier": str(event.calendar().title()),
    }


def _list_reminders(include_done: bool, limit: int) -> list[dict]:
    _ensure_access(_REMINDERS, "Rappels")
    store = _event_store()

    if include_done:
        predicate = store.predicateForRemindersInCalendars_(None)
    else:
        predicate = (
            store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
                None, None, None
            )
        )

    answered = threading.Event()
    box: list[Any] = []

    def completion(found: Any) -> None:
        box.extend(found or [])
        answered.set()

    store.fetchRemindersMatchingPredicate_completion_(predicate, completion)
    if not answered.wait(timeout=30):
        raise AppleToolError("La lecture des rappels n'a pas abouti à temps.")

    # Échéances d'abord, les sans-date à la fin.
    def sort_key(reminder: Any) -> tuple:
        due = reminder.dueDateComponents()
        date = due.date() if due else None
        return (date is None, date.timeIntervalSince1970() if date else 0)

    box.sort(key=sort_key)
    return [
        {
            "titre": str(reminder.title() or "(sans titre)"),
            "echeance": _components_str(reminder.dueDateComponents()),
            "liste": str(reminder.calendar().title())
            if reminder.calendar()
            else None,
            "termine": bool(reminder.isCompleted()),
            "notes": str(reminder.notes()) if reminder.notes() else None,
        }
        for reminder in box[:limit]
    ]


def _create_reminder(
    title: str, due: str | None, notes: str | None, list_name: str | None
) -> dict:
    _ensure_access(_REMINDERS, "Rappels")
    store = _event_store()

    reminder = EventKit.EKReminder.reminderWithEventStore_(store)
    reminder.setTitle_(title.strip())
    if notes:
        reminder.setNotes_(notes.strip())
    reminder.setCalendar_(
        _find_calendar(
            _REMINDERS, list_name, store.defaultCalendarForNewReminders()
        )
    )

    if due:
        moment = _parse_dt(due, "echeance")
        components = Foundation.NSDateComponents.alloc().init()
        components.setCalendar_(Foundation.NSCalendar.currentCalendar())
        components.setYear_(moment.year)
        components.setMonth_(moment.month)
        components.setDay_(moment.day)
        # Une échéance sans heure reste une échéance « à la journée ».
        if ":" in due:
            components.setHour_(moment.hour)
            components.setMinute_(moment.minute)
        reminder.setDueDateComponents_(components)

    ok, error = store.saveReminder_commit_error_(reminder, True, None)
    if not ok:
        raise AppleToolError(
            f"Enregistrement refusé : {error.localizedDescription() if error else 'raison inconnue'}"
        )
    return {
        "cree": str(reminder.title()),
        "echeance": _components_str(reminder.dueDateComponents()),
        "liste": str(reminder.calendar().title()),
    }


# --- Mail : scripts JXA ----------------------------------------------------

# Les propriétés sont lues en bloc (`messages.subject()`) : un seul Apple
# Event par propriété, quelle que soit la taille de la boîte — l'itération
# message par message prendrait des minutes.
_MAIL_SEARCH = """
function run(argv) {
  const query = (argv[0] || "").toLowerCase();
  const limit = Math.max(1, Math.min(50, parseInt(argv[1] || "20", 10) || 20));
  const pad = (n) => String(n).padStart(2, "0");
  const fmt = (d) => d
    ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
    : null;

  const inbox = Application("Mail").inbox();
  const subjects = inbox.messages.subject();
  const senders = inbox.messages.sender();
  const dates = inbox.messages.dateReceived();
  const read = inbox.messages.readStatus();
  const ids = inbox.messages.id();

  const rows = [];
  for (let i = 0; i < subjects.length; i++) {
    const subject = subjects[i] || "";
    const sender = senders[i] || "";
    if (
      query &&
      !subject.toLowerCase().includes(query) &&
      !sender.toLowerCase().includes(query)
    )
      continue;
    rows.push({
      id: ids[i],
      objet: subject,
      de: sender,
      recu: fmt(dates[i]),
      non_lu: read[i] === false,
    });
  }
  rows.sort((a, b) => String(b.recu).localeCompare(String(a.recu)));
  return JSON.stringify(rows.slice(0, limit));
}
"""

_MAIL_READ = """
function run(argv) {
  const target = parseInt(argv[0], 10);
  const inbox = Application("Mail").inbox();
  const ids = inbox.messages.id();
  const i = ids.indexOf(target);
  if (i === -1)
    return JSON.stringify({
      erreur: "Message introuvable dans la boîte de réception. Son id vient-il bien de mail_chercher ?",
    });
  const m = inbox.messages[i];
  return JSON.stringify({
    objet: m.subject() || "",
    de: m.sender() || "",
    contenu: String(m.content() || "").slice(0, 20000),
  });
}
"""

_MAIL_DRAFT = """
function run(argv) {
  const [to, subject, body, cc] = argv;
  const Mail = Application("Mail");
  const split = (s) => (s || "").split(",").map((x) => x.trim()).filter(Boolean);

  const draft = Mail.OutgoingMessage({
    subject: subject,
    content: body,
    visible: true,
  });
  Mail.outgoingMessages.push(draft);
  for (const address of split(to))
    draft.toRecipients.push(Mail.Recipient({ address: address }));
  for (const address of split(cc))
    draft.ccRecipients.push(Mail.Recipient({ address: address }));
  Mail.activate();
  return JSON.stringify({ brouillon_ouvert: true, a: split(to), objet: subject });
}
"""


def _osascript(script: str, *args: str) -> Any:
    """Exécute un script JXA et décode sa sortie JSON."""
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script, *args],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppleToolError(
            "Mail n'a pas répondu à temps. L'application est peut-être en "
            "train d'indexer une grosse boîte — réessaie dans un instant."
        ) from exc

    if proc.returncode != 0:
        detail = proc.stderr.strip()
        if "-1743" in detail or "autorisé" in detail or "not allowed" in detail:
            raise AppleToolError(
                "macOS a bloqué le contrôle de Mail. Sur le Mac qui héberge "
                "Gordon : Réglages Système → Confidentialité et sécurité → "
                "Automatisation, autorise Mail pour l'application qui lance "
                "le serveur (ton terminal), puis réessaie."
            )
        raise AppleToolError(f"Échec du script Mail : {detail or 'erreur inconnue'}")

    return json.loads(proc.stdout.strip() or "null")


# --- Les outils MCP --------------------------------------------------------


def _ok(payload: Any) -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=1),
            }
        ]
    }


def _failure(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "is_error": True}


async def _guarded(fn, *args) -> dict:
    """Exécute une opération bloquante hors de la boucle, erreurs incluses.

    Les AppleToolError portent un message déjà rédigé pour l'utilisateur ;
    tout le reste est résumé sans traceback — l'agent n'en ferait rien.
    """
    try:
        return _ok(await asyncio.to_thread(fn, *args))
    except AppleToolError as exc:
        return _failure(str(exc))
    except Exception as exc:  # noqa: BLE001 — l'agent doit pouvoir continuer
        return _failure(f"Erreur inattendue ({type(exc).__name__}) : {exc}")


@tool(
    "agenda",
    "Liste les évènements du calendrier Apple entre deux dates (heure locale).",
    {
        "type": "object",
        "properties": {
            "de": {"type": "string", "description": "Début, AAAA-MM-JJ"},
            "a": {"type": "string", "description": "Fin, AAAA-MM-JJ (incluse)"},
            "max": {"type": "integer", "description": "Nombre maximal, 50 par défaut"},
        },
        "required": ["de", "a"],
    },
)
async def agenda(args: dict) -> dict:
    limit = max(1, min(int(args.get("max") or 50), 200))
    return await _guarded(_list_events, args["de"], args["a"], limit)


@tool(
    "agenda_creer",
    "Crée un évènement dans le calendrier Apple. Création seulement : aucune "
    "modification ni suppression possible.",
    {
        "type": "object",
        "properties": {
            "titre": {"type": "string"},
            "debut": {"type": "string", "description": "AAAA-MM-JJ HH:MM"},
            "fin": {"type": "string", "description": "AAAA-MM-JJ HH:MM"},
            "lieu": {"type": "string"},
            "notes": {"type": "string"},
            "calendrier": {
                "type": "string",
                "description": "Nom du calendrier ; celui par défaut sinon",
            },
        },
        "required": ["titre", "debut", "fin"],
    },
)
async def agenda_creer(args: dict) -> dict:
    return await _guarded(
        _create_event,
        args["titre"],
        args["debut"],
        args["fin"],
        args.get("lieu"),
        args.get("notes"),
        args.get("calendrier"),
    )


@tool(
    "rappels",
    "Liste les rappels Apple, échéances les plus proches d'abord.",
    {
        "type": "object",
        "properties": {
            "inclure_termines": {
                "type": "boolean",
                "description": "Inclure aussi les rappels déjà cochés",
            },
            "max": {"type": "integer", "description": "Nombre maximal, 50 par défaut"},
        },
    },
)
async def rappels(args: dict) -> dict:
    limit = max(1, min(int(args.get("max") or 50), 200))
    return await _guarded(
        _list_reminders, bool(args.get("inclure_termines")), limit
    )


@tool(
    "rappel_creer",
    "Crée un rappel Apple. Création seulement : impossible de cocher, "
    "modifier ou supprimer un rappel existant.",
    {
        "type": "object",
        "properties": {
            "titre": {"type": "string"},
            "echeance": {
                "type": "string",
                "description": "AAAA-MM-JJ, ou AAAA-MM-JJ HH:MM pour une heure précise",
            },
            "notes": {"type": "string"},
            "liste": {
                "type": "string",
                "description": "Nom de la liste de rappels ; celle par défaut sinon",
            },
        },
        "required": ["titre"],
    },
)
async def rappel_creer(args: dict) -> dict:
    return await _guarded(
        _create_reminder,
        args["titre"],
        args.get("echeance"),
        args.get("notes"),
        args.get("liste"),
    )


@tool(
    "mail_chercher",
    "Cherche dans la boîte de réception Apple Mail (objet et expéditeur). "
    "Sans texte : les messages les plus récents.",
    {
        "type": "object",
        "properties": {
            "texte": {"type": "string", "description": "Texte à chercher"},
            "max": {"type": "integer", "description": "Nombre maximal, 20 par défaut"},
        },
    },
)
async def mail_chercher(args: dict) -> dict:
    return await _guarded(
        _osascript,
        _MAIL_SEARCH,
        str(args.get("texte") or ""),
        str(args.get("max") or 20),
    )


@tool(
    "mail_lire",
    "Lit le contenu d'un message de la boîte de réception, par l'id renvoyé "
    "par mail_chercher.",
    {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    },
)
async def mail_lire(args: dict) -> dict:
    return await _guarded(_osascript, _MAIL_READ, str(int(args["id"])))


@tool(
    "mail_brouillon",
    "Prépare un brouillon ouvert dans Apple Mail. N'envoie jamais rien : "
    "l'utilisateur relit et envoie lui-même.",
    {
        "type": "object",
        "properties": {
            "a": {
                "type": "string",
                "description": "Destinataires, séparés par des virgules",
            },
            "objet": {"type": "string"},
            "corps": {"type": "string"},
            "cc": {"type": "string", "description": "Copies, séparées par des virgules"},
        },
        "required": ["a", "objet", "corps"],
    },
)
async def mail_brouillon(args: dict) -> dict:
    return await _guarded(
        _osascript,
        _MAIL_DRAFT,
        str(args["a"]),
        str(args["objet"]),
        str(args["corps"]),
        str(args.get("cc") or ""),
    )


SERVER = create_sdk_mcp_server(
    name="apple",
    version="1.0.0",
    tools=[
        agenda,
        agenda_creer,
        rappels,
        rappel_creer,
        mail_chercher,
        mail_lire,
        mail_brouillon,
    ],
)


# Entrées du catalogue d'outils, fusionnées par le registre quand les outils
# Apple sont actifs. Une case cochée peut débloquer plusieurs outils MCP
# (chercher + lire pour Mail) : le champ `sdk` porte les noms complets.
CATALOG: dict[str, dict] = {
    "Agenda": {
        "label": "Lire l'agenda",
        "hint": "Consulter les évènements du calendrier Apple sur une période.",
        "group": "apple",
        "sdk": ["mcp__apple__agenda"],
    },
    "AgendaAjout": {
        "label": "Créer un évènement",
        "hint": (
            "Ajouter un évènement au calendrier. Création seulement : "
            "jamais de modification ni de suppression."
        ),
        "group": "apple",
        "sdk": ["mcp__apple__agenda_creer"],
    },
    "Rappels": {
        "label": "Lire les rappels",
        "hint": "Consulter les rappels Apple et leurs échéances.",
        "group": "apple",
        "sdk": ["mcp__apple__rappels"],
    },
    "RappelAjout": {
        "label": "Créer un rappel",
        "hint": "Ajouter un rappel, avec échéance et liste au choix.",
        "group": "apple",
        "sdk": ["mcp__apple__rappel_creer"],
    },
    "Mail": {
        "label": "Lire les mails",
        "hint": (
            "Chercher dans la boîte de réception et lire un message. "
            "Lecture seule."
        ),
        "group": "apple",
        "sdk": ["mcp__apple__mail_chercher", "mcp__apple__mail_lire"],
    },
    "MailBrouillon": {
        "label": "Préparer un brouillon",
        "hint": (
            "Rédiger un brouillon ouvert dans Mail. L'envoi reste un geste "
            "humain : l'agent ne peut rien expédier."
        ),
        "group": "apple",
        "sdk": ["mcp__apple__mail_brouillon"],
    },
}
