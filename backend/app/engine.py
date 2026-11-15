"""Connexion du moteur depuis l'interface, sans accès shell.

Le CLI propose `setup-token` : un flux OAuth qui affiche une adresse à
ouvrir, attend un code en retour, et délivre un jeton valable un an. Fait
pour les machines sans navigateur — mais il est interactif, pensé pour un
humain devant un terminal.

Ce module joue ce rôle de terminal : il lance `setup-token` dans un
pseudo-terminal, extrait l'adresse d'autorisation pour l'afficher dans la
console web, transmet le code collé par l'utilisateur, puis capture le
jeton. Le jeton est conservé en base et injecté dans l'environnement du
moteur — depuis un téléphone, se reconnecter redevient possible.

Le pseudo-terminal est volontairement très large : à 80 colonnes, le CLI
replie l'adresse d'autorisation sur plusieurs lignes et elle devient
inextricable du reste de l'affichage.
"""

from __future__ import annotations

import fcntl
import os
import re
import select
import signal
import struct
import subprocess
import termios
import threading
import time
from dataclasses import dataclass, field

from . import db
from .config import settings

KV_TOKEN = "engine_oauth_token"

_ANSI = re.compile(
    r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-B]|\x1b[78=>]|\r"
)
_URL = re.compile(r"https://\S+oauth\S+")
_TOKEN = re.compile(r"sk-ant-[A-Za-z0-9_\-]{30,}")
_FAILURE = re.compile(r"invalid|error|failed|expired|denied", re.IGNORECASE)


class EngineError(RuntimeError):
    """Message d'échec destiné à l'interface."""


def _cli_path() -> str:
    if settings.cli_path:
        return settings.cli_path
    import claude_agent_sdk

    bundled = os.path.join(
        os.path.dirname(claude_agent_sdk.__file__), "_bundled", "claude"
    )
    if not os.path.exists(bundled):
        raise EngineError("Binaire du moteur introuvable.")
    return bundled


@dataclass
class _Flow:
    proc: subprocess.Popen
    master: int
    buffer: str = ""
    started: float = field(default_factory=time.time)

    def read_for(self, seconds: float) -> None:
        """Accumule la sortie du CLI pendant au plus `seconds`."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            ready, _, _ = select.select([self.master], [], [], 0.4)
            if not ready:
                if self.proc.poll() is not None:
                    return
                continue
            try:
                chunk = os.read(self.master, 4096)
            except OSError:
                return
            if not chunk:
                return
            self.buffer += _ANSI.sub("", chunk.decode("utf-8", "replace"))

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                self.proc.send_signal(signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            os.close(self.master)
        except OSError:
            pass


_flow: _Flow | None = None
_lock = threading.Lock()


def _spawn() -> _Flow:
    master, slave = os.openpty()
    # 400 colonnes : l'adresse d'autorisation tient sur une seule ligne.
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 400, 0, 0))

    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("CLAUDE", "ANTHROPIC"))
    }
    env["TERM"] = "xterm-256color"
    # Le CLI tente d'ouvrir un navigateur sur la machine hôte — ici c'est le
    # téléphone de l'utilisateur qui ouvrira l'adresse, pas le Mac.
    env["BROWSER"] = "/usr/bin/false"

    proc = subprocess.Popen(
        [_cli_path(), "setup-token"],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        close_fds=True,
    )
    os.close(slave)
    return _Flow(proc=proc, master=master)


def begin() -> str:
    """Démarre un flux de connexion et renvoie l'adresse d'autorisation."""
    global _flow
    with _lock:
        if _flow is not None:
            _flow.close()
        _flow = _spawn()

        deadline = time.time() + 30
        while time.time() < deadline:
            _flow.read_for(1.0)
            found = _URL.search(_flow.buffer)
            if found:
                return found.group(0)
            if _flow.proc.poll() is not None:
                break

        tail = _flow.buffer.strip().splitlines()[-3:]
        _flow.close()
        _flow = None
        raise EngineError(
            "Le CLI n'a pas fourni d'adresse d'autorisation. "
            + (" / ".join(tail) if tail else "Aucune sortie.")
        )


def finish(code: str) -> None:
    """Transmet le code collé par l'utilisateur et enregistre le jeton."""
    global _flow
    with _lock:
        if _flow is None or _flow.proc.poll() is not None:
            raise EngineError(
                "Aucune connexion en cours — génère d'abord un nouveau lien."
            )

        marker = len(_flow.buffer)
        os.write(_flow.master, (code.strip() + "\r").encode())

        deadline = time.time() + 90
        while time.time() < deadline:
            _flow.read_for(1.0)
            fresh = _flow.buffer[marker:]

            token = _TOKEN.search(fresh)
            if token:
                db.set_kv(KV_TOKEN, token.group(0))
                os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = token.group(0)
                _flow.close()
                _flow = None
                return

            if _FAILURE.search(fresh) or _flow.proc.poll() is not None:
                lines = [l for l in fresh.strip().splitlines() if l.strip()]
                _flow.close()
                _flow = None
                raise EngineError(
                    "Le code n'a pas été accepté. "
                    + (lines[-1][:200] if lines else "Réessaie avec un nouveau lien.")
                )

        _flow.close()
        _flow = None
        raise EngineError("Temps écoulé : génère un nouveau lien et recommence.")


def cancel() -> None:
    global _flow
    with _lock:
        if _flow is not None:
            _flow.close()
            _flow = None


def status() -> dict:
    """Ce que l'interface affiche : d'où vient l'authentification du moteur."""
    stored = db.get_kv(KV_TOKEN)
    return {
        # settings.oauth_token : jeton posé dans .env — il prime toujours.
        "env_token": bool(settings.oauth_token),
        "saved_token": stored is not None,
        "saved_at": stored["updated_at"] if stored else None,
        "pending": _flow is not None,
    }


def forget() -> None:
    """Oublie le jeton enregistré depuis l'interface."""
    db.delete_kv(KV_TOKEN)
    if settings.oauth_token:
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = settings.oauth_token
    else:
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)


def load_saved_token() -> None:
    """Au démarrage : le jeton enregistré reprend du service.

    Le .env garde la priorité — c'est un choix d'administration explicite,
    là où le jeton en base vient de l'interface.
    """
    if settings.oauth_token:
        return
    stored = db.get_kv(KV_TOKEN)
    if stored:
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = stored["value"]
