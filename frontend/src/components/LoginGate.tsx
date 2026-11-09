import { useEffect, useRef, useState } from "react";
import {
  getAuthStatus,
  loginWithPasskey,
  registerPasskey,
  supportsPasskeys,
  type AuthStatus,
} from "../api";
import { portraitIds } from "../portraits";
import PortraitReel from "./PortraitReel";

type Props = { onUnlocked: () => void };

/**
 * Rythme de la séquence de déverrouillage.
 *
 * La fenêtre système de la passkey recouvre la page et met un instant à
 * disparaître après validation. Sans cette pause, les portraits passent en
 * tenue derrière le popup et on rate complètement l'animation.
 */
const HOLD_MS = 900; // le temps que la fenêtre système s'efface
const REEL_MS = 900; // défilement, aligné sur la transition CSS
const SETTLE_MS = 450; // un battement pour voir l'équipe en tenue

export default function LoginGate({ onUnlocked }: Props) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suited, setSuited] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    getAuthStatus()
      .then(setStatus)
      .catch((e) => setError(e.message));
  }, []);

  // La séquence de déverrouillage est différée : sans ce nettoyage, un
  // démontage entre-temps laisserait des minuteurs modifier un composant
  // qui n'existe plus.
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach(window.clearTimeout);
  }, []);

  const supported = supportsPasskeys();

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      // On laisse la fenêtre système s'effacer, l'équipe passe en tenue,
      // puis la console s'ouvre.
      timers.current.push(
        window.setTimeout(() => setSuited(true), HOLD_MS),
        window.setTimeout(onUnlocked, HOLD_MS + REEL_MS + SETTLE_MS),
      );
    } catch (e) {
      const err = e as Error;
      // Annuler la fenêtre système n'est pas une erreur à signaler.
      if (err.name === "NotAllowedError" || err.name === "AbortError") {
        setError(null);
      } else {
        setError(err.message || "Échec de l'authentification.");
      }
      setBusy(false);
    }
  }

  const firstRun = status !== null && !status.configured;

  return (
    <div className="gate">
      <div className="gate-card">
        <div className="countdown" aria-hidden="true">
          <i>5</i>
          <i>4</i>
          <i>3</i>
          <i>2</i>
          <i>1</i>
        </div>

        <div className="gate-roster" aria-hidden="true">
          {portraitIds.map((id, i) => (
            <div
              className="roster-slot"
              key={id}
              style={{ animationDelay: `${0.75 + i * 0.09}s` }}
            >
              <PortraitReel
                agentId={id}
                state={suited ? "uniform" : "civil"}
                size={88}
              />
            </div>
          ))}
        </div>

        <h1 className="gate-title">Gordon</h1>

        {status === null && !error && (
          <p className="gate-sub">Connexion à la station…</p>
        )}

        {!supported && (
          <p className="alert">
            Ce navigateur ne gère pas les passkeys. Utilise Safari, Chrome ou
            Firefox dans une version récente.
          </p>
        )}

        {status !== null && supported && (
          <>
            <p className="gate-sub">
              {suited
                ? "Équipe en tenue. Ouverture de la console…"
                : firstRun
                  ? "Première mise en service. Enregistre une passkey pour devenir le propriétaire de cette instance."
                  : "Station verrouillée. Authentifie-toi avec ta passkey."}
            </p>

            {firstRun ? (
              <button
                className="primary-btn"
                disabled={busy}
                onClick={() => run(() => registerPasskey("Appareil principal"))}
              >
                {busy ? "Enregistrement…" : "Créer ma passkey"}
              </button>
            ) : (
              <button
                className="primary-btn"
                disabled={busy}
                onClick={() => run(loginWithPasskey)}
              >
                {busy ? "Vérification…" : "Déverrouiller"}
              </button>
            )}

            {status.registration_open && !firstRun && !suited && (
              <p className="gate-note">
                L'inscription est encore ouverte en configuration. Pense à
                repasser <code>GORDON_ALLOW_REGISTRATION</code> à{" "}
                <code>false</code>.
              </p>
            )}

            {firstRun && !suited && (
              <p className="gate-note">
                Dès cette passkey enregistrée, l'inscription se ferme
                automatiquement. Tu pourras ajouter d'autres appareils depuis
                la console.
              </p>
            )}
          </>
        )}

        {error && <p className="alert">{error}</p>}
      </div>
    </div>
  );
}
