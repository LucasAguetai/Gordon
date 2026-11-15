import { useEffect, useState } from "react";
import {
  engineConnectBegin,
  engineConnectCancel,
  engineConnectCode,
} from "../api";

type Props = {
  onDone: () => void;
  onCancel: () => void;
};

type Step = "starting" | "authorize" | "checking" | "done";

/**
 * Connexion du moteur sans accès shell : le backend pilote le flux
 * `setup-token`, cette modale n'affiche que les deux gestes humains —
 * ouvrir le lien d'autorisation, coller le code obtenu.
 */
export default function EngineConnect({ onDone, onCancel }: Props) {
  const [step, setStep] = useState<Step>("starting");
  const [url, setUrl] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { url } = await engineConnectBegin();
        if (!alive) return;
        setUrl(url);
        setStep("authorize");
      } catch (e) {
        if (!alive) return;
        setError((e as Error).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  async function submit() {
    if (!code.trim()) return;
    setStep("checking");
    setError(null);
    try {
      await engineConnectCode(code);
      setStep("done");
    } catch (e) {
      setError((e as Error).message);
      setStep("authorize");
    }
  }

  function close() {
    // Un flux resté ouvert côté serveur n'attend personne d'autre.
    if (step !== "done") void engineConnectCancel().catch(() => {});
    onCancel();
  }

  return (
    <div className="sheet-backdrop" onClick={close}>
      <div className="sheet sheet-narrow" onClick={(e) => e.stopPropagation()}>
        <div className="sheet-head">
          <h2>Connecter le moteur</h2>
          <button className="ghost-btn" onClick={close}>
            Fermer
          </button>
        </div>

        <div className="engine-body">
          {step === "starting" && !error && (
            <p className="engine-note">Préparation du lien d'autorisation…</p>
          )}

          {step === "done" ? (
            <>
              <p className="engine-ok">✓ Moteur connecté.</p>
              <p className="engine-note">
                Le jeton est valable un an et survit aux redémarrages.
                Renvoie ton message : la conversation n'a pas bougé.
              </p>
              <button className="primary-btn" onClick={onDone}>
                C'est parti
              </button>
            </>
          ) : (
            url && (
              <>
                <p className="engine-note">
                  <strong>1.</strong> Ouvre le lien, connecte-toi à ton compte
                  Claude et autorise. Un code s'affiche à la fin.
                </p>
                <a
                  className="primary-btn engine-link"
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Ouvrir la page d'autorisation ↗
                </a>
                <p className="engine-note">
                  <strong>2.</strong> Colle le code ici.
                </p>
                <div className="engine-code">
                  <input
                    value={code}
                    placeholder="Code d'autorisation"
                    autoComplete="off"
                    spellCheck={false}
                    onChange={(e) => setCode(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void submit();
                    }}
                  />
                  <button
                    className="primary-btn"
                    disabled={!code.trim() || step === "checking"}
                    onClick={() => void submit()}
                  >
                    {step === "checking" ? "Vérification…" : "Valider"}
                  </button>
                </div>
              </>
            )
          )}

          {error && <p className="alert">{error}</p>}
        </div>
      </div>
    </div>
  );
}
