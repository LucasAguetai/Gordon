import { useEffect, useState } from "react";
import { getApple, type AppleOverview } from "../api";

type Props = {
  onManage: () => void;
};

const DOTS: Record<string, string> = {
  accorde: "ok",
  ecriture_seule: "warn",
  a_tester: "warn",
  non_demande: "warn",
  refuse: "bad",
  restreint: "bad",
};

/** Résumé des accès Apple sur l'accueil ; la gestion se fait sur sa page. */
export default function ApplePanel({ onManage }: Props) {
  const [data, setData] = useState<AppleOverview | null>(null);

  useEffect(() => {
    getApple().then(setData).catch(() => setData(null));
  }, []);

  // Pas de macOS, pas de panneau : le sujet n'existe pas sur cette machine.
  if (!data?.available) return null;

  const items = [
    ["Calendriers", data.calendriers?.status],
    ["Rappels", data.rappels?.status],
    ["Mail", data.mail?.status],
  ] as const;

  return (
    <section className="devices">
      <h3>Apple</h3>
      <div className="device-row">
        <span className="grow apple-summary">
          {items.map(([label, status]) => (
            <span className="apple-dot-item" key={label}>
              <i className={`dot dot-${DOTS[status ?? ""] ?? "warn"}`} />
              {label}
            </span>
          ))}
        </span>
        <button className="ghost-btn" onClick={onManage}>
          Gérer
        </button>
      </div>
    </section>
  );
}
