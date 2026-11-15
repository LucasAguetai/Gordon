import { useCallback, useEffect, useState } from "react";
import { engineForget, getEngine, type EngineStatus } from "../api";

type Props = {
  onConnect: () => void;
  /** Change à chaque connexion réussie, pour rafraîchir l'état affiché. */
  refreshKey: number;
};

function formatDate(value: string): string {
  // SQLite horodate en UTC sans suffixe ; le Z rétablit le fuseau local.
  return new Date(value.replace(" ", "T") + "Z").toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "long",
  });
}

/** État de la connexion au moteur, et le bouton pour la (re)faire —
 *  pensé pour le cas « déconnecté, au téléphone, sans accès shell ». */
export default function EnginePanel({ onConnect, refreshKey }: Props) {
  const [status, setStatus] = useState<EngineStatus | null>(null);

  const load = useCallback(() => {
    getEngine().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(load, [load, refreshKey]);

  async function forget() {
    await engineForget().catch(() => {});
    load();
  }

  const line = !status
    ? "État inconnu."
    : status.env_token
      ? "Jeton fourni par la configuration du serveur (.env)."
      : status.saved_token
        ? `Jeton enregistré depuis la console${
            status.saved_at ? ` le ${formatDate(status.saved_at)}` : ""
          } — valable un an.`
        : "Aucun jeton enregistré : le moteur s'appuie sur la session du Mac.";

  return (
    <section className="devices engine-panel">
      <h3>Moteur</h3>
      <div className="device-row">
        <span className="grow">{line}</span>
        {status?.saved_token && !status.env_token && (
          <button className="link-btn neutral" onClick={() => void forget()}>
            Oublier
          </button>
        )}
        <button className="ghost-btn" onClick={onConnect}>
          {status?.saved_token ? "Reconnecter" : "Connecter"}
        </button>
      </div>
    </section>
  );
}
