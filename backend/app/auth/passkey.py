"""Authentification par passkey (WebAuthn / FIDO2).

Modèle retenu : Gordon est une instance personnelle, mono-utilisateur. Le
premier visiteur enregistre sa passkey et devient propriétaire ; ensuite
l'inscription se ferme d'elle-même. Pour ajouter un autre appareil (téléphone,
seconde machine), on enregistre une passkey supplémentaire depuis une session
déjà authentifiée — c'est le chemin sûr, il ne rouvre rien publiquement.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .. import db
from ..config import settings

# Identifiant de l'utilisateur unique de l'instance.
OWNER_ID = "owner"

CHALLENGE_TTL = 300  # secondes


class PasskeyError(RuntimeError):
    """Erreur d'enregistrement ou de vérification de passkey."""


@dataclass
class _Challenge:
    value: bytes
    expires_at: float


# Les challenges sont à usage unique et vivent cinq minutes : les garder en
# mémoire est suffisant et évite de leur créer une table.
_challenges: dict[str, _Challenge] = {}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _store_challenge(kind: str, value: bytes) -> None:
    _purge()
    _challenges[kind] = _Challenge(value=value, expires_at=time.time() + CHALLENGE_TTL)


def _take_challenge(kind: str) -> bytes:
    _purge()
    entry = _challenges.pop(kind, None)
    if entry is None:
        raise PasskeyError(
            "Aucune demande en cours ou demande expirée. Recommence."
        )
    return entry.value


def _purge() -> None:
    now = time.time()
    for key in [k for k, v in _challenges.items() if v.expires_at < now]:
        _challenges.pop(key, None)


# --- État de l'instance ---------------------------------------------------


def registration_open() -> bool:
    """L'inscription publique est-elle ouverte ?

    Ouverte uniquement si aucune passkey n'existe encore (premier démarrage),
    ou si on l'a explicitement réouverte en configuration.
    """
    return db.credential_count() == 0 or settings.allow_registration


def status() -> dict:
    return {
        "configured": db.credential_count() > 0,
        "registration_open": registration_open(),
        "rp_id": settings.rp_id,
    }


# --- Enregistrement ------------------------------------------------------


def start_registration(label: str | None = None) -> dict:
    """Génère les options de création de passkey à passer au navigateur."""
    if not registration_open():
        raise PasskeyError(
            "L'inscription est fermée. Connecte-toi avec une passkey "
            "existante pour en ajouter une nouvelle."
        )

    existing = db.list_credentials(OWNER_ID)
    options = generate_registration_options(
        rp_id=settings.rp_id,
        rp_name=settings.rp_name,
        user_id=OWNER_ID.encode(),
        user_name=label or "gordon",
        user_display_name=settings.rp_name,
        # Empêche d'enregistrer deux fois le même authentificateur.
        exclude_credentials=[
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(row["credential_id"])
            )
            for row in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            # Passkey découvrable : permet de se connecter sans saisir
            # d'identifiant au préalable.
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    _store_challenge("register", options.challenge)
    return json.loads(_options_to_json(options))


def finish_registration(credential: dict, label: str | None = None) -> str:
    """Vérifie la réponse du navigateur et enregistre la passkey."""
    challenge = _take_challenge("register")

    try:
        verified = verify_registration_response(
            credential=json.dumps(credential),
            expected_challenge=challenge,
            expected_origin=settings.rp_origin,
            expected_rp_id=settings.rp_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise PasskeyError(f"Passkey refusée : {exc}") from exc

    db.create_user(OWNER_ID, settings.rp_name)

    transports = credential.get("response", {}).get("transports")
    db.add_credential(
        credential_id=_b64url(verified.credential_id),
        user_id=OWNER_ID,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=",".join(transports) if transports else None,
        label=label or "Appareil principal",
    )
    return OWNER_ID


# --- Connexion -----------------------------------------------------------


def start_authentication() -> dict:
    if db.credential_count() == 0:
        raise PasskeyError(
            "Aucune passkey enregistrée sur cette instance."
        )

    options = generate_authentication_options(
        rp_id=settings.rp_id,
        challenge=secrets.token_bytes(32),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _store_challenge("authenticate", options.challenge)
    return json.loads(_options_to_json(options))


def finish_authentication(credential: dict) -> str:
    challenge = _take_challenge("authenticate")

    credential_id = credential.get("id")
    if not credential_id:
        raise PasskeyError("Réponse de passkey incomplète.")

    row = db.get_credential(credential_id)
    if row is None:
        raise PasskeyError("Passkey inconnue de cette instance.")

    try:
        verified = verify_authentication_response(
            credential=json.dumps(credential),
            expected_challenge=challenge,
            expected_origin=settings.rp_origin,
            expected_rp_id=settings.rp_id,
            credential_public_key=row["public_key"],
            credential_current_sign_count=row["sign_count"],
            require_user_verification=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise PasskeyError(f"Vérification échouée : {exc}") from exc

    db.update_sign_count(credential_id, verified.new_sign_count)
    return row["user_id"]


# --- Gestion des appareils ----------------------------------------------


def list_devices(user_id: str) -> list[dict]:
    return [
        {
            "id": row["credential_id"],
            "label": row["label"],
            "created_at": row["created_at"],
        }
        for row in db.list_credentials(user_id)
    ]


def remove_device(user_id: str, credential_id: str) -> None:
    """Supprime une passkey, en refusant de retirer la dernière.

    Sans ce garde-fou, l'utilisateur pourrait se verrouiller dehors
    définitivement : plus aucune passkey pour entrer, et l'inscription reste
    fermée tant qu'une passkey existe en base.
    """
    if db.credential_count() <= 1:
        raise PasskeyError(
            "Impossible de supprimer la dernière passkey : tu perdrais "
            "l'accès à l'instance. Enregistre d'abord un autre appareil."
        )
    if not db.delete_credential(credential_id, user_id):
        raise PasskeyError("Passkey introuvable.")


def _options_to_json(options) -> str:
    """Sérialise les options WebAuthn en JSON.

    py_webauthn expose cet utilitaire sous deux noms selon la version ;
    on tente les deux plutôt que d'épingler une version précise.
    """
    try:
        from webauthn import options_to_json

        return options_to_json(options)
    except ImportError:  # pragma: no cover
        from webauthn.helpers import options_to_json as helper

        return helper(options)
